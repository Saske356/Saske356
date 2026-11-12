"""Хранилище бота на SQLite: гости, подписки, платежи, промокоды, подарки, тикеты,
персональные скидки и трафик."""

import secrets
import sqlite3
import time

DAY = 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    joined_at      REAL NOT NULL,
    referrer_id    INTEGER,
    trial_used     INTEGER NOT NULL DEFAULT 0,
    paid_stars     INTEGER NOT NULL DEFAULT 0,
    channel_bonus  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    name            TEXT NOT NULL,
    devices         INTEGER NOT NULL DEFAULT 1,
    expires_at      REAL NOT NULL DEFAULT 0,
    vpn_key         TEXT,
    key_active      INTEGER NOT NULL DEFAULT 0,
    reminded_for    REAL NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    auto_token      TEXT UNIQUE,
    auto_charge_id  TEXT,
    auto_active     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS subs_user ON subscriptions(user_id);
CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    plan        TEXT NOT NULL,
    stars       INTEGER NOT NULL,
    days        INTEGER NOT NULL,
    charge_id   TEXT UNIQUE,
    created_at  REAL NOT NULL,
    refunded    INTEGER NOT NULL DEFAULT 0,
    kind        TEXT NOT NULL DEFAULT 'buy',
    sub_id      INTEGER,
    devices     INTEGER NOT NULL DEFAULT 1,
    gift_code   TEXT
);
CREATE TABLE IF NOT EXISTS promos (
    code       TEXT PRIMARY KEY,
    days       INTEGER NOT NULL,
    uses_left  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS promo_uses (
    code     TEXT NOT NULL,
    user_id  INTEGER NOT NULL,
    PRIMARY KEY (code, user_id)
);
CREATE TABLE IF NOT EXISTS gifts (
    code         TEXT PRIMARY KEY,
    buyer_id     INTEGER NOT NULL,
    days         INTEGER NOT NULL,
    devices      INTEGER NOT NULL,
    created_at   REAL NOT NULL,
    redeemed_by  INTEGER,
    sub_id       INTEGER,
    void         INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tickets (
    admin_chat  INTEGER NOT NULL,
    admin_msg   INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    created_at  REAL NOT NULL,
    PRIMARY KEY (admin_chat, admin_msg)
);
CREATE TABLE IF NOT EXISTS offers (
    user_id     INTEGER PRIMARY KEY,
    percent     INTEGER NOT NULL,
    until       REAL NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS winback (
    user_id   INTEGER PRIMARY KEY,
    for_exp   REAL NOT NULL,
    stage     INTEGER NOT NULL DEFAULT 0
);
"""

# Колонки, добавленные после первых версий: в старой базе они появляются при запуске.
MIGRATIONS = {
    "subscriptions": [("trial", "INTEGER NOT NULL DEFAULT 0"),
                      ("up_bytes", "INTEGER NOT NULL DEFAULT 0"),
                      ("down_bytes", "INTEGER NOT NULL DEFAULT 0")],
    "payments": [("full_price", "INTEGER")],
}


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        self.conn.commit()

    def q1(self, sql: str, *args):
        return self.conn.execute(sql, args).fetchone()

    def qa(self, sql: str, *args) -> list[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchall()

    def run(self, sql: str, *args) -> int:
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur.lastrowid

    # ---------- гости ----------

    def touch_user(self, user_id: int, username: str | None, first_name: str | None,
                   referrer_id: int | None = None) -> tuple[sqlite3.Row, bool]:
        """Создаёт гостя, если его нет. Возвращает (строка, новый_ли)."""
        if self.get_user(user_id):
            self.run("UPDATE users SET username=?, first_name=? WHERE id=?", username, first_name, user_id)
            return self.get_user(user_id), False
        if referrer_id == user_id or (referrer_id and not self.get_user(referrer_id)):
            referrer_id = None
        self.run("INSERT INTO users (id, username, first_name, joined_at, referrer_id) VALUES (?,?,?,?,?)",
                 user_id, username, first_name, time.time(), referrer_id)
        return self.get_user(user_id), True

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM users WHERE id=?", user_id)

    def find_user(self, query: str) -> sqlite3.Row | None:
        """Ищет по ID или @username."""
        q = query.strip().lstrip("@")
        if q.isdigit():
            return self.get_user(int(q))
        return self.q1("SELECT * FROM users WHERE lower(username)=lower(?)", q)

    def mark_trial(self, user_id: int) -> None:
        self.run("UPDATE users SET trial_used=1 WHERE id=?", user_id)

    def mark_channel_bonus(self, user_id: int) -> None:
        self.run("UPDATE users SET channel_bonus=1 WHERE id=?", user_id)

    def referral_count(self, user_id: int) -> int:
        return self.q1("SELECT COUNT(*) FROM users WHERE referrer_id=?", user_id)[0]

    def all_user_ids(self) -> list[int]:
        return [r[0] for r in self.qa("SELECT id FROM users")]

    # ---------- подписки ----------

    def create_sub(self, user_id: int, devices: int = 1, name: str | None = None,
                   trial: bool = False) -> sqlite3.Row:
        n = self.q1("SELECT COUNT(*) FROM subscriptions WHERE user_id=?", user_id)[0] + 1
        sid = self.run("INSERT INTO subscriptions (user_id, name, devices, created_at, trial) VALUES (?,?,?,?,?)",
                       user_id, name or f"Ключ {n}", devices, time.time(), int(trial))
        return self.get_sub(sid)

    def get_sub(self, sub_id: int) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM subscriptions WHERE id=?", sub_id)

    def user_subs(self, user_id: int) -> list[sqlite3.Row]:
        return self.qa("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id", user_id)

    def active_subs(self, user_id: int) -> list[sqlite3.Row]:
        return self.qa("SELECT * FROM subscriptions WHERE user_id=? AND expires_at>? ORDER BY expires_at DESC",
                       user_id, time.time())

    def primary_sub(self, user_id: int) -> sqlite3.Row | None:
        """Куда начислять бонусные дни: активная с самым долгим сроком, иначе последняя."""
        act = self.active_subs(user_id)
        if act:
            return act[0]
        subs = self.user_subs(user_id)
        return subs[-1] if subs else None

    def extend_sub(self, sub_id: int, days: float) -> sqlite3.Row:
        """Продлевает от текущей даты окончания (или от сейчас, если истекла)."""
        sub = self.get_sub(sub_id)
        start = max(time.time(), sub["expires_at"])
        self.run("UPDATE subscriptions SET expires_at=? WHERE id=?", start + days * DAY, sub_id)
        return self.get_sub(sub_id)

    def rename_sub(self, sub_id: int, name: str) -> None:
        self.run("UPDATE subscriptions SET name=? WHERE id=?", name, sub_id)

    def set_key(self, sub_id: int, key: str | None, active: bool) -> None:
        self.run("UPDATE subscriptions SET vpn_key=?, key_active=? WHERE id=?", key, int(active), sub_id)

    def set_auto(self, sub_id: int, token: str | None, charge_id: str | None, active: bool) -> None:
        self.run("UPDATE subscriptions SET auto_token=?, auto_charge_id=?, auto_active=? WHERE id=?",
                 token, charge_id, int(active), sub_id)

    def sub_by_token(self, token: str) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM subscriptions WHERE auto_token=?", token)

    def all_active_subs(self) -> dict[int, float]:
        return {r[0]: r[1] for r in self.qa("SELECT id, expires_at FROM subscriptions WHERE expires_at>?",
                                            time.time())}

    def active_user_ids(self) -> list[int]:
        return [r[0] for r in self.qa("SELECT DISTINCT user_id FROM subscriptions WHERE expires_at>?", time.time())]

    def active_devices(self) -> dict[int, int]:
        return {r[0]: r[1] for r in self.qa("SELECT id, devices FROM subscriptions WHERE expires_at>?",
                                            time.time())}

    # ---------- трафик ----------

    def add_traffic(self, deltas: dict[int, tuple[int, int]]) -> None:
        for sid, (up, down) in deltas.items():
            self.conn.execute("UPDATE subscriptions SET up_bytes = up_bytes + ?, down_bytes = down_bytes + ? "
                              "WHERE id=?", (int(up), int(down), sid))
        self.conn.commit()

    def sub_traffic(self, sub_id: int) -> tuple[int, int]:
        r = self.q1("SELECT up_bytes, down_bytes FROM subscriptions WHERE id=?", sub_id)
        return (r[0], r[1]) if r else (0, 0)

    def top_traffic(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.qa("SELECT s.*, u.username, u.first_name FROM subscriptions s "
                       "LEFT JOIN users u ON u.id = s.user_id WHERE s.expires_at > ? "
                       "ORDER BY s.up_bytes + s.down_bytes DESC LIMIT ?", time.time(), limit)

    def total_traffic(self) -> int:
        return self.q1("SELECT COALESCE(SUM(up_bytes + down_bytes), 0) FROM subscriptions")[0]

    def expiring_soon(self, within: float) -> list[sqlite3.Row]:
        now = time.time()
        return self.qa("SELECT * FROM subscriptions WHERE expires_at>? AND expires_at<=? "
                       "AND reminded_for != expires_at", now, now + within)

    def mark_reminded(self, sub_id: int, expires_at: float) -> None:
        self.run("UPDATE subscriptions SET reminded_for=? WHERE id=?", expires_at, sub_id)

    def expired_with_key(self) -> list[sqlite3.Row]:
        return self.qa("SELECT * FROM subscriptions WHERE key_active=1 AND expires_at<=?", time.time())

    # ---------- платежи ----------

    def add_payment(self, user_id: int, plan: str, stars: int, days: int, charge_id: str,
                    kind: str = "buy", sub_id: int | None = None, devices: int = 1,
                    gift_code: str | None = None, full_price: int | None = None) -> bool:
        """Записывает платёж. False, если такой charge_id уже был (повтор от Telegram).
        full_price — цена без скидки, если оплата шла по персональному предложению."""
        try:
            self.conn.execute(
                "INSERT INTO payments (user_id, plan, stars, days, charge_id, created_at, kind, sub_id, "
                "devices, gift_code, full_price) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (user_id, plan, stars, days, charge_id, time.time(), kind, sub_id, devices, gift_code,
                 full_price))
        except sqlite3.IntegrityError:
            return False
        self.conn.execute("UPDATE users SET paid_stars = paid_stars + ? WHERE id=?", (stars, user_id))
        self.conn.commit()
        return True

    def payment_seen(self, charge_id: str) -> bool:
        return self.q1("SELECT 1 FROM payments WHERE charge_id=?", charge_id) is not None

    def set_payment_target(self, charge_id: str, sub_id: int | None, gift_code: str | None = None) -> None:
        self.run("UPDATE payments SET sub_id=?, gift_code=? WHERE charge_id=?", sub_id, gift_code, charge_id)

    def payments_count(self, user_id: int) -> int:
        return self.q1("SELECT COUNT(*) FROM payments WHERE user_id=? AND refunded=0", user_id)[0]

    def get_payment(self, charge_id: str) -> sqlite3.Row | None:
        return self.q1("SELECT p.*, u.username, u.first_name FROM payments p "
                       "LEFT JOIN users u ON u.id = p.user_id WHERE p.charge_id=?", charge_id)

    def get_payment_by_id(self, pid: int) -> sqlite3.Row | None:
        return self.q1("SELECT p.*, u.username, u.first_name FROM payments p "
                       "LEFT JOIN users u ON u.id = p.user_id WHERE p.id=?", pid)

    def list_payments(self, user_id: int | None = None, limit: int = 10) -> list[sqlite3.Row]:
        sql = "SELECT p.*, u.username, u.first_name FROM payments p LEFT JOIN users u ON u.id = p.user_id"
        if user_id is not None:
            return self.qa(sql + " WHERE p.user_id=? ORDER BY p.id DESC LIMIT ?", user_id, limit)
        return self.qa(sql + " ORDER BY p.id DESC LIMIT ?", limit)

    def mark_refunded(self, charge_id: str) -> sqlite3.Row | None:
        """Помечает возврат и снимает оплаченные дни. Возвращает затронутую подписку."""
        p = self.get_payment(charge_id)
        if not p or p["refunded"]:
            return None
        self.conn.execute("UPDATE payments SET refunded=1 WHERE charge_id=?", (charge_id,))
        self.conn.execute("UPDATE users SET paid_stars = MAX(0, paid_stars - ?) WHERE id=?",
                          (p["stars"], p["user_id"]))
        sub_id = p["sub_id"]
        if p["gift_code"]:
            g = self.get_gift(p["gift_code"])
            self.conn.execute("UPDATE gifts SET void=1 WHERE code=?", (p["gift_code"],))
            sub_id = g["sub_id"] if g else None
        if sub_id:
            self.conn.execute("UPDATE subscriptions SET expires_at = MAX(?, expires_at - ?) WHERE id=?",
                              (time.time(), p["days"] * DAY, sub_id))
        self.conn.commit()
        return self.get_sub(sub_id) if sub_id else None

    # ---------- промокоды и подарки ----------

    def add_promo(self, code: str, days: int, uses: int) -> None:
        self.run("INSERT OR REPLACE INTO promos (code, days, uses_left) VALUES (?,?,?)", code.upper(), days, uses)

    def redeem_promo(self, code: str, user_id: int) -> tuple[str, int]:
        """Возвращает (статус, дней): ok | not_found | used_up | already."""
        code = code.strip().upper()
        promo = self.q1("SELECT * FROM promos WHERE code=?", code)
        if not promo:
            return "not_found", 0
        if self.q1("SELECT 1 FROM promo_uses WHERE code=? AND user_id=?", code, user_id):
            return "already", 0
        if promo["uses_left"] <= 0:
            return "used_up", 0
        self.conn.execute("INSERT INTO promo_uses (code, user_id) VALUES (?,?)", (code, user_id))
        self.conn.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code=?", (code,))
        self.conn.commit()
        return "ok", promo["days"]

    def create_gift(self, buyer_id: int, days: int, devices: int) -> str:
        while True:
            code = "GIFT-" + secrets.token_hex(4).upper()
            if not self.get_gift(code):
                break
        self.run("INSERT INTO gifts (code, buyer_id, days, devices, created_at) VALUES (?,?,?,?,?)",
                 code, buyer_id, days, devices, time.time())
        return code

    def get_gift(self, code: str) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM gifts WHERE code=?", code.strip().upper())

    def redeem_gift(self, code: str, user_id: int) -> tuple[str, sqlite3.Row | None]:
        """ok | not_found | used | void. При ok создаётся новая подписка."""
        g = self.get_gift(code)
        if not g:
            return "not_found", None
        if g["void"]:
            return "void", None
        if g["redeemed_by"]:
            return "used", None
        sub = self.create_sub(user_id, g["devices"])
        sub = self.extend_sub(sub["id"], g["days"])
        self.run("UPDATE gifts SET redeemed_by=?, sub_id=? WHERE code=?", user_id, sub["id"], g["code"])
        return "ok", sub

    # ---------- тикеты поддержки ----------

    def add_ticket(self, admin_chat: int, admin_msg: int, user_id: int) -> None:
        self.run("INSERT OR REPLACE INTO tickets (admin_chat, admin_msg, user_id, created_at) VALUES (?,?,?,?)",
                 admin_chat, admin_msg, user_id, time.time())

    def ticket_user(self, admin_chat: int, admin_msg: int) -> int | None:
        r = self.q1("SELECT user_id FROM tickets WHERE admin_chat=? AND admin_msg=?", admin_chat, admin_msg)
        return r[0] if r else None

    # ---------- персональные скидки и возврат ушедших ----------

    def set_offer(self, user_id: int, percent: int, hours: float, reason: str = "") -> None:
        """Скидка на разовую оплату. Новое предложение заменяет прежнее, только если оно щедрее
        или прежнее уже истекло."""
        now = time.time()
        cur = self.get_offer(user_id)
        if cur and cur["percent"] >= percent:
            return
        self.run("INSERT OR REPLACE INTO offers (user_id, percent, until, reason, created_at) VALUES (?,?,?,?,?)",
                 user_id, int(percent), now + hours * 3600, reason, now)

    def get_offer(self, user_id: int) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM offers WHERE user_id=? AND until>?", user_id, time.time())

    def use_offer(self, user_id: int) -> None:
        self.run("DELETE FROM offers WHERE user_id=?", user_id)

    def winback_due(self, after_days: float, max_days: float, stage: int) -> list[sqlite3.Row]:
        """Гости, у которых все подписки закончились от after_days до max_days дней назад
        и которым ещё не отправлялось предложение этого этапа за эту дату окончания."""
        now = time.time()
        return self.qa(
            "SELECT s.user_id, MAX(s.expires_at) AS last_exp FROM subscriptions s "
            "GROUP BY s.user_id HAVING last_exp <= ? AND last_exp > ? AND s.user_id NOT IN "
            "(SELECT user_id FROM winback w WHERE w.for_exp = last_exp AND w.stage >= ?)",
            now - after_days * DAY, now - max_days * DAY, stage)

    def mark_winback(self, user_id: int, for_exp: float, stage: int) -> None:
        self.run("INSERT OR REPLACE INTO winback (user_id, for_exp, stage) VALUES (?,?,?)",
                 user_id, for_exp, stage)

    # ---------- статистика ----------

    def funnel(self, since: float = 0) -> dict:
        """Воронка: запустили бота → взяли пробный → оплатили → продлили. since — только новые гости."""
        one = lambda sql, *a: self.q1(sql, *a)[0]
        paid = ("SELECT DISTINCT user_id FROM payments WHERE refunded=0 AND plan != 'test'")
        return {
            "users": one("SELECT COUNT(*) FROM users WHERE joined_at >= ?", since),
            "trial": one("SELECT COUNT(*) FROM users WHERE trial_used=1 AND joined_at >= ?", since),
            "paid": one(f"SELECT COUNT(*) FROM users WHERE joined_at >= ? AND id IN ({paid})", since),
            "trial_paid": one(f"SELECT COUNT(*) FROM users WHERE trial_used=1 AND joined_at >= ? "
                              f"AND id IN ({paid})", since),
            "repeat": one("SELECT COUNT(*) FROM users WHERE joined_at >= ? AND id IN (SELECT user_id FROM payments "
                          "WHERE refunded=0 AND plan != 'test' GROUP BY user_id HAVING COUNT(*) >= 2)", since),
            "offers_used": one("SELECT COUNT(*) FROM payments p JOIN users u ON u.id = p.user_id "
                               "WHERE p.refunded=0 AND p.full_price IS NOT NULL AND u.joined_at >= ?", since),
        }

    def stats(self) -> dict:
        now = time.time()
        one = lambda sql, *a: self.q1(sql, *a)[0]
        return {
            "users": one("SELECT COUNT(*) FROM users"),
            "new_today": one("SELECT COUNT(*) FROM users WHERE joined_at > ?", now - DAY),
            "active": one("SELECT COUNT(DISTINCT user_id) FROM subscriptions WHERE expires_at > ?", now),
            "subs": one("SELECT COUNT(*) FROM subscriptions WHERE expires_at > ?", now),
            "auto": one("SELECT COUNT(*) FROM subscriptions WHERE auto_active=1 AND expires_at > ?", now),
            "trials": one("SELECT COUNT(*) FROM users WHERE trial_used=1"),
            "payments": one("SELECT COUNT(*) FROM payments WHERE refunded=0"),
            "stars": one("SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0"),
            "stars_today": one("SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0 AND created_at > ?",
                               now - DAY),
        }
