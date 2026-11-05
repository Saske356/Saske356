#!/usr/bin/env python3
"""
Telegram-бот для управления Bitcoin-майнером cgminer.

Команды:
    /start  — запустить cgminer (подпроцесс)
    /stop   — остановить cgminer
    /status — CPU, RAM, температура и хешрейт (через API cgminer)
    /log    — последние строки лога майнера
    /help   — список команд

Как это работает:
    * cgminer запускается через subprocess.Popen с ключом --api-listen;
    * хешрейт и шары бот читает из JSON-API cgminer (TCP 127.0.0.1:4028);
    * загрузку системы берёт из psutil;
    * команды принимаются только от пользователей из ADMIN_IDS.

Запуск:
    pip install -r requirements.txt
    cp .env.example .env        # заполнить BOT_TOKEN, ADMIN_IDS, POOL_*
    python bot.py
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import shlex
import signal
import time
from collections import deque
from typing import Any, Awaitable, Callable

# Псевдонимы библиотек
import psutil as ps
import subprocess as sp
import telegram as tg
from telegram import constants as tgc
from telegram import ext as tge


# ---------------------------------------------------------------------------
# Настройки (переменные окружения или файл .env рядом с ботом)
# ---------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env_file(path: str = os.path.join(HERE, ".env")) -> None:
    """Подхватывает KEY=VALUE из .env, не перетирая уже заданные переменные."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
# Telegram ID тех, кому можно управлять майнером, через запятую
ADMIN_IDS: set[int] = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}

CGMINER_PATH: str = os.environ.get("CGMINER_PATH", "cgminer")
POOL_URL: str = os.environ.get("POOL_URL", "")            # stratum+tcp://pool:3333
POOL_USER: str = os.environ.get("POOL_USER", "")          # worker / BTC-адрес
POOL_PASS: str = os.environ.get("POOL_PASS", "x")
CGMINER_EXTRA: list[str] = shlex.split(os.environ.get("CGMINER_EXTRA", ""))  # доп. ключи

API_HOST: str = os.environ.get("CGMINER_API_HOST", "127.0.0.1")
API_PORT: int = int(os.environ.get("CGMINER_API_PORT", "4028"))
LOG_FILE: str = os.environ.get("CGMINER_LOG", os.path.join(HERE, "cgminer.log"))
STOP_ON_EXIT: bool = os.environ.get("STOP_ON_EXIT", "1") == "1"

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("miner-bot")


# ---------------------------------------------------------------------------
# Управление процессом cgminer
# ---------------------------------------------------------------------------

class MinerError(RuntimeError):
    """Ошибка запуска/остановки майнера с текстом для пользователя."""


class Miner:
    """Обёртка над подпроцессом cgminer и его JSON-API."""

    def __init__(self) -> None:
        self.proc: sp.Popen | None = None
        self.started_at: float = 0.0
        self._log_fh = None

    # --- состояние --------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def build_cmd(self) -> list[str]:
        """Командная строка cgminer. API слушает только localhost."""
        if not POOL_URL or not POOL_USER:
            raise MinerError("Не заданы POOL_URL и POOL_USER в .env")
        return [
            CGMINER_PATH,
            "-o", POOL_URL,
            "-u", POOL_USER,
            "-p", POOL_PASS,
            "--text-only",                       # без curses-интерфейса
            "--api-listen",                      # включить JSON-API
            "--api-port", str(API_PORT),
            "--api-allow", f"W:{API_HOST}",      # W — разрешить и команды записи (quit)
            *CGMINER_EXTRA,
        ]

    # --- запуск / остановка -------------------------------------------------

    def start(self) -> int:
        if self.running:
            raise MinerError(f"Майнер уже запущен (PID {self.proc.pid})")
        cmd = self.build_cmd()
        log.info("Запуск: %s", " ".join(shlex.quote(c) for c in cmd))
        self._log_fh = open(LOG_FILE, "ab", buffering=0)
        try:
            self.proc = sp.Popen(
                cmd,
                stdout=self._log_fh,
                stderr=sp.STDOUT,
                stdin=sp.DEVNULL,
                start_new_session=True,          # своя группа процессов — удобно гасить целиком
            )
        except FileNotFoundError:
            self._close_log()
            raise MinerError(f"Не найден исполняемый файл cgminer: {CGMINER_PATH}")
        self.started_at = time.time()
        return self.proc.pid

    async def stop(self, timeout: float = 10.0) -> int:
        if not self.running:
            raise MinerError("Майнер не запущен")
        pid = self.proc.pid
        # 1) вежливо — командой quit через API
        try:
            await api_command("quit", timeout=2)
        except Exception:
            pass
        # 2) SIGTERM группе процессов, 3) SIGKILL, если не завершился
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if await asyncio.to_thread(self._wait, timeout):
                break
            log.warning("cgminer не завершился, шлю %s", sig.name)
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                break
        await asyncio.to_thread(self._wait, timeout)
        self.proc = None
        self._close_log()
        return pid

    def _wait(self, timeout: float) -> bool:
        try:
            self.proc.wait(timeout=timeout)
            return True
        except sp.TimeoutExpired:
            return False

    def _close_log(self) -> None:
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None

    def exit_code(self) -> int | None:
        return None if self.proc is None else self.proc.poll()


