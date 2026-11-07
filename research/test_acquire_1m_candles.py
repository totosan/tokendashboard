import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import acquire_1m_candles as a


class Resp:
    def __init__(self, body):
        self.body, self.status = body, 200

    def __enter__(self):
        return self

    def __exit__(self, *x):
        return False

    def read(self, n=-1):
        return self.body[:n]


def page(end, n):
    rows = [[str(end - (i + 1) * 60_000), "1", "1", "1", "1", "1", "1"] for i in range(n)]
    return json.dumps({"code": "00000", "data": rows}).encode()


class AcquireTest(unittest.TestCase):
    def test_caps_and_pagination(self):
        calls = []

        def fake(req, timeout):
            calls.append((req.full_url, timeout))
            end = int(req.full_url.split("endTime=")[1].split("&")[0])
            return Resp(page(end, 200 if len(calls) < 3 else 5))

        with tempfile.TemporaryDirectory() as d, mock.patch.object(a, "urlopen", fake), \
                mock.patch.object(a.time, "sleep"):
            m = a.run(["BTCUSDT"], Path(d) / "raw", 10, 50)
            self.assertEqual(m["history_exhausted_symbols"], ["BTCUSDT"])
            self.assertEqual(m["coverage_by_symbol"]["BTCUSDT"]["gap_count"], 0)
            self.assertEqual(len(m["pages"][0]["sha256"]), 64)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(t == a.TIMEOUT for _, t in calls))

    def test_hard_caps_and_429_stop(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                a.run(["X"] * 13, Path(d) / "r", 1, 1)
            with self.assertRaises(ValueError):
                a.run(["X"], Path(d) / "r2", a.MAX_PAGES_PER_SYMBOL + 1, 1)
        err = a.HTTPError("u", 429, "x", {}, None)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(a, "urlopen", side_effect=err), \
                mock.patch.object(a.time, "sleep"):
            m = a.run(["BTCUSDT", "AAPLUSDT"], Path(d) / "raw", 3, 50)
            self.assertEqual(m["stop_reason"], "http_error_429")
            self.assertEqual(m["http_requests"], 1)


if __name__ == "__main__":
    unittest.main()
