import json, socket, tempfile, unittest
from pathlib import Path
from unittest import mock

import pit_fetch
from pit_guard import Blocked, CN, Guard, QuotaDone, Stop


def message(code, text="x", tail="data"):
    return "0" * 21 + f"{code}\1{text}\1{tail}\n"


class Clock:
    def __init__(self, t=1793900000.0):
        self.t, self.slept = t, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class NoNetwork(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("测试不能联网"))
        p.start()
        self.addCleanup(p.stop)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.clock = Clock()

    def guard(self, limit=5):
        g = Guard(self.dir / "s", limit=limit, now=self.clock.now, sleep=self.clock.sleep)
        g.acquire()
        self.addCleanup(g.release)
        return g


class GuardTest(NoNetwork):
    def test_second_process_refused_then_released(self):
        g = self.guard()
        with self.assertRaises(Stop):
            Guard(self.dir / "s").acquire()
        g.release()
        self.guard()

    def test_no_send_without_lock(self):
        real = mock.Mock()
        with self.assertRaises(Stop):
            Guard(self.dir / "s").send(real, "m")
        real.assert_not_called()

    def test_interval_survives_restart(self):
        g = self.guard()
        g.send(lambda m: "", "a")
        g.send(lambda m: "", "b")
        self.assertEqual(self.clock.slept, [1.0])
        g.release()
        self.guard().send(lambda m: "", "c")
        self.assertEqual(self.clock.slept, [1.0, 1.0])

    def test_slow_response_counts_from_its_end(self):
        g = self.guard()
        def slow(m):
            self.clock.t += 30
            return ""
        g.send(slow, "a")
        g.send(slow, "b")
        self.assertEqual(self.clock.slept, [1.0])

    def test_clock_going_backwards_waits_at_most_interval(self):
        g = self.guard()
        g.send(lambda m: "", "a")
        self.clock.t -= 1000
        g.send(lambda m: "", "b")
        self.assertEqual(self.clock.slept, [1.0])

    def test_quota_survives_restart_and_stops_before_send(self):
        g = self.guard(limit=2)
        g.send(lambda m: "", "a")
        g.release()
        g = self.guard(limit=2)
        g.send(lambda m: "", "b")
        real = mock.Mock()
        with self.assertRaises(QuotaDone) as e:
            g.send(real, "c")
        self.assertEqual(e.exception.code, 0)
        real.assert_not_called()

    def test_counted_before_send_even_if_it_crashes(self):
        g = self.guard()
        with self.assertRaises(ValueError):
            g.send(mock.Mock(side_effect=ValueError), "a")
        g.release()
        self.assertEqual(self.guard().used(), 1)

    def test_network_failure_is_counted(self):
        g = self.guard()
        self.assertIsNone(g.send(lambda m: None, "a"))
        self.assertEqual(g.used(), 1)

    def test_day_changes_at_beijing_midnight(self):
        self.clock.t = 1793894399.0 - 1793894399 % 86400 + 16 * 3600 - 2
        g = self.guard(limit=1)
        g.send(lambda m: "", "a")
        self.assertEqual(g.remaining(), 0)
        self.clock.t += 2
        self.assertEqual(g.remaining(), 1)
        self.assertEqual(self.clock.now() % 86400, 16 * 3600)

    def test_corrupt_or_wrong_state_is_not_reset(self):
        d = self.dir / "s"
        d.mkdir()
        for text in ("{bad", "[]", '{"days": {"2026-11-06": "x"}, "last": 0}', '{"days": {}}'):
            (d / "state.json").write_text(text)
            g = Guard(d)
            with self.assertRaises(Stop):
                g.acquire()
            g.release()
            self.assertEqual((d / "state.json").read_text(), text)

    def test_blacklist_response_stops_and_stays_stopped(self):
        g = self.guard()
        with self.assertRaises(Blocked):
            g.send(lambda m: message("10001011", "黑名单用户"), "login")
        self.assertIn("黑名单用户", (self.dir / "s/blocked.json").read_text())
        real = mock.Mock()
        with self.assertRaises(Blocked):
            g.send(real, "next")
        g.release()
        with self.assertRaises(Blocked):
            self.guard()
        real.assert_not_called()

    def test_blacklist_not_swallowed_by_except_exception(self):
        g = self.guard()
        with self.assertRaises(Blocked):
            try:
                g.send(lambda m: message("10001011"), "a")
            except Exception:
                self.fail("被 except Exception 吞掉")

    def test_blacklist_number_inside_data_is_not_a_block(self):
        g = self.guard()
        g.send(lambda m: message("0", "success", "10001011"), "a")
        g.send(lambda m: "short", "b")
        g.send(lambda m: "", "c")
        self.assertFalse((self.dir / "s/blocked.json").exists())