async def api_command(command: str, parameter: str | None = None, timeout: float = 5.0) -> dict[str, Any]:
    """Запрос к JSON-API cgminer: {"command": "...", "parameter": "..."}.

    cgminer отвечает JSON-ом и закрывает соединение; в конце бывает \\x00.
    """
    req: dict[str, str] = {"command": command}
    if parameter is not None:
        req["parameter"] = parameter

    async def _call() -> dict[str, Any]:
        reader, writer = await asyncio.open_connection(API_HOST, API_PORT)
        try:
            writer.write(json.dumps(req).encode())
            await writer.drain()
            raw = await reader.read()             # читаем до закрытия сокета
        finally:
            writer.close()
        return json.loads(raw.decode(errors="replace").strip("\x00 \r\n"))

    return await asyncio.wait_for(_call(), timeout)


miner = Miner()


# ---------------------------------------------------------------------------
# Сбор статуса
# ---------------------------------------------------------------------------

def fmt_hashrate(mhs: float) -> str:
    """cgminer отдаёт хешрейт в MH/s — переводим в удобные единицы."""
    hs = mhs * 1e6
    for unit in ("H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s"):
        if hs < 1000:
            return f"{hs:.2f} {unit}"
        hs /= 1000
    return f"{hs:.2f} EH/s"


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_duration(sec: float) -> str:
    sec = int(sec)
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return (f"{d}д " if d else "") + f"{h:02d}:{m:02d}:{s:02d}"


def system_status() -> list[str]:
    """CPU, RAM, температура — синхронно, вызывается через asyncio.to_thread."""
    cpu = ps.cpu_percent(interval=1.0)           # средняя загрузка за 1 секунду
    per_core = ps.cpu_percent(interval=None, percpu=True)
    vm = ps.virtual_memory()
    lines = [
        "<b>Система</b>",
        f"CPU: {cpu:.0f}% ({ps.cpu_count()} ядер, макс. ядро {max(per_core):.0f}%)",
        f"RAM: {vm.percent:.0f}% — {fmt_bytes(vm.used)} из {fmt_bytes(vm.total)}",
    ]
    try:
        load1, load5, load15 = os.getloadavg()
        lines.append(f"Load avg: {load1:.2f} / {load5:.2f} / {load15:.2f}")
    except OSError:
        pass
    temps = getattr(ps, "sensors_temperatures", lambda: {})() or {}
    readings = [t.current for entries in temps.values() for t in entries if t.current]
    if readings:
        lines.append(f"Температура: макс. {max(readings):.0f}°C")

    if miner.running:
        try:
            p = ps.Process(miner.proc.pid)
            with p.oneshot():
                lines.append(
                    f"cgminer: PID {p.pid}, CPU {p.cpu_percent(interval=0.2):.0f}%, "
                    f"RAM {fmt_bytes(p.memory_info().rss)}"
                )
        except ps.NoSuchProcess:
            pass
    return lines


async def miner_status() -> list[str]:
    """Хешрейт, шары и пул из API cgminer."""
    lines = ["<b>Майнер</b>"]
    if not miner.running:
        code = miner.exit_code()
        lines.append("Остановлен" + (f" (код выхода {code})" if code is not None else ""))
        return lines

    lines.append(f"Работает {fmt_duration(time.time() - miner.started_at)}, PID {miner.proc.pid}")
    try:
        summary = (await api_command("summary"))["SUMMARY"][0]
    except (OSError, asyncio.TimeoutError, KeyError, IndexError, ValueError) as e:
        lines.append(f"API cgminer недоступно ({type(e).__name__}) — возможно, ещё запускается")
        return lines

    accepted = summary.get("Accepted", 0)
    rejected = summary.get("Rejected", 0)
    total = accepted + rejected
    rej_pct = 100 * rejected / total if total else 0.0
    lines += [
        f"Хешрейт (5с): {fmt_hashrate(summary.get('MHS 5s', 0))}",
        f"Хешрейт (средн.): {fmt_hashrate(summary.get('MHS av', 0))}",
        f"Шары: ✅ {accepted} / ❌ {rejected} ({rej_pct:.1f}%)",
        f"Аппаратные ошибки: {summary.get('Hardware Errors', 0)}",
    ]
    try:
        pools = (await api_command("pools")).get("POOLS", [])
        active = next((p for p in pools if p.get("Stratum Active") or p.get("Status") == "Alive"), None)
        if active:
            lines.append(f"Пул: {active.get('URL')} ({active.get('Status')})")
    except Exception:
        pass
    return lines


