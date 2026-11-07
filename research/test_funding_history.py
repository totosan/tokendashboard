import base64
import hashlib
import json
import unittest
from unittest.mock import patch
from research.funding_history import (
    Collector, START, END, SYMBOLS, coverage, merge_page, validate_page,
)


def row(stamp=START, rate="0.0001", symbol="BTCUSDT"):
    return {"symbol": symbol, "fundingTime": str(stamp), "fundingRate": rate}


class FundingTests(unittest.TestCase):
    def test_overlap_and_contradiction(self):
        seen = {}
        self.assertEqual(merge_page(seen, [(START, "0.1"), (START, ".10")]), 1)
        self.assertEqual(merge_page(seen, [(START, ".1"), (START - 1, ".2")], START), 1)
        with self.assertRaisesRegex(ValueError, "contradictory"):
            merge_page(seen, [(START, ".3")])

    def test_bad_values(self):
        for bad in (row(symbol="ETHUSDT"), row(rate="NaN"), row(rate="Infinity"),
                    row(rate="oops"), row(rate=None), row(rate=True),
                    row(stamp=1), row(stamp=END + 1), row(stamp="1.5")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_page([bad], "BTCUSDT", END)
        with self.assertRaises(ValueError):
            validate_page([], "UNKNOWN", END)

    def test_order_and_stalled_pages(self):
        with self.assertRaises(ValueError):
            validate_page([row(START), row(START + 1)], "BTCUSDT", END)
        with self.assertRaisesRegex(ValueError, "backwards"):
            merge_page({START: ".1"}, [(START, ".1")], START)
        with self.assertRaisesRegex(ValueError, "forward"):
            merge_page({START: ".1"}, [(START + 1, ".1"), (START - 1, ".1")], START)

    def test_window_boundaries_and_gaps(self):
        step = 8 * 3600000
        seen = {t: ".1" for t in range(START - step, END + step, step)}
        result = coverage(seen, step, True)
        self.assertEqual(result["window_rows"], 135)
        self.assertTrue(result["grid_match_only"])
        self.assertEqual(result["rows"][0]["fundingTime"], START)
        self.assertLess(result["rows"][-1]["fundingTime"], END)
        self.assertTrue(result["excluded_end_boundary_present"])
        del seen[START + step]
        result = coverage(seen, step, True)
        self.assertEqual(len(result["missing_provisional_grid_utc"]), 1)
        self.assertEqual(len(result["observed_interval_deviations"]), 1)
        self.assertIn("unverified", result["historical_completeness"])
        seen[START + 1] = ".2"
        self.assertEqual(len(coverage(seen, step, True)["off_provisional_grid_utc"]), 1)

    def test_empty(self):
        result = coverage({}, 8 * 3600000, False)
        self.assertFalse(result["grid_match_only"])
        self.assertEqual(len(result["missing_provisional_grid_utc"]), 135)

    def test_collection_pagination_and_failure_persistence(self):
        class Fake(Collector):
            def __init__(self, fail=False):
                super().__init__(None)
                self.calls = []
                self.fail = fail

            def save(self):
                self.saved = True

            def get(self, endpoint, parameters):
                self.calls.append(dict(parameters))
                self.report["request_count"] += 1
                if "symbol" not in parameters:
                    return {"data": [{"symbol": s, "category": "USDT-FUTURES",
                                      "type": "perpetual", "fundInterval": "8"} for s in SYMBOLS]}
                if self.fail:
                    raise RuntimeError("endpoint unavailable")
                all_rows = [row(t, symbol=parameters["symbol"])
                            for t in range(END, START - 9 * 3600000, -8 * 3600000)]
                n = parameters["pageNo"]
                return {"data": all_rows[(n - 1) * 100:n * 100]}

        collector = Fake()
        self.assertEqual(collector.run(), 0)
        self.assertEqual(collector.report["request_count"], 25)
        self.assertEqual(collector.calls[2]["pageNo"], 2)
        self.assertEqual(collector.report["symbols"]["BTCUSDT"]["window_rows"], 135)
        failed = Fake(True)
        self.assertEqual(failed.run(), 1)
        self.assertTrue(failed.saved)
        self.assertEqual(failed.report["symbols"]["COINUSDT"]["status"], "not_collected")

    def test_hard_budget(self):
        collector = Collector(None)
        collector.report["request_count"] = 36
        with self.assertRaisesRegex(RuntimeError, "budget"):
            collector.get("/api/v3/market/instruments", {})

    def test_transport_failure_retry_evidence(self):
        collector = Collector(None)
        with patch.object(collector, "save"), patch.object(
            collector.opener, "open", side_effect=TimeoutError("fixture timeout")
        ) as opened:
            with self.assertRaisesRegex(RuntimeError, "fixture timeout"):
                collector.get("/api/v3/market/instruments", {"category": "USDT-FUTURES"})
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(collector.report["request_count"], 2)
        for request in collector.report["requests"]:
            self.assertIn("error", request)
            self.assertIn("finished_utc", request)
            self.assertIn("category=USDT-FUTURES", request["url"])

    def test_api_failure_and_raw_hashes(self):
        raw = b'{"code":"40000","msg":"failure","data":[]}'

        class Response:
            code = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return raw

        collector = Collector(None)
        with patch.object(collector, "save"), patch.object(
            collector.opener, "open", side_effect=[Response(), Response()]
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP/API failure"):
                collector.get("/api/v3/market/instruments", {})
        self.assertEqual(collector.report["request_count"], 2)
        request = collector.report["requests"][0]
        self.assertEqual(base64.b64decode(request["raw_response_base64"]), raw)
        self.assertEqual(request["raw_response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(request["response"], json.loads(raw))
        self.assertEqual(request["api_code"], "40000")

    def test_retry_cannot_exceed_budget(self):
        collector = Collector(None)
        collector.report["request_count"] = 35
        with patch.object(collector, "save"), patch.object(
            collector.opener, "open", side_effect=TimeoutError("failure")
        ) as opened:
            with self.assertRaisesRegex(RuntimeError, "budget"):
                collector.get("/api/v3/market/instruments", {})
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(collector.report["request_count"], 36)


if __name__ == "__main__":
    unittest.main()
