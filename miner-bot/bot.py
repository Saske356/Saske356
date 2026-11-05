"""Учебный Telegram-бот-майнер. Майнит на ВАШЕМ сервере, открыто, по команде.

Показывает суть Proof-of-Work: перебор nonce, пока хеш блока не станет меньше цели.
Монеты учебные: блокчейн свой, живёт в файле chain.json.

Запуск:  BOT_TOKEN=123:ABC python bot.py   (или токен в файле .env)
"""

import asyncio
import html
import json
import logging
import os
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, Defaults

from chain import REWARD, TARGET_BLOCK_TIME, Chain, Miner

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
NAMES_PATH = os.path.join(HERE, "names.json")

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("miner-bot")

chain = Chain(os.path.join(HERE, "chain.json"))
active: dict[int, Miner] = {}   # кто сейчас майнит
names: dict[str, str] = json.load(open(NAMES_PATH, encoding="utf-8")) if os.path.exists(NAMES_PATH) else {}
esc = html.escape

MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("⛏ Майнить блок", callback_data="mine")],
    [InlineKeyboardButton("💰 Баланс", callback_data="balance"),
     InlineKeyboardButton("🏆 Топ", callback_data="top")],
    [InlineKeyboardButton("⛓ Последние блоки", callback_data="chain"),
     InlineKeyboardButton("❓ Как это работает", callback_data="how")],
])
STOP = InlineKeyboardMarkup([[InlineKeyboardButton("⏹ Остановить", callback_data="stop")]])

HOW = (
    "<b>Как работает майнинг (Proof-of-Work)</b>\n\n"
    "1. Блок = номер + <b>хеш прошлого блока</b> + время + майнер + <b>nonce</b> (просто число).\n"
    "2. От этих данных считается SHA-256. Получается 64 hex-символа, выглядит как случайный мусор.\n"
    "3. Правило сети: хеш должен быть <b>меньше цели</b>, то есть начинаться с N нулевых бит.\n"
    "4. Предсказать хеш нельзя, поэтому майнер <b>перебирает nonce</b>: 0, 1, 2, 3… "
    "и каждый раз считает хеш заново. Это и есть «работа».\n"
    "5. Нашёл подходящий: блок добавляется в цепочку, майнер получает награду.\n"
    "6. Проверить блок легко (один хеш), а найти трудно (миллионы хешей).\n"
    "7. Хеш каждого блока зависит от прошлого, поэтому подделать старый блок "
    "значит перемайнить всё после него.\n\n"
    f"<b>Сложность</b> подстраивается: если блоки находят быстрее {TARGET_BLOCK_TIME // 2} с, "
    "нужен ещё 1 нулевой бит (работы в 2 раза больше); если медленнее "
    f"{TARGET_BLOCK_TIME * 2} с, на 1 бит меньше.\n\n"
    "<b>Чем отличается от настоящего Bitcoin:</b> там сложность примерно 2⁷⁹ хешей на блок, "
    "и майнят специальные ASIC-устройства по сотни триллионов хешей в секунду. "
    "Этот бот делает сотни тысяч хешей в секунду на обычном процессоре, поэтому у него своя "
    "учебная сеть. В настоящей сети он не нашёл бы ни одного блока за всю жизнь Вселенной."
)


def name_of(uid: int) -> str:
    return esc(names.get(str(uid), f"id{uid}"))


def remember(update: Update) -> None:
    u = update.effective_user
    if u and names.get(str(u.id)) != u.first_name:
        names[str(u.id)] = u.first_name
        with open(NAMES_PATH, "w", encoding="utf-8") as f:
            json.dump(names, f, ensure_ascii=False)


def fmt_rate(r: float) -> str:
    return f"{r / 1000:.1f} kH/s" if r < 1e6 else f"{r / 1e6:.2f} MH/s"


async def reply(update: Update, text: str, kb=MENU) -> None:
    q = update.callback_query
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text, reply_markup=kb)
        except BadRequest:
            pass
    else:
        await update.effective_message.reply_text(text, reply_markup=kb)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    remember(update)
    await reply(update,
                "<b>⛏ Учебный майнер</b>\n\n"
                "Бот майнит блоки в своей мини-сети по тому же принципу, что и Bitcoin: "
                "перебирает числа, пока SHA-256 не даст хеш с нужным числом нулей.\n"
                f"За каждый найденный блок: <b>{REWARD} монет</b> (учебных).\n\n"
                f"Блоков в цепочке: <b>{chain.tip['index']}</b>")


