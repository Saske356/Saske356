"""Сквозные сценарии бота на имитации Telegram: python3 -m unittest discover -s tests

Проходит весь путь гостя и админа: реферал, пробный период, покупка с устройствами, продление,
автопродление, подарки, промокоды, тикеты, возвраты, фоновые задачи, мини-приложение, /server,
резервные копии и режим настоящего VPN. Заодно проверяет каждый экран: длину подписи и HTML.
В сеть и в Telegram тесты не ходят.
"""

import asyncio, base64, html.parser, itertools, json, os, sys, tempfile, time, unittest
from unittest.mock import AsyncMock, MagicMock

S = tempfile.mkdtemp(prefix="aurora-test-")
BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Все настройки задаём явно: на сервере рядом лежит настоящий .env, он не должен влиять на тесты.
os.environ.update(DB_PATH=os.path.join(S, "test.db"), ADMIN_IDS="1", SUPPORT_USERNAME="aurora_help",
                  BOT_TOKEN="1:x", CHANNEL="@aurora_news", MINIAPP_URL="", VPN_MODE="demo",
                  TRIAL_DAYS="1", REF_BONUS_DAYS="3", REF_ON_JOIN="1", REFUND_DAYS="3", AUTO_RENEW="1",
                  CHANNEL_BONUS_DAYS="1", BACKUP_DAILY="1", SET_PROFILE="1", BRAND="Aurora VPN")
sys.path.insert(0, BOT_DIR)
try:
    import bot, config
except ImportError as e:  # нет библиотек бота: pip install -r requirements.txt
    raise unittest.SkipTest(f"не хватает библиотек бота: {e}")

DAY = 86400
BANNER_UID = "BANNER"
captions = []
mid = itertools.count(1000)


class TagCheck(html.parser.HTMLParser):
    ALLOWED = {"b", "i", "code", "blockquote", "a", "u", "s", "pre"}
    def __init__(self):
        super().__init__(); self.stack = []; self.bad = []
    def handle_starttag(self, t, a):
        if t not in self.ALLOWED: self.bad.append(t)
        self.stack.append(t)
    def handle_endtag(self, t):
        if not self.stack or self.stack.pop() != t: self.bad.append("/" + t)


def check_caption(text, limit=1024):
    assert text and len(text) <= limit, f"caption length {len(text or '')}"
    p = TagCheck(); p.feed(text); p.close()
    assert not p.bad and not p.stack, f"bad html {p.bad} {p.stack}: {text[:100]}"
    captions.append(text)


def msg_obj():
    m = MagicMock(); m.message_id = next(mid)
    m.photo = [MagicMock(file_id="FILE", file_unique_id=BANNER_UID)]
    return m


def make_ctx():
    ctx = MagicMock()
    ctx.bot_data = {"banners": {n: b"jpg" for n in ["main", "plans", "key", "howto", "profile", "ref",
                                                    "support", "welcome"]},
                    "banner_ids": {}, "banner_uids": {BANNER_UID: "main"}}
    ctx.user_data = {}
    ctx.args = []
    b = ctx.bot
    b.username = "aurora_vpn_bot"
    async def send_photo(chat_id, photo, caption=None, reply_markup=None, message_effect_id=None):
        if caption: check_caption(caption)
        ctx.effects.append(message_effect_id)
        return msg_obj()
    ctx.effects = []
    b.send_photo = AsyncMock(side_effect=send_photo)
    async def send_message(chat_id, text, reply_markup=None):
        check_caption(text, 4096)  # у обычного сообщения предел 4096 символов, у подписи к фото 1024
        return msg_obj()
    b.send_message = AsyncMock(side_effect=send_message)
    b.copy_message = AsyncMock(side_effect=lambda *a, **k: msg_obj())
    b.send_invoice = AsyncMock()
    b.create_invoice_link = AsyncMock(return_value="https://t.me/$autoinv")
    b.refund_star_payment = AsyncMock()
    b.edit_user_star_subscription = AsyncMock()
    b.set_chat_menu_button = AsyncMock()
    b.get_chat_member = AsyncMock()
    b.send_document = AsyncMock()
    return ctx


def make_update(uid, name="Саша", data=None, text=None, banner=True, reply_to=None):
    upd = MagicMock()
    upd.effective_user.id = uid; upd.effective_user.username = f"user{uid}"
    upd.effective_user.first_name = name
    upd.effective_chat.id = uid
    if data is not None:
        q = MagicMock(); q.data = data; q.answer = AsyncMock()
        async def edit(caption=None, reply_markup=None):
            check_caption(caption)
        q.edit_message_caption = AsyncMock(side_effect=edit)
        async def edit_media(media=None, reply_markup=None):
            check_caption(media.caption)
            m = MagicMock(); m.photo = [MagicMock(file_id="F2", file_unique_id="U_" + str(id(media)))]
            return m
        q.edit_message_media = AsyncMock(side_effect=edit_media)
        q.message.photo = [MagicMock(file_unique_id=BANNER_UID if banner else "OTHER")]
        upd.callback_query = q
    else:
        upd.callback_query = None
    m = MagicMock(); m.text = text; m.reply_text = AsyncMock()
    m.chat_id = uid; m.message_id = next(mid)
    m.reply_to_message = None if reply_to is None else MagicMock(message_id=reply_to)
    upd.message = m
    return upd


