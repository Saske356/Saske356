"""Telegram-бот для управления настоящим майнером Monero (XMRig) на ВАШЕМ компьютере.

Майнит открыто, по кнопке, на ваш кошелёк через пул. Управлять может только ADMIN_ID.

Запуск:  ./install_xmrig.sh && python bot.py   (настройки в .env, см. .env.example)
"""

import asyncio
import html
import json
import logging
import os
import time
import urllib.request

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, Defaults

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env() -> None:
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_load_env()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or 0)
WALLET = os.environ.get("WALLET", "").strip()
POOL = os.environ.get("POOL", "pool.supportxmr.com:443")
POOL_TLS = os.environ.get("POOL_TLS", "1") == "1"
WORKER = os.environ.get("WORKER", "bot")
CPU_PERCENT = max(1, min(100, int(os.environ.get("CPU_PERCENT", "50"))))
XMRIG = os.path.join(HERE, os.environ.get("XMRIG_PATH", "./xmrig/xmrig"))
API_PORT = 18088
LOG_PATH = os.path.join(HERE, "xmrig.log")

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("xmr-bot")
esc = html.escape

STATE: dict = {"proc": None, "started": 0.0, "stopping": False}

MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("▶️ Запустить", callback_data="start_mining"),
     InlineKeyboardButton("⏹ Остановить", callback_data="stop_mining")],
    [InlineKeyboardButton("📊 Статус", callback_data="status"),
     InlineKeyboardButton("💰 Баланс в пуле", callback_data="pool")],
    [InlineKeyboardButton("📜 Лог", callback_data="log"),
     InlineKeyboardButton("❓ Как это работает", callback_data="how")],
])

HOW = (
    "<b>Как это работает</b>\n\n"
    "• <b>XMRig</b> — открытый майнер. Он берёт у пула задание (заголовок блока Monero), "
    "перебирает nonce и считает хеш алгоритмом <b>RandomX</b>, который рассчитан на обычный процессор.\n"
    "• Найти целый блок Monero в одиночку почти невозможно, поэтому работает <b>пул</b>: "
    "он даёт задачи попроще (shares). Каждая принятая share — доказательство твоей работы.\n"
    "• Когда кто-то из пула находит блок, награда делится пропорционально shares. "
    "Твоя доля копится в пуле и выплачивается на кошелёк после порога (на SupportXMR это 0.1 XMR).\n\n"
    "<b>Честно про доход:</b> обычный процессор даёт примерно 1–15 kH/s, это центы в день. "
    "Часто электричество стоит дороже. На арендованных VPS майнинг обычно запрещён правилами, "
    "за это банят. Майнить стоит только на своём железе."
)


def is_admin(update: Update) -> bool:
    return bool(ADMIN_ID) and update.effective_user and update.effective_user.id == ADMIN_ID


def running() -> bool:
    p = STATE["proc"]
    return p is not None and p.returncode is None


def http_json(url: str, timeout: float = 5) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "xmr-miner-bot"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


async def get_json(url: str) -> dict | None:
    try:
        return await asyncio.to_thread(http_json, url)
    except Exception as e:  # noqa: BLE001 — сеть/таймаут/не тот ответ
        log.info("Запрос %s не удался: %s", url, e)
        return None


def fmt_hs(v) -> str:
    if v is None:
        return "—"
    return f"{v:.0f} H/s" if v < 1000 else f"{v / 1000:.2f} kH/s"


def fmt_dur(s: float) -> str:
    s = int(s)
    return f"{s // 3600} ч {s % 3600 // 60} мин" if s >= 3600 else f"{s // 60} мин {s % 60} с"


async def reply(update: Update, text: str) -> None:
    q = update.callback_query
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text, reply_markup=MENU)
        except BadRequest:
            pass
    else:
        await update.effective_message.reply_text(text, reply_markup=MENU)


def admin_only(fn):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_admin(update):
            uid = update.effective_user.id if update.effective_user else "?"
            if update.callback_query:
                await update.callback_query.answer("Нет доступа", show_alert=True)
            else:
                await update.effective_message.reply_text(
                    f"Этот бот управляет майнером владельца. Твой id: <code>{uid}</code>")
            return
        await fn(update, ctx)
    return wrapper


@admin_only
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = "⛏ майнит" if running() else "💤 остановлен"
    await reply(update,
                "<b>⛏ Майнер Monero (XMR)</b>\n\n"
                f"Состояние: <b>{state}</b>\n"
                f"Пул: <code>{esc(POOL)}</code>\n"
                f"Кошелёк: <code>{esc(WALLET[:8])}…{esc(WALLET[-6:])}</code>\n"
                f"Нагрузка: до {CPU_PERCENT}% потоков процессора")


async def _watch(proc: asyncio.subprocess.Process, app: Application) -> None:
    """Сообщает владельцу, если XMRig неожиданно завершился."""
    code = await proc.wait()
    if not STATE["stopping"] and STATE["proc"] is proc:
        await app.bot.send_message(ADMIN_ID, f"⚠️ XMRig завершился сам (код {code}). Загляни в 📜 Лог.",
                                   reply_markup=MENU)