async def mine(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    remember(update)
    uid = update.effective_user.id
    if uid in active:
        return await reply(update, "Ты уже майнишь, дождись блока.", STOP)
    if update.callback_query:
        await update.callback_query.answer()
    m = chain.new_miner(uid)
    active[uid] = m
    msg = await update.effective_message.reply_text(
        f"⛏ Майню блок <b>#{m.index}</b>, сложность {m.bits} бит…", reply_markup=STOP)

    task = asyncio.create_task(asyncio.to_thread(m.run))
    try:
        while not task.done():
            await asyncio.sleep(2)
            if task.done():
                break
            expected = 2 ** m.bits
            try:
                await msg.edit_text(
                    f"⛏ Майню блок <b>#{m.index}</b>\n\n"
                    f"Сложность: <b>{m.bits}</b> нулевых бит (~{expected:,} попыток в среднем)\n"
                    f"Перебрано nonce: <code>{m.attempts:,}</code>\n"
                    f"Скорость: <b>{fmt_rate(m.hashrate)}</b>\n"
                    f"Прошло: {time.time() - m.started:.0f} с", reply_markup=STOP)
            except BadRequest:
                pass
        block = task.result()
    finally:
        active.pop(uid, None)

    if block is None:
        return await msg.edit_text("⏹ Майнинг остановлен.", reply_markup=MENU)
    if not chain.add(block):
        return await msg.edit_text(
            f"😔 Блок #{block['index']} найден, но кто-то успел раньше. "
            "Твой блок ссылается на старую вершину цепочки, сеть его не примет "
            "(так в реальности появляются «осиротевшие» блоки).", reply_markup=MENU)

    zeros = len(block["hash"]) - len(block["hash"].lstrip("0"))
    await msg.edit_text(
        f"✅ <b>Блок #{block['index']} найден!</b>\n\n"
        f"nonce: <code>{block['nonce']}</code>\n"
        f"hash: <code>{block['hash']}</code>\n"
        f"(начинается с {zeros} нулей в hex, нужно было ≥{block['bits']} нулевых бит)\n\n"
        f"Попыток: {block['attempts']:,}, время: {block['seconds']} с, "
        f"скорость: {fmt_rate(block['attempts'] / max(block['seconds'], 1e-6))}\n"
        f"Награда: <b>+{REWARD} монет</b>, баланс: <b>{chain.balance(uid)}</b>", reply_markup=MENU)


async def stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    m = active.get(update.effective_user.id)
    if update.callback_query:
        await update.callback_query.answer("Останавливаю…" if m else "Нечего останавливать")
    if m:
        m.stop.set()


async def balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    mined = chain.balance(uid) // REWARD
    await reply(update, f"💰 Баланс: <b>{chain.balance(uid)}</b> монет\nНайдено блоков: {mined}")


async def top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    rows = [f"{i}. {name_of(uid)}: {n} бл. ({n * REWARD} монет)"
            for i, (uid, n) in enumerate(chain.top(), 1)]
    await reply(update, "🏆 <b>Топ майнеров</b>\n\n" + ("\n".join(rows) or "Пока никто ничего не намайнил."))


async def show_chain(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    lines = []
    for b in chain.blocks[-5:][::-1]:
        lines.append(f"<b>#{b['index']}</b> · {name_of(b['miner']) if b['index'] else 'genesis'} · "
                     f"{b['bits']} бит · nonce {b['nonce']}\n"
                     f"hash <code>{b['hash'][:24]}…</code>\n"
                     f"prev <code>{b['prev_hash'][:24]}…</code>")
    await reply(update, "⛓ <b>Последние блоки</b>\n"
                        "Видно, что prev каждого блока = hash предыдущего.\n\n" + "\n\n".join(lines)
                        + f"\n\nСледующий блок: сложность {chain.next_bits()} бит")


async def how(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, HOW)


ROUTES = {"menu": start, "mine": mine, "stop": stop, "balance": balance,
          "top": top, "chain": show_chain, "how": how}


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await ROUTES.get(update.callback_query.data, start)(update, ctx)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Нет токена. Запусти так: BOT_TOKEN=123:ABC python bot.py  (или положи его в .env)")
    app = (Application.builder().token(BOT_TOKEN)
           .defaults(Defaults(parse_mode=ParseMode.HTML)).concurrent_updates(True).build())
    for cmd, fn in [("start", start), ("mine", mine), ("stop", stop), ("balance", balance),
                    ("top", top), ("chain", show_chain), ("how", how)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    log.info("Майнер-бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
