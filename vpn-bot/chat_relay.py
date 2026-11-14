"""Ретранслятор зашифрованного чата для приложения Arise.

Сервер хранит только шифр: сообщения шифрует телефон отправителя открытым ключом получателя
(HPKE: X25519 + ChaCha20-Poly1305, библиотека Tink в приложении), расшифровать может только
телефон получателя. Ни сервер, ни хостинг, ни админ текст не прочитают.

Что сервер всё же знает (метаданные): какой подписке принадлежит код чата, кто кому и когда
писал и сколько байт. Сообщение лежит на сервере, пока получатель его не заберёт (не дольше
MAX_AGE), и после подтверждения удаляется.

Адресация — по коду чата (9 знаков), его гость сам даёт собеседнику. Вход — по ссылке подписки
и номеру устройства: запрос приходит на <подписка>/chat/<действие>, сервер подписок проверяет, что
подписка активна и у устройства есть место в ней (те же места, что в «📱 Устройства»), и передаёт
сюда номер подписки и устройства. У каждого устройства свой код: подписку на троих делят трое,
и у каждого своя переписка. Нет подписки или места — нет чата.
Чат включает и выключает админ (из приложения, по своей подписке).
"""

import base64
import json
import os
import secrets
import time

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # без похожих O/0, I/1/L
CODE_LEN = 9
MAX_BOX = 24 * 1024           # одно зашифрованное сообщение, байт (после base64 — чуть больше)
MAX_QUEUE = 1000              # писем в ящике одного получателя
MAX_FROM_ONE = 200            # из них — недоставленных от одного отправителя
MAX_AGE = 7 * 86400           # сколько письмо ждёт получателя
SEND_PER_MIN = 60             # сообщений в минуту от одного отправителя
MAX_KEY = 4096                # открытый ключ (набор ключей Tink в JSON/base64)


def norm_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch in ALPHABET)[:CODE_LEN]