async def press(uid, data, ctx, **kw):
    u = make_update(uid, data=data, **kw)
    await bot.on_button(u, ctx)
    return u


def alerted(u):
    return bool(u.callback_query.answer.await_args and u.callback_query.answer.await_args.kwargs.get("show_alert"))


async def pay(uid, ctx, payload, amount, charge, recurring=False, first=False):
    u = make_update(uid)
    sp = MagicMock(); sp.invoice_payload = payload; sp.total_amount = amount
    sp.telegram_payment_charge_id = charge
    sp.is_recurring = recurring; sp.is_first_recurring = first
    u.message.successful_payment = sp
    await bot.paid(u, ctx)


async def precheck(uid, payload, amount, ctx):
    pc = MagicMock(); pc.answer = AsyncMock(); pc.invoice_payload = payload
    pc.currency = "XTR"; pc.total_amount = amount; pc.from_user.id = uid
    upd = MagicMock(); upd.pre_checkout_query = pc
    await bot.precheckout(upd, ctx)
    return pc.answer.await_args.kwargs["ok"]


def near(a, b, tol=10):
    return abs(a - b) < tol



def make_provider(d):
    """Провайдер с заглушкой Xray, которая, как настоящий, отказывается от файлов без .json."""
    import xray_provider as xp
    p = os.path.join(d, "xray")
    with open(p, "w") as f:
        f.write('#!/bin/sh\ncase "$4" in *.json) exit 0;; *) echo "Failed to get format of $4"; exit 1;; esac\n')
    os.chmod(p, 0o755)
    return xp.XrayProvider(state_path=os.path.join(d, "s.json"), config_path=os.path.join(d, "c.json"),
                           xray_bin=p, public_host="203.0.113.7", port=443, sni="www.microsoft.com",
                           private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0,
                           brand="Aurora VPN", default_location="🇸🇪 Швеция", restart_cmd=("true",))


