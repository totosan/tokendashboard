import contextlib
import gzip
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from research.recorder import integrity_report, recorder

NOW_NS = 1_700_000_000_000_000_000  # 2023-11-14T22:13:20Z
NOW_MS = NOW_NS // 10**6


def body(url):
    if "orderbook" in url:
        return {"code": "00000", "data": {"ts": str(NOW_MS - 5), "b": [["10", "2"], ["9", "1"]],
                                           "a": [["11", "3"]]}}
    if "ticker" in url:
        return {"code": "00000", "requestTime": NOW_MS, "data": [
            {"ts": str(NOW_MS), "bidPr": "10", "askPr": "11", "bidSz": "1", "askSz": "2",
             "lastPr": "10.5", "fundingRate": "0.0001"}]}
    if "current-fund-rate" in url:
        return {"code": "00000", "requestTime": NOW_MS, "data": [
            {"symbol": "X", "fundingRate": "0.0001", "fundingRateInterval": "8",
             "nextUpdate": str(NOW_MS + 1000)}]}
    return {"code": "00000", "requestTime": NOW_MS, "data": [
        {"makerFeeRate": "0.0002", "takerFeeRate": "0.0006", "sizeMultiplier": "1"}]}


def good_fetch(calls):
    def fetch(url, timeout):
        calls.append(url)
        return json.dumps(body(url)).encode()
    return fetch


