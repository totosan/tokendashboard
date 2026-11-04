import gzip
import json
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
                now_ns=lambda: NOW_NS, min_gap=0, fetcher=good_fetch([]))
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


if __name__ == "__main__":
    unittest.main()