B = {"ipoDate": "2021-05-25", "outDate": ""}


class PlanTest(unittest.TestCase):
    def full(self):
        return pit_fetch.plan([], "2030-01-01")

    def test_blank_or_bad_dates_skip_nothing_by_those_dates(self):
        p, y, s = self.full()
        for basic in ([{"ipoDate": "", "outDate": ""}], [{"ipoDate": "未知", "outDate": None}], [{}]):
            self.assertEqual(pit_fetch.plan(basic, "2030-01-01")[:2], (p, y))
        self.assertEqual(s, {"periods": [], "dividend_years": []})
        self.assertEqual(len(p), 4 + 33)

    def test_pre_ipo_keeps_two_years(self):
        p, y, s = pit_fetch.plan([B], "2026-11-06")
        self.assertEqual(p[0], (2019, 1))
        self.assertIn((2020, 4), p)
        self.assertEqual(y[0], 2019)
        self.assertIn([2018, 4], s["periods"])

    def test_after_delisting_skipped_but_last_report_kept(self):
        p, y, s = pit_fetch.plan([{"ipoDate": "1998-04-20", "outDate": "2023-06-26"}], "2026-11-06")
        self.assertIn((2023, 1), p)
        self.assertNotIn((2023, 2), p)
        self.assertEqual(y[-1], 2023)

    def test_delisted_on_period_end_keeps_period(self):
        p = pit_fetch.plan([{"ipoDate": "1998-04-20", "outDate": "2023-06-30"}], "2026-11-06")[0]
        self.assertIn((2023, 2), p)

    def test_unpublished_periods(self):
        self.assertNotIn((2026, 4), pit_fetch.plan([], "2026-11-06")[0])
        self.assertIn((2026, 2), pit_fetch.plan([], "2026-11-06")[0])
        self.assertNotIn((2026, 2), pit_fetch.plan([], "2026-08-31")[0])
        self.assertIn((2026, 2), pit_fetch.plan([], "2026-09-01")[0])
        self.assertNotIn((2025, 4), pit_fetch.plan([], "2026-03-01")[0])

    def test_future_dividend_year_skipped(self):
        self.assertEqual(pit_fetch.plan([], "2025-06-01")[1][-1], 2025)


class Result:
    def __init__(self, data=(), code="0", msg="success"):
        self.data, self.error_code, self.error_msg = list(data), code, msg
        self.fields, self.i = ["ipoDate", "outDate"], 0

    def next(self):
        self.i += 1
        return self.i <= len(self.data)

    def get_row_data(self):
        return self.data[self.i - 1]


class FakeClient:
    """调用方式与 baostock 相同，每次查询都经过 sock.send_msg。"""
    def __init__(self, sock, answer):
        self.sock, self.answer, self.calls = sock, answer, []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append(name)
            self.sock.send_msg(name)
            return self.answer(name, a, k)
        return call


class Sock:
    def __init__(self, reply):
        self.reply, self.sent = reply, []

    def send_msg(self, m):
        self.sent.append(m)
        return self.reply(m, len(self.sent))