def run(root, **kw):
    symbols = kw.pop("symbols", ["AAPLUSDT", "BTCUSDT"])
    args = dict(cycles=2, interval=0, duration=60, wait=lambda s: None,
                now_ns=lambda: NOW_NS, min_gap=0, inventory=False, fetcher=good_fetch([]),
                clock_status=lambda: {"ntp_synchronized": True, "source": "test"})
    args.update(kw)
    return recorder.run(root, symbols, args.pop("cycles"), args.pop("interval"),
                        args.pop("duration"), **args)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        recorder.STOP.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        recorder.STOP.clear()
        self.tmp.cleanup()

    def records(self):
        out = []
        for p in self.root.rglob("*.jsonl.gz"):
            out += [json.loads(x) for x in gzip.decompress(p.read_bytes()).decode().splitlines()]
        return out

    def test_records_stored_with_both_clocks_and_utc_hour_partition(self):
        calls = []
        s = run(self.root, fetcher=good_fetch(calls), symbols=["AAPLUSDT", "BTCUSDT"])
        self.assertEqual(s["exit_status"], 0)
        # cycle1: 4 kinds x 2 symbols; cycle2: 2 kinds x 2 symbols
        self.assertEqual(s["records"], 12)
        self.assertTrue((self.root / "2023/11/14/22/records.jsonl.gz").exists())
        recs = self.records()
        book = next(r for r in recs if r["kind"] == "orderbook")
        self.assertEqual((book["event_ms"], book["available_ms"]), (NOW_MS - 5, NOW_MS))
        self.assertEqual(book["clock_skew_ms"], 5)
        self.assertEqual(book["fields"]["bid"], "10")
        self.assertEqual(book["instrument"]["product"], "USDT-FUTURES")
        fee = next(r for r in recs if r["kind"] == "contract")
        self.assertEqual(fee["fields"]["taker_fee_rate"], "0.0006")
        self.assertEqual(len(calls), 12)

    def test_append_only_and_integrity_report_ok(self):
        run(self.root, cycles=1)
        path = self.root / "2023/11/14/22/records.jsonl.gz"
        first = path.read_bytes()
        run(self.root, cycles=1, now_ns=lambda: NOW_NS + 10**9)
        self.assertTrue(path.read_bytes().startswith(first))
        rep = integrity_report.scan(self.root, 60)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["records"], 16)
        self.assertEqual(rep["duplicate_records"], 0)

    def test_integrity_detects_tamper_and_truncation(self):
        run(self.root, cycles=1)
        path = self.root / "2023/11/14/22/records.jsonl.gz"
        lines = gzip.decompress(path.read_bytes()).decode().splitlines()
        rec = json.loads(lines[0])
        rec["fields"]["bid"] = "999"
        path.write_bytes(gzip.compress(json.dumps(rec).encode() + b"\n"))
        rep = integrity_report.scan(self.root, 60)
        self.assertFalse(rep["ok"])
        self.assertEqual(len(rep["bad_records"]), 1)
        path.write_bytes(path.read_bytes()[:-6])
        self.assertTrue(integrity_report.scan(self.root, 60)["corrupt_partitions"])

    def test_gap_report(self):
        run(self.root, cycles=1, now_ns=lambda: NOW_NS)
        run(self.root, cycles=1, now_ns=lambda: NOW_NS + 300 * 10**9)
        rep = integrity_report.scan(self.root, 60)
        self.assertEqual(len(rep["gaps"]), 4)
        self.assertEqual(rep["gaps"][0]["seconds"], 300)

    def test_bounded_retries_then_failure_recorded(self):
        calls = []

        def bad(url, timeout):
            calls.append(url)
            raise OSError("boom")

        s = run(self.root, fetcher=bad, cycles=1, retries=2, symbols=["BTCUSDT"])
        self.assertEqual(len(calls), 3 * 4)
        self.assertEqual(s["exit_status"], 1)
        self.assertEqual(s["records"], 0)
        self.assertEqual(len(s["failures"]), 4)

    def test_retry_recovers_and_invalid_payload_not_written(self):
        state = {"n": 0}

        def flaky(url, timeout):
            state["n"] += 1
            if state["n"] == 1:
                raise TimeoutError("slow")
            if "ticker" in url:
                return json.dumps({"code": "40001", "data": []}).encode()
            return json.dumps(body(url)).encode()

        s = run(self.root, fetcher=flaky, cycles=1, symbols=["BTCUSDT"])
        self.assertEqual(s["exit_status"], 2)
        self.assertEqual({r["kind"] for r in self.records()}, {"orderbook", "funding", "contract"})
        self.assertEqual(s["failures"][0]["kind"], "ticker")

    def test_crossed_book_rejected(self):
        def crossed(url, timeout):
            d = body(url)
            if "orderbook" in url:
                d["data"]["a"] = [["9", "1"]]
            return json.dumps(d).encode()

        s = run(self.root, fetcher=crossed, cycles=1, symbols=["BTCUSDT"])
        self.assertEqual([f["kind"] for f in s["failures"]], ["orderbook"])

    def test_max_cycles_and_duration_cap(self):
        calls = []
        s = run(self.root, fetcher=good_fetch(calls), cycles=3, slow_every=100, symbols=["BTCUSDT"])
        self.assertEqual((s["cycles_completed"], len(calls)), (3, 4 + 2 + 2))
        ticks = iter(x * 100 for x in range(1000))
        s = run(self.root, cycles=50, duration=150, monotonic=lambda: next(ticks),
                symbols=["BTCUSDT"])
        self.assertEqual(s["stop_reason"], "DURATION_CAP")
        self.assertLess(s["cycles_completed"], 5)

    def test_sigterm_flag_stops_gracefully_after_current_request(self):
        calls = []

        def fetch(url, timeout):
            calls.append(url)
            recorder.STOP.set()
            return json.dumps(body(url)).encode()

        s = run(self.root, fetcher=fetch, cycles=10)
        self.assertEqual(s["stop_reason"], "SIGNAL")
        self.assertEqual(len(calls), 1)
        self.assertEqual(s["records"], 1)
        self.assertTrue(integrity_report.scan(self.root, 60)["ok"])

    def test_rate_limiter_enforces_gap(self):
        waits, t = [], [0.0]
        limiter = recorder.RateLimiter(0.5, lambda: t[0], waits.append)
        limiter.acquire()
        t[0] = 0.1
        limiter.acquire()
        self.assertEqual(waits, [0.4])

    def test_interval_wait_between_cycles(self):
        waits = []
        run(self.root, cycles=2, interval=5, wait=waits.append, symbols=["BTCUSDT"])
        self.assertTrue(any(w > 0 for w in waits))

    def test_rejects_bad_bounds_and_symbols(self):
        for kw in ({"cycles": 0}, {"duration": 0}, {"symbols": ["btc"]}, {"retries": 9}):
            with self.assertRaises(ValueError):
                run(self.root, **kw)

    def test_public_get_urls_only_and_no_credentials(self):
        urls = [recorder.build_url(*v) for v in recorder.endpoints("AAPLUSDT", 50).values()]
        self.assertTrue(all(u.startswith("https://api.bitget.com/api/v") for u in urls))
        src = Path(recorder.__file__).read_text().lower()
        for word in ("access-key", "api_key", "secret", "passphrase"):
            self.assertNotIn(word, src)