@admin_only
async def start_mining(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if running():
        return await reply(update, "Майнер уже работает.")
    if not os.path.exists(XMRIG):
        return await reply(update, "XMRig не найден. Сначала выполни <code>./install_xmrig.sh</code>")
    if not WALLET:
        return await reply(update, "В .env не указан WALLET (адрес Monero-кошелька).")
    args = [XMRIG, "-o", POOL, "-u", WALLET, "-p", WORKER, "-k",
            f"--cpu-max-threads-hint={CPU_PERCENT}", "--donate-level=1",
            "--http-host=127.0.0.1", f"--http-port={API_PORT}", "--no-color", f"--log-file={LOG_PATH}"]
    if POOL_TLS:
        args.append("--tls")
    STATE["stopping"] = False
    STATE["proc"] = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    STATE["started"] = time.time()
    asyncio.create_task(_watch(STATE["proc"], ctx.application))
    log.info("XMRig запущен, pid %s", STATE["proc"].pid)
    await reply(update, "▶️ Майнер запущен. Через ~30 секунд в 📊 Статус появится хешрейт.")


async def _stop() -> None:
    p = STATE["proc"]
    if p and p.returncode is None:
        STATE["stopping"] = True
        p.terminate()
        try:
            await asyncio.wait_for(p.wait(), 10)
        except asyncio.TimeoutError:
            p.kill()


@admin_only
async def stop_mining(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not running():
        return await reply(update, "Майнер и так остановлен.")
    await _stop()
    await reply(update, f"⏹ Майнер остановлен. Проработал {fmt_dur(time.time() - STATE['started'])}.")


@admin_only
async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not running():
        return await reply(update, "💤 Майнер остановлен.")
    s = await get_json(f"http://127.0.0.1:{API_PORT}/2/summary")
    if not s:
        return await reply(update, "⏳ Майнер запускается, API ещё не ответил. Попробуй через несколько секунд.")
    hr = (s.get("hashrate") or {}).get("total") or [None, None, None]
    res = s.get("results") or {}
    conn = s.get("connection") or {}
    cpu = s.get("cpu") or {}
    await reply(update,
                "📊 <b>Статус майнера</b>\n\n"
                f"Хешрейт: <b>{fmt_hs(hr[0])}</b> (10 с) · {fmt_hs(hr[1])} (1 мин) · {fmt_hs(hr[2])} (15 мин)\n"
                f"Shares принято: <b>{res.get('shares_good', 0)}</b> из {res.get('shares_total', 0)}\n"
                f"Пул: <code>{esc(str(conn.get('pool', POOL)))}</code>, пинг {conn.get('ping', '—')} мс\n"
                f"Алгоритм: {esc(str(s.get('algo', '—')))}\n"
                f"Процессор: {esc(str(cpu.get('brand', '—')))}\n"
                f"Работает: {fmt_dur(time.time() - STATE['started'])}")


@admin_only
async def pool(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if "supportxmr" not in POOL:
        return await reply(update, "Баланс умею показывать только для SupportXMR. "
                                   "Для другого пула открой его сайт и вставь адрес кошелька.")
    d = await get_json(f"https://supportxmr.com/api/miner/{WALLET}/stats")
    if not d:
        return await reply(update, "Пул не ответил. Если ты только начал, статистика появится через пару минут.")
    atomic = 1e12  # 1 XMR = 10^12 атомарных единиц
    await reply(update,
                "💰 <b>Баланс в пуле SupportXMR</b>\n\n"
                f"Ожидает выплаты: <b>{d.get('amtDue', 0) / atomic:.6f} XMR</b>\n"
                f"Уже выплачено: {d.get('amtPaid', 0) / atomic:.6f} XMR\n"
                f"Хешрейт по данным пула: {fmt_hs(d.get('hash'))}\n"
                f"Принятых shares: {d.get('validShares', 0)}\n\n"
                "Выплата на кошелёк приходит автоматически после 0.1 XMR.")


@admin_only
async def show_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not os.path.exists(LOG_PATH):
        return await reply(update, "Лога пока нет.")
    with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
        tail = f.readlines()[-15:]
    text = "".join(tail)[-3500:]
    await reply(update, f"📜 <b>Последние строки лога</b>\n\n<pre>{esc(text)}</pre>")


async def how(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, HOW)


ROUTES = {"menu": cmd_start, "start_mining": start_mining, "stop_mining": stop_mining,
          "status": status, "pool": pool, "log": show_log, "how": how}


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await ROUTES.get(update.callback_query.data, cmd_start)(update, ctx)


async def on_shutdown(app: Application) -> None:
    await _stop()   # бот выключается — майнер тоже


def main() -> None:
    if not BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("Заполни BOT_TOKEN и ADMIN_ID в .env (см. .env.example)")
    app = (Application.builder().token(BOT_TOKEN).defaults(Defaults(parse_mode=ParseMode.HTML))
           .post_shutdown(on_shutdown).build())
    for cmd, fn in [("start", cmd_start), ("mine", start_mining), ("stop", stop_mining),
                    ("status", status), ("pool", pool), ("log", show_log), ("how", how)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    log.info("Бот запущен, админ %s", ADMIN_ID)
    app.run_polling()


if __name__ == "__main__":
    main()
