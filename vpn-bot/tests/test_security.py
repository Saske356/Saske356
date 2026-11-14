import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import security  # noqa: E402

SS = """tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))
tcp LISTEN 0 4096 0.0.0.0:443 0.0.0.0:* users:(("python3",pid=2,fd=5))
udp UNCONN 0 0 *:443 *:* users:(("hysteria",pid=3,fd=6))
tcp LISTEN 0 4096 127.0.0.1:10085 0.0.0.0:* users:(("xray",pid=4,fd=7))
tcp LISTEN 0 4096 0.0.0.0:6379 0.0.0.0:* users:(("redis-server",pid=5,fd=8))
"""


class AuditTest(unittest.TestCase):
    def make(self, sshd, ufw="Status: active", f2b="active", files=(), shadow="root:$6$x:1::::::\n"):
        answers = {"sshd": sshd, "ufw": ufw, "systemctl": f2b, "ss": SS,
                   "apt-get": "Inst libssl3 [3.0.1] (3.0.2 Ubuntu:22.04/jammy-security [amd64])\nInst vim [1] (2 x)\n"}
        reads = {"/etc/apt/apt.conf.d/20auto-upgrades": 'APT::Periodic::Unattended-Upgrade "1";',
                 "/etc/shadow": shadow}
        return security.Audit(list(files), {443}, run=lambda cmd, timeout=60: answers.get(cmd[0], ""),
                              read=lambda p: reads.get(p, ""), exists=lambda p: False)

    def test_root_password_login_is_flagged_with_a_fix(self):
        res = self.make("port 22\npasswordauthentication yes\npermitrootlogin yes\n").check()
        titles = {r[1]: r for r in res}
        self.assertEqual(titles["SSH: вход root по паролю"][0], security.BAD)
        self.assertIn("PasswordAuthentication no", titles["SSH: вход root по паролю"][3])
        ports = titles["Наружу открыты незнакомые порты"]
        self.assertIn("6379 (redis-server)", ports[2])
        self.assertNotIn("10085", ports[2], "локальные порты не считаются открытыми наружу")
        self.assertIn("Не установлены обновления безопасности: 1", titles)
        text = security.report(res)
        self.assertIn("Найдено проблем", text)

    def test_clean_server_and_perms_fix(self):
        d = tempfile.mkdtemp()
        f = os.path.join(d, "bot.db")
        open(f, "w").close()
        os.chmod(f, 0o644)
        a = self.make("port 2222\npasswordauthentication no\npermitrootlogin prohibit-password\n", files=[f])
        res = a.check()
        self.assertIn("Файлы с секретами читают посторонние", security.problems(res))
        self.assertEqual(a.fix_perms(), 1)
        self.assertEqual(os.stat(f).st_mode & 0o777, 0o600)
        self.assertNotIn("Файлы с секретами читают посторонние", security.problems(a.check()))
        self.assertIn("SSH: только по ключу", {r[1] for r in res})

    def test_missing_tools_and_empty_passwords(self):
        res = self.make("", ufw="", f2b="inactive", shadow="root:$6$x:1::\nguest::1::\n").check()
        names = security.problems(res)
        self.assertIn("Нет защиты от перебора паролей", names)
        self.assertIn("Учётки без пароля", names)
        self.assertIn("Файрвол", names)


if __name__ == "__main__":
    unittest.main()
