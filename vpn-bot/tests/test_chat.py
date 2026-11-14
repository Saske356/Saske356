import base64
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import chat_relay  # noqa: E402

KEY_A = base64.b64encode(b"public key of A").decode()
KEY_B = base64.b64encode(b"public key of B").decode()
BOX = base64.b64encode(b"\x00ciphertext").decode()


class ChatRelayTest(unittest.TestCase):
    def test_each_device_of_a_subscription_has_its_own_code(self):
        a = self.call(1, "register", "POST", {"key": KEY_A}, dev="mom")[1]["code"]
        b = self.call(1, "register", "POST", {"key": KEY_B}, dev="son")[1]["code"]
        self.assertNotEqual(a, b, "подписка на двоих — два разных чата")
        self.call(1, "send", "POST", {"to": b, "box": BOX}, dev="mom")
        self.assertEqual(self.call(1, "inbox", dev="mom")[1]["messages"], [], "мама не видит почту сына")
        self.assertEqual(len(self.call(1, "inbox", dev="son")[1]["messages"]), 1)
        second = self.call(1, "register", "POST", {"key": KEY_A}, dev="son#1")[1]["code"]
        self.assertNotIn(second, (a, b), "второй профиль на том же телефоне — свой код")
        self.assertEqual(self.c.drop(1, "son"), 2, "устройство удалили в боте — пропали оба его профиля")
        self.assertEqual(self.call(1, "key", code=b)[0], 404)
        self.assertEqual(self.c.drop(1), 1, "«Сбросить все» — пропали все коды подписки")
        self.assertEqual(self.call(1, "status", dev="mom")[1]["code"], "")

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.path = os.path.join(self.d, "chat.json")
        self.c = chat_relay.ChatRelay(self.path, is_admin=lambda uid: uid == 99)

    def call(self, uid, action, method="GET", body=None, dev="phone", **query):
        return self.c.handle(uid, action, method, {k: [v] for k, v in query.items()},
                             json.dumps(body).encode() if body is not None else b"", dev)

    def test_message_goes_through_as_ciphertext_only(self):
        code_a = self.call(1, "register", "POST", {"key": KEY_A})[1]["code"]
        code_b = self.call(2, "register", "POST", {"key": KEY_B})[1]["code"]
        self.assertEqual(len(code_a), chat_relay.CODE_LEN)
        self.assertEqual(self.call(1, "register", "POST", {"key": KEY_A})[1]["code"], code_a, "код постоянный")
        self.assertEqual(self.call(1, "key", code=code_b.lower())[1]["key"], KEY_B, "поиск без учёта регистра")
        self.assertEqual(self.call(1, "key", code="ZZZZZZZZZ")[0], 404)
        self.assertEqual(self.call(1, "send", "POST", {"to": code_b, "box": BOX}), (200, {"ok": True}))
        msgs = self.call(2, "inbox")[1]["messages"]
        self.assertEqual([(m["from"], m["box"]) for m in msgs], [(code_a, BOX)], "отправителя ставит сервер")
        self.assertEqual(self.call(2, "inbox")[1]["messages"], msgs, "без подтверждения письмо остаётся")
        self.call(2, "ack", "POST", {"ids": [msgs[0]["id"]]})
        self.assertEqual(self.call(2, "inbox")[1]["messages"], [])
        with open(self.path) as f:
            self.assertNotIn("ciphertext", f.read(), "на диске нет даже шифра прочитанных писем")
        # после перезапуска данные на месте
        again = chat_relay.ChatRelay(self.path)
        self.assertEqual(again.code_of(1, "phone"), code_a)

    def test_new_key_drops_old_mail_and_bad_input(self):
        self.call(1, "register", "POST", {"key": KEY_A})
        code_b = self.call(2, "register", "POST", {"key": KEY_B})[1]["code"]
        self.call(1, "send", "POST", {"to": code_b, "box": BOX})
        self.call(2, "register", "POST", {"key": KEY_A})  # новый телефон: старые письма не прочитать
        self.assertEqual(self.call(2, "inbox")[1]["messages"], [])
        self.assertEqual(self.call(3, "inbox")[0], 409, "без регистрации")
        self.assertEqual(self.call(1, "send", "POST", {"to": code_b, "box": "!!"})[0], 400)
        self.assertEqual(self.call(1, "send", "POST", {"to": code_b, "box": "A" * 40000})[0], 400)
        self.assertEqual(self.call(1, "register", "POST", {"key": "not base64!"})[0], 400)
        self.assertEqual(self.c.handle(1, "send", "POST", {}, b"[1]", "phone")[0], 400)
        self.assertEqual(self.call(1, "register", "POST", {"key": KEY_A}, dev="")[0], 400, "без устройства")

    def test_rate_limit_and_old_mail(self):
        self.call(1, "register", "POST", {"key": KEY_A})
        code_b = self.call(2, "register", "POST", {"key": KEY_B})[1]["code"]
        codes = [self.call(1, "send", "POST", {"to": code_b, "box": BOX})[0] for _ in range(chat_relay.SEND_PER_MIN + 1)]
        self.assertEqual(codes[-1], 429)
        for m in self.c.data["boxes"][code_b]:
            m["t"] = time.time() - chat_relay.MAX_AGE - 1
        self.assertEqual(self.call(2, "inbox")[1]["messages"], [], "письма старше недели удаляются")

    def test_admin_bans_code_posts_notice_and_sees_stats(self):
        self.c.stats = lambda: {"subs": 7, "online": 3}
        a = self.call(1, "register", "POST", {"key": KEY_A})[1]["code"]
        b = self.call(2, "register", "POST", {"key": KEY_B})[1]["code"]
        ans = self.call(99, "admin", "POST", {"ban": a.lower(), "notice": "  Технические работы в 23:00  "})[1]
        self.assertEqual((ans["banned"], ans["notice"], ans["subs"], ans["online"]),
                         ([a], "Технические работы в 23:00", 7, 3))
        self.assertEqual(self.call(1, "status")[1]["notice"], "Технические работы в 23:00", "объявление видят все")
        self.assertEqual(self.call(1, "send", "POST", {"to": b, "box": BOX})[1]["error"], "banned")
        self.assertEqual(self.call(2, "send", "POST", {"to": a, "box": BOX})[0], 404, "заблокированному не написать")
        self.call(99, "admin", "POST", {"unban": a, "notice": ""})
        self.assertEqual(self.call(1, "send", "POST", {"to": b, "box": BOX})[0], 200)
        self.assertEqual(self.call(1, "status")[1]["notice"], "")
        self.c.stats = lambda: 1 / 0
        self.assertEqual(self.call(99, "admin")[0], 200, "сводка сломалась — админка всё равно открывается")

    def test_one_sender_cannot_fill_someone_box(self):
        self.call(1, "register", "POST", {"key": KEY_A})
        b = self.call(2, "register", "POST", {"key": KEY_B})[1]["code"]
        self.c.data["boxes"][b] = [{"id": str(i), "from": self.c.code_of(1, "phone"), "box": BOX, "t": time.time()}
                                   for i in range(chat_relay.MAX_FROM_ONE)]
        self.assertEqual(self.call(1, "send", "POST", {"to": b, "box": BOX})[0], 429)
        self.call(3, "register", "POST", {"key": KEY_A})
        self.assertEqual(self.call(3, "send", "POST", {"to": b, "box": BOX})[0], 200, "другие пишут как обычно")

    def test_admin_switches_chat(self):
        self.assertEqual(self.call(1, "status")[1], {"enabled": True, "admin": False, "code": "", "notice": ""})
        self.assertTrue(self.call(99, "status")[1]["admin"])
        self.assertEqual(self.call(1, "admin", "POST", {"enabled": False})[0], 403, "только админ")
        self.assertEqual(self.call(99, "admin", "POST", {"enabled": False})[1]["enabled"], False)
        self.assertEqual(self.call(1, "register", "POST", {"key": KEY_A})[0], 403, "чат выключен")
        self.assertEqual(self.call(99, "admin")[1], {"enabled": False, "users": 0, "queued": 0, "notice": "", "banned": []})
        self.call(99, "admin", "POST", {"enabled": True})
        self.assertEqual(self.call(1, "register", "POST", {"key": KEY_A})[0], 200)


if __name__ == "__main__":
    unittest.main()