class CrashSafetyTests(unittest.TestCase):
    def setUp(self):
        recorder.STOP.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.part = self.root / "2023/11/14/22/records.jsonl.gz"

    def events(self):
        path = self.root / "_meta" / "events.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()]

    def test_torn_trailing_member_is_quarantined_and_truncated(self):
        run(self.root, cycles=1, symbols=["BTCUSDT"])
        good = self.part.read_bytes()
        torn = gzip.compress(b'{"x": 1}\n')[:-5]
        self.part.write_bytes(good + torn)
        (self.root / "_meta" / "clean_shutdown.json").unlink()  # simulate crash
        s = run(self.root, cycles=1, symbols=["BTCUSDT"], now_ns=lambda: NOW_NS + 10**9)
        self.assertEqual(s["previous_shutdown"], "unclean")
        self.assertEqual(s["recovered_partitions"][0]["quarantined_bytes"], len(torn))
        self.assertTrue(self.part.read_bytes().startswith(good))
        quarantined = Path(s["recovered_partitions"][0]["quarantine_file"])
        self.assertEqual(quarantined.read_bytes(), torn)
        self.assertTrue(integrity_report.scan(self.root, 60)["ok"])

    def test_torn_garbage_and_incomplete_line_handled(self):
        recorder.append_member(self.part, ["{}\n"])
        good = self.part.read_bytes()
        for tail in (b"\x00\x01garbage", gzip.compress(b'{"partial"')):
            self.part.write_bytes(good + tail)
            info = recorder.recover_partition(self.part, self.root, 1)
            self.assertEqual(info["kept_bytes"], len(good))
            self.assertEqual(self.part.read_bytes(), good)
        self.assertIsNone(recorder.recover_partition(self.part, self.root, 1))

    def test_marker_logic(self):
        marker = self.root / "_meta" / "clean_shutdown.json"
        s = run(self.root, cycles=1, symbols=["BTCUSDT"])
        self.assertEqual(s["previous_shutdown"], "first_run")
        self.assertTrue(marker.exists())
        self.assertEqual(run(self.root, cycles=1, symbols=["BTCUSDT"])["previous_shutdown"], "clean")
        # crash mid-run: marker consumed at start, never rewritten
        recorder.begin_run(self.root, "crashed", NOW_MS, {})
        self.assertFalse(marker.exists())
        s = run(self.root, cycles=1, symbols=["BTCUSDT"])
        self.assertEqual(s["previous_shutdown"], "unclean")
        startup = [e for e in self.events() if e["event"] == "startup"][-1]
        self.assertTrue(startup["unclean_shutdown_detected"])
        self.assertEqual(startup["clock_sync"]["source"], "test")
        rep = integrity_report.scan(self.root, 60)
        self.assertEqual(len(rep["unclean_startups"]), 1)

    def test_marker_written_on_sigterm_stop_not_on_exception(self):
        marker = self.root / "_meta" / "clean_shutdown.json"

        def fetch(url, timeout):
            recorder.STOP.set()
            return json.dumps(body(url)).encode()

        run(self.root, fetcher=fetch, cycles=5, symbols=["BTCUSDT"])
        self.assertEqual(json.loads(marker.read_text())["stop_reason"], "SIGNAL")
        marker.unlink()

        def boom(url, timeout):
            raise KeyboardInterrupt

        recorder.STOP.clear()
        with self.assertRaises(KeyboardInterrupt):
            run(self.root, fetcher=boom, cycles=1, symbols=["BTCUSDT"])
        self.assertFalse(marker.exists())

    def test_clock_sync_stored_in_records_and_probe(self):
        run(self.root, cycles=1, symbols=["BTCUSDT"])
        rec = json.loads(gzip.decompress(self.part.read_bytes()).decode().splitlines()[0])
        self.assertTrue(rec["clock_sync"]["ntp_synchronized"])
        Out = type("Out", (), {})

        def runner(cmd, **kw):
            out = Out()
            out.stdout, out.returncode = "no\n", 0
            return out

        self.assertEqual(recorder.read_clock_sync(runner),
                         {"ntp_synchronized": False, "source": "timedatectl"})

        def missing(cmd, **kw):
            raise FileNotFoundError

        from unittest import mock
        with mock.patch("os.path.exists", return_value=False):
            self.assertIsNone(recorder.read_clock_sync(missing)["ntp_synchronized"])
        with mock.patch("os.path.exists", return_value=True):
            self.assertEqual(recorder.read_clock_sync(missing),
                             {"ntp_synchronized": True, "source": "timesyncd_marker"})

    def test_fetch_rejects_foreign_host(self):
        with self.assertRaises(ValueError):
            recorder.fetch("https://example.com/x?a=1", 5)
        with self.assertRaises(ValueError):
            recorder.fetch("http://api.bitget.com/x?a=1", 5)

    def test_fsync_called_per_write(self):
        calls = []
        real = os.fsync
        os.fsync = lambda fd: (calls.append(fd), real(fd))[1]
        try:
            s = run(self.root, cycles=1, symbols=["BTCUSDT"])
        finally:
            os.fsync = real
        self.assertGreaterEqual(len(calls), s["records"])