# ---------------------------------------------------------------------------
# Обработчики команд Telegram
# ---------------------------------------------------------------------------

Handler = Callable[[tg.Update, tge.ContextTypes.DEFAULT_TYPE], Awaitable[None]]


def admin_only(func: Handler) -> Handler:
    """Пропускает только пользователей из ADMIN_IDS; остальным показывает их ID."""
    @functools.wraps(func)
    async def wrapper(update: tg.Update, context: tge.ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or user.id not in ADMIN_IDS:
            uid = user.id if user else "?"
            log.warning("Отказ в доступе: %s", uid)
            await update.effective_message.reply_text(
                f"⛔ Нет доступа. Ваш Telegram ID: {uid}\n"
                "Владелец бота может добавить его в ADMIN_IDS."
            )
            return
        await func(update, context)
    return wrapper


@admin_only
async def cmd_start(update: tg.Update, context: tge.ContextTypes.DEFAULT_TYPE) -> None:
    try:
        pid = miner.start()
    except MinerError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return
    await asyncio.sleep(2)                       # даём процессу шанс упасть сразу
    if not miner.running:
        await update.message.reply_text(
            f"❌ cgminer завершился сразу (код {miner.exit_code()}). Смотрите /log"
        )
        return
    await update.message.reply_text(f"⛏ cgminer запущен, PID {pid}\nПул: {POOL_URL}\nСтатус: /status")


@admin_only
async def cmd_stop(update: tg.Update, context: tge.ContextTypes.DEFAULT_TYPE) -> None:
    try:
        pid = await miner.stop()
    except MinerError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return
    await update.message.reply_text(f"🛑 cgminer остановлен (PID {pid})")


@admin_only
async def cmd_status(update: tg.Update, context: tge.ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action(tgc.ChatAction.TYPING)
    sys_lines, miner_lines = await asyncio.gather(asyncio.to_thread(system_status), miner_status())
    await update.message.reply_text("\n".join(miner_lines + [""] + sys_lines),
                                    parse_mode=tgc.ParseMode.HTML)


@admin_only
async def cmd_log(update: tg.Update, context: tge.ContextTypes.DEFAULT_TYPE) -> None:
    if not os.path.exists(LOG_FILE):
        await update.message.reply_text("Лог пуст")
        return
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        tail = "".join(deque(f, maxlen=20))[-3500:]   # лимит сообщения Telegram — 4096
    safe = tail.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    await update.message.reply_text(f"<pre>{safe}</pre>", parse_mode=tgc.ParseMode.HTML)


async def cmd_help(update: tg.Update, context: tge.ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/start — запустить cgminer\n"
        "/stop — остановить cgminer\n"
        "/status — CPU, RAM, хешрейт\n"
        "/log — последние строки лога"
    )


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

async def on_startup(app: tge.Application) -> None:
    ps.cpu_percent(interval=None)                # первый вызов psutil всегда 0 — «прогреваем»
    await app.bot.set_my_commands([
        tg.BotCommand("start", "Запустить майнер"),
        tg.BotCommand("stop", "Остановить майнер"),
        tg.BotCommand("status", "CPU, RAM, хешрейт"),
        tg.BotCommand("log", "Лог майнера"),
        tg.BotCommand("help", "Помощь"),
    ])
    log.info("Бот запущен, админы: %s", sorted(ADMIN_IDS) or "не заданы!")


async def on_shutdown(app: tge.Application) -> None:
    if STOP_ON_EXIT and miner.running:
        log.info("Останавливаю cgminer перед выходом")
        await miner.stop()


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Задайте BOT_TOKEN в .env или переменной окружения")
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS пуст — бот будет отвечать всем «нет доступа» и показывать их ID")

    app = (
        tge.Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    app.add_handler(tge.CommandHandler("start", cmd_start))
    app.add_handler(tge.CommandHandler("stop", cmd_stop))
    app.add_handler(tge.CommandHandler("status", cmd_status))
    app.add_handler(tge.CommandHandler("log", cmd_log))
    app.add_handler(tge.CommandHandler("help", cmd_help))
    app.run_polling(allowed_updates=tg.Update.ALL_TYPES)


if __name__ == "__main__":
    main()
