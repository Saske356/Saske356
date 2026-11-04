"""Хранилище бота на SQLite: пользователи, подписки, платежи, промокоды."""

import sqlite3
import time

DAY = 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    joined_at     REAL NOT NULL,
    referrer_id   INTEGER,
    expires_at    REAL NOT NULL DEFAULT 0,
    trial_used    INTEGER NOT NULL DEFAULT 0,
    paid_stars    INTEGER NOT NULL DEFAULT 0,
    vpn_key       TEXT,
    key_active    INTEGER NOT NULL DEFAULT 0,
    reminded_for  REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    plan        TEXT NOT NULL,
    stars       INTEGER NOT NULL,
    days        INTEGER NOT NULL,
    charge_id   TEXT UNIQUE,
    created_at  REAL NOT NULL,
    refunded    INTEGER NOT NULL DEFAULT 0
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
"""


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- пользователи ----------

    def touch_user(self, user_id: int, username: str | None, first_name: str | None,
                   referrer_id: int | None = None) -> tuple[sqlite3.Row, bool]:
        """Создаёт пользователя, если его нет. Возвращает (строка, новый_ли)."""
        row = self.get_user(user_id)
        if row:
            self.conn.execute("UPDATE users SET username=?, first_name=? WHERE id=?",
                              (username, first_name, user_id))
            self.conn.commit()
            return self.get_user(user_id), False
        if referrer_id == user_id or (referrer_id and not self.get_user(referrer_id)):
            referrer_id = None
        self.conn.execute(
            "INSERT INTO users (id, username, first_name, joined_at, referrer_id) VALUES (?,?,?,?,?)",
            (user_id, username, first_name, time.time(), referrer_id))
        self.conn.commit()
        return self.get_user(user_id), True

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def extend(self, user_id: int, days: int) -> float:
        """Продлевает подписку от текущей даты окончания (или от сейчас, если истекла)."""
        row = self.get_user(user_id)
        start = max(time.time(), row["expires_at"] if row else 0)
        new_exp = start + days * DAY
        self.conn.execute("UPDATE users SET expires_at=? WHERE id=?", (new_exp, user_id))
        self.conn.commit()
        return new_exp

    def mark_trial(self, user_id: int) -> None:
        self.conn.execute("UPDATE users SET trial_used=1 WHERE id=?", (user_id,))
        self.conn.commit()

    def set_key(self, user_id: int, key: str | None, active: bool) -> None:
        self.conn.execute("UPDATE users SET vpn_key=?, key_active=? WHERE id=?",
                          (key, int(active), user_id))
        self.conn.commit()

    def referral_count(self, user_id: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?",
                                 (user_id,)).fetchone()[0]

    def all_user_ids(self) -> list[int]:
        return [r[0] for r in self.conn.execute("SELECT id FROM users")]

    def expiring_soon(self, within: float) -> list[sqlite3.Row]:
        now = time.time()
        return self.conn.execute(
            "SELECT * FROM users WHERE expires_at > ? AND expires_at <= ? AND reminded_for != expires_at",
            (now, now + within)).fetchall()

    def mark_reminded(self, user_id: int, expires_at: float) -> None:
        self.conn.execute("UPDATE users SET reminded_for=? WHERE id=?", (expires_at, user_id))
        self.conn.commit()

    def expired_with_key(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM users WHERE key_active=1 AND expires_at <= ?", (time.time(),)).fetchall()

    # ---------- платежи ----------

    def add_payment(self, user_id: int, plan: str, stars: int, days: int, charge_id: str) -> bool:
        """Записывает платёж. False, если такой charge_id уже был (повтор от Telegram)."""
        try:
            self.conn.execute(
                "INSERT INTO payments (user_id, plan, stars, days, charge_id, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, plan, stars, days, charge_id, time.time()))
        except sqlite3.IntegrityError:
            return False
        self.conn.execute("UPDATE users SET paid_stars = paid_stars + ? WHERE id=?", (stars, user_id))
        self.conn.commit()
        return True

    def payments_count(self, user_id: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM payments WHERE user_id=? AND refunded=0",
                                 (user_id,)).fetchone()[0]

    def get_payment(self, charge_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM payments WHERE charge_id=?", (charge_id,)).fetchone()

    def mark_refunded(self, charge_id: str) -> None:
        p = self.get_payment(charge_id)
        if not p or p["refunded"]:
            return
        self.conn.execute("UPDATE payments SET refunded=1 WHERE charge_id=?", (charge_id,))
        self.conn.execute("UPDATE users SET paid_stars = MAX(0, paid_stars - ?), "
                          "expires_at = MAX(?, expires_at - ?) WHERE id=?",
                          (p["stars"], time.time(), p["days"] * DAY, p["user_id"]))
        self.conn.commit()

    # ---------- промокоды ----------

    def add_promo(self, code: str, days: int, uses: int) -> None:
        self.conn.execute("INSERT OR REPLACE INTO promos (code, days, uses_left) VALUES (?,?,?)",
                          (code.upper(), days, uses))
        self.conn.commit()

    def redeem_promo(self, code: str, user_id: int) -> tuple[str, int]:
        """Возвращает (статус, дней): ok | not_found | used_up | already."""
        code = code.strip().upper()
        promo = self.conn.execute("SELECT * FROM promos WHERE code=?", (code,)).fetchone()
        if not promo:
            return "not_found", 0
        if self.conn.execute("SELECT 1 FROM promo_uses WHERE code=? AND user_id=?",
                             (code, user_id)).fetchone():
            return "already", 0
        if promo["uses_left"] <= 0:
            return "used_up", 0
        try:
            self.conn.execute("INSERT INTO promo_uses (code, user_id) VALUES (?,?)", (code, user_id))
        except sqlite3.IntegrityError:
            return "already", 0
        self.conn.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code=?", (code,))
        self.conn.commit()
        return "ok", promo["days"]

    # ---------- статистика ----------

    def stats(self) -> dict:
        now = time.time()
        q = lambda sql, *a: self.conn.execute(sql, a).fetchone()[0]
        return {
            "users": q("SELECT COUNT(*) FROM users"),
            "new_today": q("SELECT COUNT(*) FROM users WHERE joined_at > ?", now - DAY),
            "active": q("SELECT COUNT(*) FROM users WHERE expires_at > ?", now),
            "trials": q("SELECT COUNT(*) FROM users WHERE trial_used=1"),
            "payments": q("SELECT COUNT(*) FROM payments WHERE refunded=0"),
            "stars": q("SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0"),
            "stars_today": q("SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0 AND created_at > ?",
                             now - DAY),
        }