class CoverageTests(unittest.TestCase):
    def points(self, times_s):
        return [(t * 1000, t * 1000) for t in times_s]

    def test_full_and_partial_coverage_with_gap_exclusion(self):
        base = 1_700_000_000 // 3600 * 3600
        times = list(range(base, base + 1800, 10)) + list(range(base + 2400, base + 3600, 10))
        cov = integrity_report.coverage(self.points(times), 60, 95.0)
        hour = cov["hour"][0]
        self.assertTrue(hour["below_threshold"])
        self.assertAlmostEqual(hour["coverage_pct"], 83.01, places=1)

    def test_complete_hour_meets_threshold_and_days(self):
        base = 1_700_000_000 // 86400 * 86400
        times = list(range(base, base + 7200 + 1, 30))
        cov = integrity_report.coverage(self.points(times), 60, 95.0)
        self.assertTrue(all(r["coverage_pct"] == 100 for r in cov["hour"]))
        self.assertEqual(cov["day"][0]["coverage_pct"], 100)

    def test_scan_flags_gap_and_threshold(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        recorder.STOP.clear()
        run(root, cycles=1, symbols=["BTCUSDT"], now_ns=lambda: NOW_NS)
        run(root, cycles=1, symbols=["BTCUSDT"], now_ns=lambda: NOW_NS + 600 * 10**9)
        rep = integrity_report.scan(root, 60, min_coverage_pct=50)
        self.assertEqual(rep["gaps"][0]["action"], "EXCLUDE")
        self.assertIn("never interpolate", rep["policy"])
        self.assertFalse(rep["coverage_ok"])
        self.assertEqual(rep["low_coverage_buckets"][0]["coverage_pct"], 0)
        with contextlib.redirect_stdout(io.StringIO()):
            code = integrity_report.main([str(root), "--min-coverage-pct", "50"])
        self.assertEqual(code, 3)
        self.assertTrue(integrity_report.scan(root, 1000)["coverage_ok"])


if __name__ == "__main__":
    unittest.main()