class ChatRelay:
    def __init__(self, path: str, is_admin=None, stats=None):
        self.path = path
        self.is_admin = is_admin or (lambda uid: False)
        # Сводка для админа в приложении (подписки, онлайн, деньги) — её даёт бот
        self.stats = stats or (lambda: {})
        self.data = {"enabled": True, "users": {}, "codes": {}, "boxes": {}, "banned": [], "notice": ""}
        self._rate: dict[str, list[float]] = {}
        try:
            with open(path, encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    # ---------- данные ----------

    @staticmethod
    def ident(uid: int, device: str) -> str:
        return f"{uid}:{device}"

    def code_of(self, uid: int, device: str) -> str:
        return self.data["users"].get(self.ident(uid, device), {}).get("code", "")

    def drop(self, uid: int, device: str | None = None) -> int:
        """Убрать код чата устройства (удалили в «📱 Устройства») или всех устройств подписки
        («Сбросить все»): ключ и письма для него пропадают. Возвращает, сколько убрано."""
        me = self.ident(uid, device or "")
        # «телефон#1» — второй профиль чата на том же устройстве (второй PIN): уходит вместе с ним
        gone = [k for k in self.data["users"]
                if (device is not None and (k == me or k.startswith(me + "#")))
                or (device is None and k.startswith(f"{uid}:"))]
        for k in gone:
            code = self.data["users"].pop(k).get("code")
            if code:
                self.data["codes"].pop(code, None)
                self.data["boxes"].pop(code, None)
        if gone:
            self._save()
        return len(gone)

    def _prune(self, now: float) -> None:
        for code, box in list(self.data["boxes"].items()):
            box[:] = [m for m in box if now - m["t"] < MAX_AGE]
            if not box:
                del self.data["boxes"][code]

    # ---------- запросы ----------

    def handle(self, uid: int, action: str, method: str, query: dict, body: bytes,
               device: str = "") -> tuple[int, dict]:
        """Один запрос приложения с устройства device подписки uid. Возвращает (HTTP-код, JSON)."""
        try:
            req = json.loads(body or b"{}") if method == "POST" else {}
            if not isinstance(req, dict):
                raise ValueError
        except ValueError:
            return 400, {"error": "bad json"}
        admin = bool(self.is_admin(uid))
        if action == "status":
            return 200, {"enabled": bool(self.data["enabled"]), "admin": admin, "code": self.code_of(uid, device),
                         "notice": self.data.get("notice", "")}
        if action == "admin":
            if not admin:
                return 403, {"error": "not admin"}
            if method == "POST":
                if "enabled" in req:
                    self.data["enabled"] = bool(req["enabled"])
                if "notice" in req:  # объявление всем в чате: видно сверху списка чатов, не шифруется
                    self.data["notice"] = str(req["notice"] or "").strip()[:500]
                for key, on in (("ban", True), ("unban", False)):
                    code = norm_code(str(req.get(key, "")))
                    if len(code) == CODE_LEN:
                        banned = set(self.data.get("banned", []))
                        banned = banned | {code} if on else banned - {code}
                        self.data["banned"] = sorted(banned)
                        if on:
                            self.data["boxes"].pop(code, None)  # и письма для него — в никуда
                self._save()
            now = time.time()
            self._prune(now)
            try:
                extra = dict(self.stats() or {})
            except Exception:
                extra = {}
            return 200, {"enabled": bool(self.data["enabled"]), "users": len(self.data["users"]),
                         "queued": sum(len(b) for b in self.data["boxes"].values()),
                         "notice": self.data.get("notice", ""), "banned": self.data.get("banned", []), **extra}
        if not self.data["enabled"]:
            return 403, {"error": "disabled"}
        if action == "register" and method == "POST":
            return self._register(uid, device, str(req.get("key", "")))
        if action == "key":
            code = norm_code((query.get("code") or [""])[0])
            u = self.data["codes"].get(code)
            if not u:
                return 404, {"error": "no such code"}
            return 200, {"code": code, "key": self.data["users"][u]["key"]}
        me = self.code_of(uid, device)
        if not me:
            return 409, {"error": "not registered"}
        if me in self.data.get("banned", []):
            return 403, {"error": "banned"}
        if action == "send" and method == "POST":
            return self._send(uid, me, norm_code(str(req.get("to", ""))), str(req.get("box", "")))
        if action == "inbox":
            now = time.time()
            self._prune(now)
            msgs = self.data["boxes"].get(me, [])[:200]
            return 200, {"messages": [{"id": m["id"], "from": m["from"], "box": m["box"], "t": int(m["t"])}
                                      for m in msgs]}
        if action == "ack" and method == "POST":
            ids = {str(i) for i in req.get("ids") or []}
            box = self.data["boxes"].get(me, [])
            left = [m for m in box if m["id"] not in ids]
            if len(left) != len(box):
                if left:
                    self.data["boxes"][me] = left
                else:
                    self.data["boxes"].pop(me, None)
                self._save()
            return 200, {"ok": True}
        return 404, {"error": "unknown action"}

    def _register(self, uid: int, device: str, key: str) -> tuple[int, dict]:
        """Открытый ключ устройства. Код у устройства постоянный; новый ключ (переустановка,
        «стереть всё») заменяет прежний — письма для старого ключа удаляются, прочитать их нельзя."""
        if not device:
            return 400, {"error": "no device"}
        if not key or len(key) > MAX_KEY:
            return 400, {"error": "bad key"}
        try:
            base64.b64decode(key, validate=True)
        except ValueError:
            return 400, {"error": "bad key"}
        me = self.ident(uid, device)
        u = self.data["users"].setdefault(me, {})
        code = u.get("code")
        if not code:
            while True:
                code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
                if code not in self.data["codes"]:
                    break
            u["code"] = code
            self.data["codes"][code] = me
        if u.get("key") != key:
            u["key"] = key
            self.data["boxes"].pop(code, None)
        u["t"] = time.time()
        self._save()
        return 200, {"code": code}

    def _send(self, uid: int, me: str, to: str, box: str) -> tuple[int, dict]:
        if to not in self.data["codes"] or to in self.data.get("banned", []):
            return 404, {"error": "no such code"}
        if not box or len(box) > MAX_BOX * 4 // 3 + 4:
            return 400, {"error": "bad box"}
        try:
            base64.b64decode(box, validate=True)
        except ValueError:
            return 400, {"error": "bad box"}
        now = time.time()
        recent = [t for t in self._rate.get(me, []) if now - t < 60]
        if len(recent) >= SEND_PER_MIN:
            return 429, {"error": "too fast"}
        recent.append(now)
        self._rate[me] = recent
        q = self.data["boxes"].setdefault(to, [])
        if len(q) >= MAX_QUEUE:
            return 507, {"error": "recipient box full"}
        # Один отправитель не может забить чужой ящик целиком и закрыть его для остальных
        if sum(1 for m in q if m["from"] == me) >= MAX_FROM_ONE:
            return 429, {"error": "too fast"}
        # «from» ставит сервер по подписке отправителя: подделать отправителя нельзя
        q.append({"id": secrets.token_hex(8), "from": me, "box": box, "t": now})
        self._save()
        return 200, {"ok": True}
