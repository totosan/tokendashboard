import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.bitget_snapshot_recorder import record, validate


def payload():
    return {"code": "00000", "data": {"ts": "1000", "b": [["10", "2"]], "a": [["11", "3"]]}}


class RecorderTests(unittest.TestCase):
    def run_record(self, fetcher, samples=1):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "new"
            with patch("research.bitget_snapshot_recorder.time.time_ns", return_value=10**9):
                result = record(directory, "AAPLUSDT", samples, 1, 5, fetcher)
            saved = json.loads((directory / "manifest.json").read_text())
            raw = (directory / "snapshots.jsonl").read_bytes()
            self.assertEqual(saved, result)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), result["saved_jsonl_sha256"])
            return result, raw

    def test_complete_raw_capture_and_documented_read_only_route(self):
        source = json.dumps(payload()).encode()
        calls = []

        def fetch(url, timeout):
            calls.append(url)
            return source

        result, raw = self.run_record(fetch)
        self.assertEqual(result["status"], "COMPLETE_SAMPLED_SNAPSHOTS")
        item = json.loads(raw)
        self.assertEqual(base64.b64decode(item["raw_response_base64"]), source)
        self.assertEqual(item["raw_response_sha256"], hashlib.sha256(source).hexdigest())
        self.assertTrue(calls[0].startswith("https://api.bitget.com/api/v3/market/orderbook?"))
        self.assertIn("category=USDT-FUTURES", calls[0])

    def test_failures_persist_and_never_look_complete(self):
        for source in [b"{}", b"not-json", b'{"code":"40000"}']:
            result, raw = self.run_record(lambda *args: source)
            self.assertEqual(result["status"], "FAILED_PARTIAL")
            self.assertTrue(result["failures"])
            self.assertEqual(raw, b"")
        result, _ = self.run_record(lambda *args: (_ for _ in ()).throw(TimeoutError("timeout")))
        self.assertEqual(result["status"], "FAILED_PARTIAL")

    def test_bad_levels_and_crossed_books(self):
        for side in [[], [["0", "1"]], [["10", "-1"]], [["NaN", "1"]],
                     [["10", "1"], ["10", "2"]], [["9", "1"], ["10", "1"]]]:
            source = payload()
            source["data"]["b"] = side
            with self.subTest(side=side), self.assertRaises((ValueError, ArithmeticError)):
                validate(source, 5)
        source = payload()
        source["data"]["b"] = [["12", "1"]]
        with self.assertRaisesRegex(ValueError, "crossed"):
            validate(source, 5)

    def test_stale_snapshot_rejected(self):
        source = payload()
        source["data"]["ts"] = "1000000"
        result, _ = self.run_record(lambda *args: json.dumps(source).encode())
        self.assertEqual(result["status"], "FAILED_PARTIAL")

    def test_no_overwrite_and_bounds_before_network(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            with self.assertRaises(FileExistsError):
                record(path, "AAPLUSDT", 1, 1, 5)
            for samples, interval in [(0, 1), (3601, 1), (60, 61), (3600, 2)]:
                with self.assertRaises(ValueError):
                    record(path / "new", "AAPLUSDT", samples, interval, 5)
            with self.assertRaises(ValueError):
                record(path / "new", "../AAPLUSDT", 1, 1, 5)


if __name__ == "__main__":
    unittest.main()
