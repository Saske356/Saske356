"""Ретранслятор зашифрованного чата для приложения Arise.

Сервер хранит только шифр: сообщения шифрует телефон отправителя открытым ключом получателя
(HPKE: X25519 + ChaCha20-Poly1305, библиотека Tink в приложении), расшифровать может только
телефон получателя. Ни сервер, ни хостинг, ни админ текст не прочитают.

Что сервер всё же знает (метаданные): какой подписке принадлежит код чата, кто кому и когда
писал и сколько байт. Сообщение лежит на сервере, пока получатель его не заберёт (не дольше
MAX_AGE), и после подтверждения удаляется.

Адресация — по коду чата (9 знаков), его гость сам даёт собеседнику. Вход — по ссылке подписки:
запрос приходит на <подписка>/chat/<действие>, сервер подписок проверяет её и передаёт сюда номер
подписки. Чат включает и выключает админ (из приложения, по своей подписке).
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
MAX_AGE = 7 * 86400           # сколько письмо ждёт получателя
SEND_PER_MIN = 60             # сообщений в минуту от одного отправителя
MAX_KEY = 4096                # открытый ключ (набор ключей Tink в JSON/base64)


def norm_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch in ALPHABET)[:CODE_LEN]


class ChatRelay:
    def __init__(self, path: str, is_admin=None):
        self.path = path
        self.is_admin = is_admin or (lambda uid: False)
        self.data = {"enabled": True, "users": {}, "codes": {}, "boxes": {}}
        self._rate: dict[int, list[float]] = {}
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

    def code_of(self, uid: int) -> str:
        return self.data["users"].get(str(uid), {}).get("code", "")

    def _prune(self, now: float) -> None:
        for code, box in list(self.data["boxes"].items()):
            box[:] = [m for m in box if now - m["t"] < MAX_AGE]
            if not box:
                del self.data["boxes"][code]

    # ---------- запросы ----------

    def handle(self, uid: int, action: str, method: str, query: dict, body: bytes) -> tuple[int, dict]:
        """Один запрос приложения. Возвращает (HTTP-код, JSON-ответ)."""
        try:
            req = json.loads(body or b"{}") if method == "POST" else {}
            if not isinstance(req, dict):
                raise ValueError
        except ValueError:
            return 400, {"error": "bad json"}
        admin = bool(self.is_admin(uid))
        if action == "status":
            return 200, {"enabled": bool(self.data["enabled"]), "admin": admin, "code": self.code_of(uid)}
        if action == "admin":
            if not admin:
                return 403, {"error": "not admin"}
            if method == "POST" and "enabled" in req:
                self.data["enabled"] = bool(req["enabled"])
                self._save()
            now = time.time()
            self._prune(now)
            return 200, {"enabled": bool(self.data["enabled"]), "users": len(self.data["users"]),
                         "queued": sum(len(b) for b in self.data["boxes"].values())}
        if not self.data["enabled"]:
            return 403, {"error": "disabled"}
        if action == "register" and method == "POST":
            return self._register(uid, str(req.get("key", "")))
        if action == "key":
            code = norm_code((query.get("code") or [""])[0])
            u = self.data["codes"].get(code)
            if not u:
                return 404, {"error": "no such code"}
            return 200, {"code": code, "key": self.data["users"][str(u)]["key"]}
        me = self.code_of(uid)
        if not me:
            return 409, {"error": "not registered"}
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

    def _register(self, uid: int, key: str) -> tuple[int, dict]:
        """Открытый ключ телефона. Код у подписки постоянный; новый телефон (или переустановка)
        заменяет ключ — старые письма для прежнего ключа удаляются, прочитать их уже нельзя."""
        if not key or len(key) > MAX_KEY:
            return 400, {"error": "bad key"}
        try:
            base64.b64decode(key, validate=True)
        except ValueError:
            return 400, {"error": "bad key"}
        u = self.data["users"].setdefault(str(uid), {})
        code = u.get("code")
        if not code:
            while True:
                code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
                if code not in self.data["codes"]:
                    break
            u["code"] = code
            self.data["codes"][code] = uid
        if u.get("key") != key:
            u["key"] = key
            self.data["boxes"].pop(code, None)
        u["t"] = time.time()
        self._save()
        return 200, {"code": code}

    def _send(self, uid: int, me: str, to: str, box: str) -> tuple[int, dict]:
        if to not in self.data["codes"]:
            return 404, {"error": "no such code"}
        if not box or len(box) > MAX_BOX * 4 // 3 + 4:
            return 400, {"error": "bad box"}
        try:
            base64.b64decode(box, validate=True)
        except ValueError:
            return 400, {"error": "bad box"}
        now = time.time()
        recent = [t for t in self._rate.get(uid, []) if now - t < 60]
        if len(recent) >= SEND_PER_MIN:
            return 429, {"error": "too fast"}
        recent.append(now)
        self._rate[uid] = recent
        q = self.data["boxes"].setdefault(to, [])
        if len(q) >= MAX_QUEUE:
            return 507, {"error": "recipient box full"}
        # «from» ставит сервер по подписке отправителя: подделать отправителя нельзя
        q.append({"id": secrets.token_hex(8), "from": me, "box": box, "t": now})
        self._save()
        return 200, {"ok": True}