class MainTest(NoNetwork):
    def run_main(self, reply=lambda m, n: message("0"), answer=None, args=(), limit=40000, codes=("sh.600001", "sh.600002")):
        sock = Sock(reply)
        answer = answer or (lambda n, a, k: Result([["2000-01-01", ""]] if n == "query_stock_basic" else []))
        client = FakeClient(sock, answer)
        out = self.dir / "pit"
        out.mkdir(exist_ok=True)
        (out / "universe.json").write_text(json.dumps({"d": list(codes)}))
        real_guard = Guard
        def make(state):
            return real_guard(self.dir / "s", limit=limit, now=self.clock.now, sleep=self.clock.sleep)
        def load(argv):
            pit_fetch.bs = client
            return sock
        with mock.patch.object(pit_fetch, "OUT", out), mock.patch.object(pit_fetch, "Guard", make), \
                mock.patch.object(pit_fetch, "load_client", load), mock.patch.object(pit_fetch.time, "sleep"):
            try:
                pit_fetch.main(list(args))
            finally:
                pit_fetch.guard.release()
        return sock, client, out

    def test_normal_run_saves_and_logs_out(self):
        sock, client, out = self.run_main()
        self.assertTrue((out / "sh.600001.json").exists())
        d = json.loads((out / "sh.600002.json").read_text())
        self.assertIn([2026, 4], d["skipped"]["periods"])
        self.assertEqual(client.calls[-1], "logout")

    def test_every_call_is_counted(self):
        sock, client, _ = self.run_main()
        state = json.loads((self.dir / "s/state.json").read_text())
        self.assertEqual(sum(state["days"].values()), len(sock.sent))
        self.assertLess(len(sock.sent) // 2, pit_fetch.STOCK_RESERVE)

    def test_blacklist_at_login_sends_one_message(self):
        sock = None
        with self.assertRaises(Blocked):
            self.run_main(reply=lambda m, n: message("10001011", "黑名单用户"))
        self.assertTrue((self.dir / "s/blocked.json").exists())

    def test_blacklist_mid_stock_no_retry_no_logout_no_file(self):
        seen = []
        def reply(m, n):
            seen.append(m)
            return message("10001011") if n == 5 else message("0")
        with self.assertRaises(Blocked):
            self.run_main(reply=reply)
        self.assertEqual(len(seen), 5)
        self.assertFalse((self.dir / "pit/sh.600001.json").exists())

    def test_blacklist_only_in_result_object(self):
        def answer(n, a, k):
            return Result([], "10001011", "黑名单用户") if n == "query_profit_data" else Result([["2000-01-01", ""]])
        with self.assertRaises(Blocked):
            self.run_main(answer=answer)
        self.assertTrue((self.dir / "s/blocked.json").exists())

    def test_marker_prevents_any_message_and_clear_sends_none(self):
        (self.dir / "s").mkdir()
        (self.dir / "s/blocked.json").write_text("{}")
        with mock.patch.object(pit_fetch, "load_client", side_effect=AssertionError):
            g = Guard(self.dir / "s")
            with mock.patch.object(pit_fetch, "Guard", lambda s: g), self.assertRaises(Blocked):
                pit_fetch.main([])
            g.release()
            with mock.patch.object(pit_fetch, "Guard", lambda s: Guard(self.dir / "s")):
                pit_fetch.main(["--clear-block"])
        self.assertFalse((self.dir / "s/blocked.json").exists())

    def test_shard_rejected_before_anything(self):
        with mock.patch.object(pit_fetch, "Guard", side_effect=AssertionError), self.assertRaises(Stop):
            pit_fetch.main(["--shard", "0/3"])

    def test_low_quota_does_not_start_a_stock(self):
        with self.assertRaises(QuotaDone):
            self.run_main(limit=pit_fetch.STOCK_RESERVE)
        self.assertFalse((self.dir / "pit/sh.600001.json").exists())

    def test_login_failure_is_not_ignored(self):
        def answer(n, a, k):
            return Result([], "10002007", "网络接收错误")
        with self.assertRaises(RuntimeError):
            self.run_main(answer=answer)

    def test_error_on_later_page_is_not_saved_as_complete(self):
        r = Result([["a", "b"]])
        real_next = r.next
        def bad_next():
            ok = real_next()
            if not ok:
                r.error_code, r.error_msg = "10002007", "网络接收错误"
            return ok
        r.next = bad_next
        pit_fetch.guard = mock.Mock(block=mock.Mock())
        with self.assertRaises(RuntimeError):
            pit_fetch.rows(r)

    def test_repeated_failures_stop(self):
        def answer(n, a, k):
            return Result([], "10004003", "未知") if n == "query_stock_basic" else Result()
        with self.assertRaises(Stop):
            self.run_main(answer=answer, codes=[f"sh.6000{i:02d}" for i in range(20)])

    def test_probe_is_three_messages(self):
        sock, client, _ = self.run_main(args=["--probe"])
        self.assertEqual(client.calls, ["login", "query_stock_basic", "logout"])


if __name__ == "__main__":
    unittest.main()
