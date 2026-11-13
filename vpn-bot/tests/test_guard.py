import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import guard  # noqa: E402


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.t = [1000.0]
        self.g = guard.RateGuard(clock=lambda: self.t[0])

    def test_rate_limit_per_minute(self):
        for _ in range(guard.PER_MIN):
            self.assertTrue(self.g.enter("1.2.3.4")); self.g.leave("1.2.3.4")
        self.assertFalse(self.g.enter("1.2.3.4"), "61-й запрос за минуту отброшен")
        self.assertTrue(self.g.enter("5.6.7.8"), "другой адрес не задет"); self.g.leave("5.6.7.8")
        self.t[0] += 61
        self.assertTrue(self.g.enter("1.2.3.4"), "через минуту снова можно")

    def test_concurrent_per_ip_and_total(self):
        for _ in range(guard.PER_IP):
            self.assertTrue(self.g.enter("1.1.1.1"))
        self.assertFalse(self.g.enter("1.1.1.1"))
        self.g.leave("1.1.1.1")
        self.assertTrue(self.g.enter("1.1.1.1"))
        self.g.total = guard.TOTAL
        self.assertFalse(self.g.enter("9.9.9.9"), "общий лимит соединений")

    def test_ban_for_brute_force(self):
        for _ in range(guard.FAIL_LIMIT):
            self.g.fail("6.6.6.6")
        self.assertFalse(self.g.enter("6.6.6.6"))
        self.assertEqual(self.g.bans(), 1)
        self.t[0] += guard.BAN + 1
        self.assertTrue(self.g.enter("6.6.6.6"), "бан снимается сам")

    def test_localhost_is_never_limited(self):
        for _ in range(guard.PER_MIN * 2):
            self.assertTrue(self.g.enter("127.0.0.1"))
            self.g.fail("127.0.0.1")
        self.assertEqual(self.g.bans(), 0)


if __name__ == "__main__":
    unittest.main()