async def main():
    ctx = make_ctx()
    db = bot.db

    # 1. реферал: +3 дня сразу, один раз, не за себя
    await bot.start(make_update(100, "Реферер"), ctx)
    ctx.args = ["ref_100"]; await bot.start(make_update(200, "Друг"), ctx)
    s100 = db.primary_sub(100)
    assert s100 and near(s100["expires_at"] - time.time(), 3 * DAY, 60) and s100["key_active"] == 1
    ctx.args = ["ref_100"]; await bot.start(make_update(200, "Друг"), ctx)
    assert db.primary_sub(100)["expires_at"] == s100["expires_at"]
    ctx.args = ["ref_300"]; await bot.start(make_update(300, "Сам"), ctx)
    assert not db.user_subs(300)
    ctx.args = []

    # 2. пробный период
    u = await press(200, "trial", ctx)
    t = db.user_subs(200)
    assert len(t) == 1 and t[0]["name"] == "Пробный ключ" and near(t[0]["expires_at"] - time.time(), DAY, 60)
    u = await press(200, "trial", ctx); assert alerted(u)
    assert not bot.can_trial(db.get_user(100)), "у кого уже есть подписка, пробника нет"

    # 3. экраны
    for uid in (300, 200):
        for data in ["menu", "plans", "subs", "howto", "how:android", "how:ios", "how:windows", "how:mac",
                     "profile", "ref", "promo", "support", "tk", "gift", "ch", "fix"]:
            await press(uid, data, ctx)
    ctx.user_data.clear()
    sid200 = db.user_subs(200)[0]["id"]
    await press(200, f"sub:{sid200}", ctx)
    u = await press(300, f"sub:{sid200}", ctx); assert alerted(u), "чужую подписку не открыть"

    # 4. новая подписка на 3 устройства, 3 месяца
    await press(200, "buy:m3", ctx)          # есть подписки -> выбор цели
    await press(200, "bd:m3", ctx)           # выбор устройств
    await press(200, "bn:m3:3", ctx)         # m3 не месячный -> сразу счёт
    kw = ctx.bot.send_invoice.await_args.kwargs
    price = config.plan_price("m3", 3)
    assert kw["prices"][0].amount == price == 538 and kw["payload"] == f"v2:b:m3:90:{price}:3:0:-"
    assert await precheck(200, kw["payload"], price, ctx)
    assert not await precheck(200, kw["payload"], 1, ctx)
    assert not await precheck(200, "plan:m3:90:269", 269, ctx), "старый формат счёта отклоняется"
    u = await press(200, "bn:m3:4", ctx); assert alerted(u), "4 устройства нет в вариантах"
    await pay(200, ctx, kw["payload"], price, "C1")
    subs = db.user_subs(200); new = subs[-1]
    assert len(subs) == 2 and new["devices"] == 3 and near(new["expires_at"] - time.time(), 90 * DAY, 60)
    assert db.get_payment("C1")["sub_id"] == new["id"] and ctx.effects[-1] == bot.CONFETTI
    await pay(200, ctx, kw["payload"], price, "C1")  # дубль
    assert len(db.user_subs(200)) == 2

    # 5. продление этой подписки разово на месяц
    await press(200, f"ext:{new['id']}", ctx)
    await press(200, f"bt:m1:{new['id']}", ctx)   # месячный -> выбор способа оплаты
    await press(200, f"po:e:m1:3:{new['id']}", ctx)
    kw = ctx.bot.send_invoice.await_args.kwargs
    p_ext = config.plan_price("m1", 3)
    assert kw["payload"] == f"v2:e:m1:30:{p_ext}:3:{new['id']}:-"
    assert await precheck(200, kw["payload"], p_ext, ctx)
    assert not await precheck(300, kw["payload"], p_ext, ctx), "чужую подписку не продлить"
    before = db.get_sub(new["id"])["expires_at"]
    await pay(200, ctx, kw["payload"], p_ext, "C2")
    assert near(db.get_sub(new["id"])["expires_at"], before + 30 * DAY)
    u = await press(300, f"po:e:m1:3:{new['id']}", ctx); assert alerted(u)

    # 6. автопродление: новая подписка на 2 устройства
    await press(300, "bn:m1:2", ctx)
    await press(300, "pa:n:m1:2:0", ctx)
    lk = ctx.bot.create_invoice_link.await_args.kwargs
    p_auto = config.plan_price("m1", 2)
    assert lk["subscription_period"] == 2592000 and lk["prices"][0].amount == p_auto
    payload = lk["payload"]; token = payload.split(":")[-1]
    assert payload.startswith(f"v2:a:m1:30:{p_auto}:2:0:") and len(token) == 12
    assert await precheck(300, payload, p_auto, ctx)
    await pay(300, ctx, payload, p_auto, "A1", recurring=True, first=True)
    a = db.user_subs(300)[-1]
    assert a["auto_active"] == 1 and a["auto_token"] == token and a["auto_charge_id"] == "A1"
    exp = a["expires_at"]
    await pay(300, ctx, payload, p_auto, "A2", recurring=True, first=False)   # следующий месяц
    assert near(db.get_sub(a["id"])["expires_at"], exp + 30 * DAY) and db.get_payment("A2")["kind"] == "renew"
    await pay(300, ctx, payload, p_auto, "A2", recurring=True, first=False)   # дубль
    assert near(db.get_sub(a["id"])["expires_at"], exp + 30 * DAY)
    assert len(db.user_subs(300)) == 1
    await press(300, f"noauto:{a['id']}", ctx)
    await press(300, f"noautook:{a['id']}", ctx)
    ctx.bot.edit_user_star_subscription.assert_awaited_with(300, "A1", True)
    assert db.get_sub(a["id"])["auto_active"] == 0

    # 7. подарок
    await press(300, "gift", ctx); await press(300, "gd:m1", ctx)
    await press(300, "bg:m1:1", ctx)
    kw = ctx.bot.send_invoice.await_args.kwargs
    assert kw["payload"] == "v2:g:m1:30:99:1:0:-"
    await pay(300, ctx, kw["payload"], 99, "G1")
    code = db.get_payment("G1")["gift_code"]; assert code.startswith("GIFT-")
    await bot.start(make_update(400, "Одарённый"), ctx)
    ctx.args = [f"gift_{code}"]; await bot.start(make_update(400, "Одарённый"), ctx)
    g = db.user_subs(400)
    assert len(g) == 1 and near(g[0]["expires_at"] - time.time(), 30 * DAY, 60)
    ctx.args = []
    st, _ = db.redeem_gift(code, 500); assert st == "used"
    assert db.redeem_gift("GIFT-NOPE", 500)[0] == "not_found"

    # 8. промокоды
    ctx.args = ["SUMMER", "5", "1"]; await bot.addpromo(make_update(1), ctx)
    ctx.args = ["GIFT-X", "5", "1"]; u = make_update(1); await bot.addpromo(u, ctx)
    assert "GIFT-" in u.message.reply_text.await_args.args[0]
    ctx.args = []
    await press(400, "promo", ctx)
    await bot.on_message(make_update(400, text="summer"), ctx)
    assert near(db.primary_sub(400)["expires_at"] - time.time(), 35 * DAY, 60)
    assert db.redeem_promo("SUMMER", 400)[0] == "already"

    # 9. тикеты поддержки
    await press(400, "tk", ctx)
    assert ctx.user_data.get("await") == "ticket"
    ctx.bot.copy_message.reset_mock(); ctx.bot.send_message.reset_mock()
    await bot.on_message(make_update(400, text="Не подключается"), ctx)
    head_msg = ctx.bot.send_message.await_args_list[0]
    assert head_msg.args[0] == 1 and "Обращение" in head_msg.args[1]
    assert ctx.bot.copy_message.await_args_list[0].args[0] == 1
    admin_msgs = db.qa("SELECT admin_msg FROM tickets WHERE user_id=400")
    assert len(admin_msgs) == 2
    ctx.bot.copy_message.reset_mock()
    await bot.on_message(make_update(1, text="Переустановите приложение", reply_to=admin_msgs[0][0]), ctx)
    assert ctx.bot.copy_message.await_args.args[0] == 400, "ответ ушёл гостю"
    ctx.bot.copy_message.reset_mock()
    await bot.on_message(make_update(1, text="привет", reply_to=999999), ctx)
    assert ctx.bot.copy_message.await_count == 0

    # 10. переименование
    s = db.user_subs(400)[0]
    await press(400, f"ren:{s['id']}", ctx)
    await bot.on_message(make_update(400, text="  Мой   телефон  "), ctx)
    assert db.get_sub(s["id"])["name"] == "Мой телефон"
    await press(400, f"ren:{s['id']}", ctx)
    await bot.on_message(make_update(400, text="Х" * 40), ctx)
    assert len(db.get_sub(s["id"])["name"]) == 24
    u = await press(300, f"ren:{s['id']}", ctx); assert alerted(u)

    # 11. бонус за канал
    ctx.bot.get_chat_member.return_value = MagicMock(status="left")
    await press(300, "chk", ctx)
    assert db.get_user(300)["channel_bonus"] == 0
    ctx.bot.get_chat_member.return_value = MagicMock(status="member")
    before = db.primary_sub(300)["expires_at"]
    await press(300, "chk", ctx)
    assert db.get_user(300)["channel_bonus"] == 1 and near(db.primary_sub(300)["expires_at"], before + DAY)
    await press(300, "chk", ctx)
    assert near(db.primary_sub(300)["expires_at"], before + DAY), "бонус один раз"
    assert "канал" not in str([b.text for r in bot.main_kb(db.get_user(300)).inline_keyboard for b in r])

    # 12. админка и возвраты
    await bot.start(make_update(1, "Админ"), ctx)
    await bot.admin(make_update(1), ctx)
    st = db.stats(); assert st["auto"] == 0 and st["payments"] == 5, st
    text, kb = bot.payments_view(); check_caption(text)
    ctx.args = ["@user300"]; await bot.payments(make_update(1), ctx); ctx.args = []
    pid = db.get_payment("C2")["id"]
    await press(200, f"adm:rfok:{pid}", ctx)
    assert ctx.bot.refund_star_payment.await_count == 0, "не админ не возвращает"
    before = db.get_sub(new["id"])["expires_at"]
    await press(1, f"adm:rf:{pid}", ctx)
    await press(1, f"adm:rfok:{pid}", ctx)
    ctx.bot.refund_star_payment.assert_awaited_with(200, "C2")
    assert near(db.get_sub(new["id"])["expires_at"], before - 30 * DAY)
    before = db.get_sub(g[0]["id"])["expires_at"]
    ctx.args = ["G1"]; await bot.refund(make_update(1), ctx); ctx.args = []
    assert db.get_gift(code)["void"] == 1 and near(db.get_sub(g[0]["id"])["expires_at"], before - 30 * DAY)
    db.set_auto(a["id"], token, "A1", True)
    ctx.bot.edit_user_star_subscription.reset_mock()
    ctx.args = ["A1"]; await bot.refund(make_update(1), ctx); ctx.args = []
    ctx.bot.edit_user_star_subscription.assert_awaited_with(300, "A1", True)
    assert db.get_sub(a["id"])["auto_active"] == 0
    ctx.args = ["400", "10"]; await bot.give(make_update(1), ctx); ctx.args = []
    await bot.testpay(make_update(1), ctx)
    kw = ctx.bot.send_invoice.await_args.kwargs
    assert kw["prices"][0].amount == 5 and await precheck(1, kw["payload"], 5, ctx)
    assert not await precheck(200, kw["payload"], 5, ctx)
    ctx.user_data.clear(); ctx.bot.copy_message.reset_mock()
    await press(1, "adm:bc", ctx)
    await bot.on_message(make_update(1, text="Акция!"), ctx)
    await bot.STATE["broadcast"]  # рассылка идёт в фоне
    assert ctx.bot.copy_message.await_count == len(db.all_user_ids())
    assert "Доставлено: " in ctx.bot.send_message.await_args.args[1]
    # Telegram просит подождать: сообщение не теряется, а уходит повторно
    from telegram.error import RetryAfter
    calls = {"n": 0}
    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RetryAfter(0)
        return msg_obj()
    ctx.bot.copy_message = AsyncMock(side_effect=flaky)
    ok, fail = await bot.broadcast(ctx.bot, 1, 1, 5)
    assert ok == len(db.all_user_ids()) and fail == 0 and calls["n"] == ok + 1
    ctx.bot.copy_message = AsyncMock(side_effect=lambda *a, **k: msg_obj())
    # воронка и трафик
    for data in ("adm:fun", "adm:trf"):
        await press(1, data, ctx)
    f = db.funnel(); assert f["users"] >= 5 and f["paid"] >= 2 and f["trial"] == 1
    check_caption(bot.funnel_text()); check_caption(bot.traffic_text())

    # 12b. сервер и резервные копии
    await bot.server(make_update(1), ctx)
    st_text = await bot.server_text(); check_caption(st_text)
    assert "демо-режим" in st_text and "Диск" in st_text and "Гостей" in st_text
    await press(1, "adm:srv", ctx)
    n_cap = len(captions); await bot.server(make_update(200), ctx); assert len(captions) == n_cap, "не админ"
    await bot.backup(make_update(200), ctx); assert ctx.bot.send_document.await_count == 0
    await bot.backup(make_update(1), ctx)
    call = ctx.bot.send_document.await_args
    assert ctx.bot.send_document.await_count == 1 and call.args[0] == 1
    assert call.kwargs["filename"].endswith("-bot.db") and call.kwargs["filename"].startswith("aurora-20")
    blob = call.kwargs["document"].getvalue()
    assert blob[:15] == b"SQLite format 3"
    import sqlite3 as _sq
    rp = os.path.join(S, "restored.db")
    with open(rp, "wb") as f:
        f.write(blob)
    rc = _sq.connect(rp)
    assert rc.execute("SELECT COUNT(*) FROM users").fetchone()[0] == len(db.all_user_ids())
    assert rc.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == db.q1("SELECT COUNT(*) FROM subscriptions")[0]
    rc.close(); os.remove(rp)
    check_caption(call.kwargs["caption"])
    await press(1, "adm:bak", ctx); assert ctx.bot.send_document.await_count == 2
    await press(200, "adm:bak", ctx); assert ctx.bot.send_document.await_count == 2
    await bot.backup_job(ctx); assert ctx.bot.send_document.await_count == 3
    assert [f for f in os.listdir(config.BACKUP_DIR) if f.endswith(".tar.gz")], "копия на диске сервера"
    # с паролем копия шифруется одним архивом и расшифровывается openssl
    import shutil, subprocess, tarfile, io as _io
    if shutil.which("openssl"):
        config.BACKUP_PASSWORD = "s3cret pass"
        ctx.bot.send_document.reset_mock()
        await bot.backup(make_update(1), ctx)
        call = ctx.bot.send_document.await_args
        assert ctx.bot.send_document.await_count == 1 and call.kwargs["filename"].endswith(".tar.gz.enc")
        enc = call.kwargs["document"].getvalue(); assert not enc.startswith(b"\x1f\x8b")
        plain = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                                "-pass", "pass:s3cret pass"], input=enc, capture_output=True, check=True).stdout
        names = tarfile.open(fileobj=_io.BytesIO(plain)).getnames()
        assert names == ["bot.db"], names
        check_caption(call.kwargs["caption"])
        config.BACKUP_KEEP = 2
        for _ in range(3):
            await bot.store_backup()
        assert len([f for f in os.listdir(config.BACKUP_DIR) if f.startswith("aurora-")]) <= 2
        config.BACKUP_PASSWORD = ""

    # 13. фоновые задачи
    c = db.conn
    s_auto, s_plain = db.user_subs(300)[0], db.user_subs(400)[0]
    c.execute("UPDATE subscriptions SET expires_at=?, auto_active=1 WHERE id=?", (time.time() + 3600, s_auto["id"]))
    c.execute("UPDATE subscriptions SET expires_at=? WHERE id=?", (time.time() + 3600, s_plain["id"]))
    c.execute("UPDATE subscriptions SET expires_at=?, key_active=1 WHERE id=?", (time.time() - 5, s100["id"]))
    c.commit()
    ctx.bot.send_message.reset_mock()
    await bot.lifecycle_job(ctx)
    sent = [(call.args[0], call.args[1]) for call in ctx.bot.send_message.await_args_list]
    assert any(uid == 400 and "закончится" in t for uid, t in sent)
    assert not any(uid == 300 and "закончится" in t for uid, t in sent), "автопродление без напоминания"
    assert any(uid == 100 and "закончился" in t for uid, t in sent)
    assert db.get_sub(s100["id"])["key_active"] == 0
    ctx.bot.send_message.reset_mock()
    await bot.lifecycle_job(ctx)
    assert ctx.bot.send_message.await_count == 0

    # 13b. пробный период: напоминание за несколько часов, после конца — скидка
    trial = next(x for x in db.user_subs(200) if x["trial"])
    c.execute("UPDATE subscriptions SET expires_at=?, reminded_for=0 WHERE id=?", (time.time() + 5 * 3600, trial["id"]))
    c.commit(); ctx.bot.send_message.reset_mock()
    await bot.lifecycle_job(ctx)
    assert ctx.bot.send_message.await_count == 0, "за 5 часов до конца пробного ещё рано"
    c.execute("UPDATE subscriptions SET expires_at=? WHERE id=?", (time.time() + 2 * 3600, trial["id"])); c.commit()
    await bot.lifecycle_job(ctx)
    sent = [call.args for call in ctx.bot.send_message.await_args_list]
    assert len(sent) == 1 and sent[0][0] == 200 and "Пробный доступ закончится через 2 часа" in sent[0][1]
    # гость без оплат: после конца пробного получает скидку на первую покупку
    await bot.start(make_update(600, "Новичок"), ctx)
    await press(600, "trial", ctx)
    t600 = db.user_subs(600)[0]
    c.execute("UPDATE subscriptions SET expires_at=? WHERE id=?", (time.time() - 5, t600["id"])); c.commit()
    ctx.bot.send_message.reset_mock()
    await bot.lifecycle_job(ctx)
    sent = [call.args for call in ctx.bot.send_message.await_args_list if call.args[0] == 600]
    assert sent and "Пробный период закончился" in sent[0][1] and "15%" in sent[0][1]
    assert db.get_offer(600)["percent"] == 15
    # скидка видна в тарифах, работает только на разовую оплату и тратится при оплате
    assert "−15%" in str([b.text for r in bot.main_kb(db.get_user(600)).inline_keyboard for b in r])
    full = config.plan_price("m1", 1); cut = bot.price(600, "m1", 1)
    assert cut == round(full * 0.85) and bot.price(600, "m1", 1, once=False) == full
    assert f"{cut} ⭐ вместо {full}" in bot.plans_text(uid=600)
    await press(600, "po:n:m1:1:0", ctx)
    kw = ctx.bot.send_invoice.await_args.kwargs
    assert kw["prices"][0].amount == cut and kw["payload"] == f"v2:b:m1:30:{cut}:1:0:-"
    assert await precheck(600, kw["payload"], cut, ctx)
    assert not await precheck(300, kw["payload"], cut, ctx), "чужая скидка не работает"
    await press(600, "pa:n:m1:1:0", ctx)
    assert ctx.bot.create_invoice_link.await_args.kwargs["prices"][0].amount == full, "автопродление без скидки"
    await pay(600, ctx, kw["payload"], cut, "OFF1")
    assert db.get_offer(600) is None and db.get_payment("OFF1")["full_price"] == full
    assert not await precheck(600, kw["payload"], cut, ctx), "после оплаты скидки нет"
    assert db.funnel()["offers_used"] == 1
    # возврат ушедших: через 3 дня скидка 20%, через 7 — 30%, каждая один раз
    for x in db.user_subs(600):
        c.execute("UPDATE subscriptions SET expires_at=?, key_active=0 WHERE id=?", (time.time() - 4 * DAY, x["id"]))
    c.commit(); ctx.bot.send_message.reset_mock()
    await bot.winback_job(ctx)
    sent = [call.args for call in ctx.bot.send_message.await_args_list if call.args[0] == 600]
    assert len(sent) == 1 and "20%" in sent[0][1] and db.get_offer(600)["percent"] == 20
    await bot.winback_job(ctx)
    assert len([c_ for c_ in ctx.bot.send_message.await_args_list if c_.args[0] == 600]) == 1, "один раз"
    for x in db.user_subs(600):
        c.execute("UPDATE subscriptions SET expires_at=? WHERE id=?", (time.time() - 8 * DAY, x["id"]))
    c.commit(); ctx.bot.send_message.reset_mock()
    await bot.winback_job(ctx)
    sent = [call.args for call in ctx.bot.send_message.await_args_list if call.args[0] == 600]
    assert len(sent) == 1 and "30%" in sent[0][1] and "Последнее" in sent[0][1]
    for x in db.user_subs(600):
        c.execute("UPDATE subscriptions SET expires_at=? WHERE id=?", (time.time() - 40 * DAY, x["id"]))
    c.commit(); db.use_offer(600)

    # 14. мини-приложение
    config.MINIAPP_URL = "https://example.github.io/app/"
    bot.STATE["username"] = "aurora_vpn_bot"
    url = bot.miniapp_url(db.get_user(200))
    enc = url.split("#d=")[1]; enc += "=" * (-len(enc) % 4)
    d = json.loads(base64.urlsafe_b64decode(enc))
    assert len(d["subs"]) == 2 and d["p"][0]["id"] == "m1" and d["bu"] == "aurora_vpn_bot"
    assert any(b.web_app for r in bot.main_kb(db.get_user(200)).inline_keyboard for b in r)
    await bot.start(make_update(200), ctx)
    assert ctx.bot.set_chat_menu_button.await_args.kwargs["chat_id"] == 200
    ctx.args = ["buy_m1"]; await bot.start(make_update(200), ctx); ctx.args = []
    config.MINIAPP_URL = ""

    # 15. режим настоящего VPN
    prov = make_provider(tempfile.mkdtemp())
    demo, bot.vpn = bot.vpn, prov
    app = MagicMock(); app.bot.get_me = AsyncMock(return_value=MagicMock(username="aurora_vpn_bot"))
    for m in ["set_my_commands", "set_my_short_description", "set_my_description", "set_my_name"]:
        setattr(app.bot, m, AsyncMock())
    app.bot.get_my_name = AsyncMock(return_value=MagicMock(name="x"))
    app.bot.send_message = AsyncMock()
    await bot.setup_profile(app)
    await prov.on_problem("Xray отклонил конфиг <тест>")
    assert app.bot.send_message.await_args.args[0] == 1
    check_caption(app.bot.send_message.await_args.args[1])
    st_text = await bot.server_text(); check_caption(st_text)
    assert "VPN (порт 443)" in st_text and "Подписки (порт" in st_text and "Стран: 1" in st_text
    prov.last_error = "Xray отклонил конфиг <тест>"
    st_text = await bot.server_text(); check_caption(st_text); assert "Последняя ошибка" in st_text
    prov.last_error = ""
    ctx.bot.send_document.reset_mock()
    await bot.backup(make_update(1), ctx)
    names = [c.kwargs["filename"] for c in ctx.bot.send_document.await_args_list]
    assert len(names) == 2 and names[1].endswith("-vpn.json")
    active = db.all_active_subs()
    assert set(prov.state["users"]) == {str(k) for k in active}
    some = next(iter(active)); assert db.get_sub(some)["vpn_key"] == prov.sub_url(some)
    u = make_update(1, text="/addloc nl 🇳🇱 Нидерланды | socks5://u:p@1.2.3.4:1080")
    await bot.addloc(u, ctx); assert len(prov.locations) == 2
    assert "Страны:" in bot.main_text(db.get_user(200))
    assert "другую страну" in bot.fix_text() and "Обход" not in bot.fix_text()
    u = make_update(1, text="/addbridge ru1 🇷🇺 Обход | 198.51.100.9"); await bot.addbridge(u, ctx)
    assert "Мост добавлен" in u.message.reply_text.await_args.args[0] and len(prov.bridges) == 1
    check_caption(bot.locations_text())
    check_caption(bot.fix_text()); assert "🇷🇺 Обход" in bot.fix_text()
    u = make_update(1, text="/addbridge сломано"); await bot.addbridge(u, ctx)
    assert "Формат" in u.message.reply_text.await_args.args[0]
    u = make_update(200, text="/addbridge ru2 x | 1.1.1.1"); await bot.addbridge(u, ctx)
    assert len(prov.bridges) == 1, "не админ не добавляет мосты"
    ctx.args = ["ru1"]; await bot.delbridge(make_update(1), ctx); ctx.args = []
    assert not prov.bridges
    # ключи без подписки: на случай, если оператор режет порт раздачи
    owner = db.get_sub(some)["user_id"]
    ctx.bot.send_message.reset_mock()
    await press(owner, f"raw:{some}", ctx)
    sent = "\n".join(c.args[1] for c in ctx.bot.send_message.await_args_list)
    assert "без подписки" in sent and sent.count("vless://") == len(prov.links(some)) and "· запасной" in sent
    u = await press(300, f"raw:{some}", ctx); assert alerted(u), "чужие ключи не выдаются"
    assert "запасной" in bot.fix_text() and "Ключи без подписки" in bot.fix_text()
    # мост для белых списков: бот сам подбирает российский сайт маскировки
    real_pick = bot.pick_bridge_site
    bot.pick_bridge_site = AsyncMock(return_value="vk.com")
    ctx.application.create_task = lambda coro: asyncio.ensure_future(coro)
    u = make_update(1, text="/addbridge ru3 🇷🇺 Белые списки | 198.51.100.30 | ru"); await bot.addbridge(u, ctx)
    assert "Подбираю" in u.message.reply_text.await_args.args[0]
    await asyncio.sleep(0.1)
    assert prov.bridge_site == "vk.com" and prov.bridges[0]["ru"]
    assert any("vk.com" in c.args[1] for c in ctx.bot.send_message.await_args_list)
    assert any("198.51.100.30" in l and "sni=vk.com" in l for l in prov.links(some))
    check_caption(bot.locations_text()); assert "белые списки" in bot.locations_text()
    ctx.args = []; u = make_update(1); await bot.bridgesite_cmd(u, ctx)
    assert "vk.com" in u.message.reply_text.await_args.args[0]
    bot.pick_bridge_site = real_pick
    ctx.args = ["ru3"]; await bot.delbridge(make_update(1), ctx); ctx.args = []
    st_text = await bot.server_text(); check_caption(st_text); assert "без перезапуска" in st_text
    # режим без Xray: в подписке и на экранах только Hysteria
    prov.xray_enabled = False
    prov.hy2 = {"port": 443, "sni": "www.nvidia.com", "pin": "", "obfs": "", "stats_ports": []}
    prov.sub_domain = "sub.example.com"
    st_text = await bot.server_text(); check_caption(st_text)
    assert "Xray выключен" in st_text and "HTTPS" in st_text and "Перезапусков" not in st_text
    assert "Xray выключен" in bot.locations_text() and len(bot.location_names()) == 1
    assert all(l.startswith("hysteria2://") for l in prov.links(some)) and "Hysteria" in bot.fix_text()
    assert "запасной" not in bot.fix_text()
    prov.xray_enabled, prov.hy2, prov.sub_domain = True, None, ""
    ctx.bot.send_message.reset_mock()
    prov.add_location("dead", "🇺🇸 США", "socks5://u:p@127.0.0.1:1")
    prov.check_proxies = AsyncMock(return_value=[(prov.locations[-1], False)])  # сама проверка покрыта в tests/
    await bot.proxy_health_job(ctx)
    assert any("не отвечает" in c.args[1] for c in ctx.bot.send_message.await_args_list)
    # трафик и лимит устройств
    some_sub = db.get_sub(some)
    prov.traffic = AsyncMock(return_value={some: (3 * 2**30, 2**29)})
    await bot.traffic_job(ctx)
    assert db.sub_traffic(some) == (3 * 2**30, 2**29) and "Трафик: 3.5 ГБ" in bot.sub_text(db.get_sub(some))
    check_caption(bot.traffic_text()); assert "3.5 ГБ" in bot.traffic_text()
    prov.online = AsyncMock(return_value={some: some_sub["devices"] + 2})
    prov.suspend, prov.resume = AsyncMock(), AsyncMock()
    ctx.bot.send_message.reset_mock()
    for _ in range(5):
        await bot.devices_job(ctx)
    texts = [(c.args[0], c.args[1]) for c in ctx.bot.send_message.await_args_list]
    owner = some_sub["user_id"]
    assert sum(1 for u_, t in texts if u_ == owner and "⚠️" in t) == 1, texts
    assert any(u_ == owner and "отключена на" in t for u_, t in texts)
    assert any(u_ == 1 and "Превышение устройств" in t for u_, t in texts)
    prov.suspend.assert_awaited_once_with(some, bot.guard.block_seconds)
    bot.guard.blocked[some] = time.time() - 1
    await bot.devices_job(ctx)
    prov.resume.assert_awaited_once_with(some)
    bot.guard.__init__("block")
    # JSON-конфиги для Happ включаются и выключаются в /admin
    assert prov.json_sub and any("JSON-конфиги" in b.text for r in bot.admin_kb().inline_keyboard for b in r)
    await press(1, "adm:json", ctx); assert not prov.json_sub
    await press(owner, "adm:json", ctx); assert not prov.json_sub, "не админ не переключает"
    await press(1, "adm:json", ctx); assert prov.json_sub
    # сайт Hysteria меняется по расписанию, сообщение только админам
    prov.hy2 = {"port": 443, "sni": "www.example.com", "pin": "", "obfs": "", "obfs_port": 0,
                "stats_ports": [], "stats_secret": "s"}
    prov.xray_enabled = False
    saved_rot, saved_rank = prov.hy2_sni_rotatable, bot.masking.ranked
    prov.hy2_sni_rotatable = lambda: True
    bot.masking.ranked = AsyncMock(return_value=[("www.wp.pl", 50.0)])
    try:
        ctx.bot.send_message.reset_mock()
        await bot.hy2_sni_job(ctx.bot)          # первый запуск: только начало отсчёта
        assert ctx.bot.send_message.await_count == 0 and prov.state["hy2_sni_changed"]
        prov.state["hy2_sni_changed"] = time.time() - 25 * 3600
        await bot.hy2_sni_job(ctx.bot)
        assert prov.hy2_sni == "www.wp.pl"
        to = [c.args[0] for c in ctx.bot.send_message.await_args_list]
        assert to and set(to) == config.ADMIN_IDS, "гостям ничего не уходит, только админам"
        check_caption(ctx.bot.send_message.await_args.args[1])
        u = make_update(1); ctx.args = []; await bot.sni_cmd(u, ctx)
        assert "Hysteria" in u.message.reply_text.await_args.args[0] and "www.wp.pl" in u.message.reply_text.await_args.args[0]
        check_caption(u.message.reply_text.await_args.args[0])
    finally:
        prov.hy2_sni_rotatable, bot.masking.ranked = saved_rot, saved_rank
        prov.hy2, prov.xray_enabled = None, True
    # купленные прокси списком: ссылка хранится на сервере, сообщение с ней удаляется
    import webshare as ws
    saved = ws.fetch, ws.scan, bot.public_proxies.direct_ok
    ws.fetch = AsyncMock(return_value=["socks5://u:p@1.1.1.1:1", "socks5://u:p@2.2.2.2:1", "socks5://u:p@3.3.3.3:1"])
    ws.scan = AsyncMock(return_value=[("socks5://u:p@1.1.1.1:1", "de", 80), ("socks5://u:p@3.3.3.3:1", "fi", 120),
                                      ("socks5://u:p@2.2.2.2:1", "de", 200)])
    bot.public_proxies.direct_ok = AsyncMock(return_value=True)
    try:
        report = await bot.webshare_refresh()
        assert "Ссылка на список не задана" in report
        u = make_update(1, text="/webshare https://proxy.webshare.io/api/v2/proxy/list/download/SECRET/")
        u.message.delete = AsyncMock()
        ctx.args = ["https://proxy.webshare.io/api/v2/proxy/list/download/SECRET/"]
        tasks = []
        ctx.application.create_task = lambda coro: tasks.append(asyncio.get_running_loop().create_task(coro))
        await bot.webshare_cmd(u, ctx)
        await asyncio.gather(*tasks)
        u.message.delete.assert_awaited()
        assert prov.state["webshare"]["url"].endswith("SECRET/")
        report = await bot.webshare_refresh()
        check_caption(report)
        assert "SECRET" not in report and "стран 2" in report
        de = next(l for l in prov.locations if l["code"] == "de")
        assert de["src"] == "webshare" and de["pool"] == ["socks5://u:p@1.1.1.1:1", "socks5://u:p@2.2.2.2:1"]
        ws.scan = AsyncMock(return_value=[("socks5://u:p@1.1.1.1:1", "de", 90)])
        report = await bot.webshare_refresh()
        assert "Убраны" in report and not any(l["code"] == "fi" for l in prov.locations)
        ctx.args = []
        u = make_update(1); await bot.webshare_cmd(u, ctx)
        assert "Германия" in u.message.reply_text.await_args.args[0]
        # список вставлен прямо в сообщение
        u = make_update(1, text="/webshare\np.webshare.io:80:user-1:pw\np.webshare.io:80:user-2:pw")
        u.message.delete = AsyncMock(); ctx.args = ["p.webshare.io:80:user-1:pw", "p.webshare.io:80:user-2:pw"]
        tasks.clear(); await bot.webshare_cmd(u, ctx); await asyncio.gather(*tasks)
        u.message.delete.assert_awaited()
        assert prov.state["webshare"]["list"] == ["socks5://user-1:pw@p.webshare.io:80", "socks5://user-2:pw@p.webshare.io:80"]
        assert "url" not in prov.state["webshare"]
        ws.fetch.reset_mock(); await bot.webshare_refresh(); ws.fetch.assert_not_awaited()
        ctx.args = ["off"]; u = make_update(1); await bot.webshare_cmd(u, ctx); ctx.args = []
        assert not prov.paid_locations() and prov.state["webshare"] == {}
    finally:
        ws.fetch, ws.scan, bot.public_proxies.direct_ok = saved
        ctx.args = []
    prov._server.close()
    bot.vpn = demo

    app = bot.build_app("123:abc")
    assert len(captions) > 90, "экраны должны были провериться"


class BotFlows(unittest.IsolatedAsyncioTestCase):
    async def test_all_flows(self):
        await main()


if __name__ == "__main__":
    unittest.main()
