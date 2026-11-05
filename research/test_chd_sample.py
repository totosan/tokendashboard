import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from research.chd_sample import BudgetRedirects, acquire, validate_object

OBJECT = "bitget_futures/2026-09-17/14/AAPLUSDT_trades.parquet"


class Response(io.BytesIO):
    status = 200


class SampleTests(unittest.TestCase):
    def run_acquisition(self, effects, objects=None, inspection=None):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "new"
            with patch.dict(sys.modules, {"pyarrow": types.SimpleNamespace(__version__="test")}), \
                    patch("research.chd_sample.build_opener") as opener, \
                    patch("research.chd_sample.inspect_parquet",
                          return_value=inspection or {"status": "OBSERVED", "rows": 1}):
                opener.return_value.open.side_effect = effects
                report = acquire(objects or [OBJECT], target)
                self.assertEqual(report, json.loads((target / "manifest.json").read_text()))
                return report, opener.return_value.open.call_args_list

    def test_exact_anonymous_request_hash_and_new_directory(self):
        report, calls = self.run_acquisition([Response(b"data")])
        record = report["objects"][0]
        self.assertEqual(record["bytes"], 4)
        self.assertEqual(record["http_status"], 200)
        self.assertEqual(len(record["sha256"]), 64)
        self.assertEqual(report["status"], "BOUNDED_SAMPLE_OBSERVED")
        request = calls[0].args[0]
        self.assertTrue(request.full_url.startswith("https://api.cryptohftdata.com/v1/download?file="))
        self.assertNotIn("Authorization", request.headers)

    def test_missing_failed_empty_and_rate_limit_are_distinct(self):
        other = OBJECT.replace("/14/", "/15/")
        missing = HTTPError("https://example.test", 404, "missing", {}, None)
        report, _ = self.run_acquisition([missing, URLError("failed")], [OBJECT, other])
        self.assertEqual([r["status"] for r in report["objects"]], ["MISSING", "DOWNLOAD_OR_VALIDATION_FAILED"])
        limited = HTTPError("https://example.test", 429, "limited", {"Retry-After": "60"}, None)
        report, calls = self.run_acquisition([limited], [OBJECT, other])
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["objects"][0]["retry_after"], "60")
        self.assertEqual(report["objects"][1]["status"], "NOT_REQUESTED_BUDGET_OR_RATE_LIMIT")
        report, _ = self.run_acquisition([Response(b"data")],
                                         inspection={"status": "EMPTY", "rows": 0})
        self.assertEqual(report["objects"][0]["status"], "EMPTY")
        self.assertEqual(report["status"], "PARTIAL_OR_UNAVAILABLE")

    def test_byte_budget_stops_without_success_report(self):
        with patch("research.chd_sample.MAX_BYTES", 3):
            report, _ = self.run_acquisition([Response(b"1234")])
        self.assertEqual(report["status"], "PARTIAL_OR_UNAVAILABLE")
        self.assertEqual(report["objects"][0]["status"], "DOWNLOAD_OR_VALIDATION_FAILED")

    def test_paths_reserved_outcomes_duplicates_and_existing_cache_refused(self):
        for value in (OBJECT.replace("2026-09-17", "2027-02-01"),
                      OBJECT.replace("/14/", "/24/"), "../" + OBJECT, OBJECT + "?api_key=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_object(value)
        with self.assertRaises(ValueError):
            acquire([OBJECT, OBJECT], Path("not-created"))
        with tempfile.TemporaryDirectory() as root, \
                patch.dict(sys.modules, {"pyarrow": types.SimpleNamespace(__version__="test")}), \
                self.assertRaises(FileExistsError):
            acquire([OBJECT], Path(root))

    def test_eight_objects_allowed_nine_refused_and_budgets_recorded(self):
        names = [OBJECT.replace("/14/", f"/{h}/").replace("AAPL", s)
                 for s in ("AAPL", "BTC") for h in ("13", "14", "15", "16")]
        report, calls = self.run_acquisition([Response(b"d") for _ in names], names)
        self.assertEqual(len(calls), 8)
        self.assertEqual(report["budgets"]["objects"], 8)
        self.assertEqual(report["budgets"]["http_transactions"], 16)
        self.assertEqual(report["budgets"]["total_bytes"], 16 * 1024 * 1024)
        with self.assertRaises(ValueError):
            acquire(names + [OBJECT.replace("/14/", "/12/")], Path("not-created"))

    def test_redirect_budget_and_plain_http_refused(self):
        redirect = BudgetRedirects()
        request = Request("https://api.cryptohftdata.com/")
        with self.assertRaises(ValueError):
            redirect.redirect_request(request, None, 302, "", {}, "http://example.test")
        redirect.transactions = 16
        with self.assertRaises(ValueError):
            redirect.redirect_request(request, None, 302, "", {}, "https://example.test")

    def test_interruption_leaves_requested_object_and_in_progress_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "new"
            with patch.dict(sys.modules, {"pyarrow": types.SimpleNamespace(__version__="test")}), \
                    patch("research.chd_sample.build_opener") as opener:
                opener.return_value.open.side_effect = KeyboardInterrupt
                with self.assertRaises(KeyboardInterrupt):
                    acquire([OBJECT], target)
            report = json.loads((target / "manifest.json").read_text())
            self.assertEqual(report["requested_objects"], [OBJECT])
            self.assertEqual(report["status"], "IN_PROGRESS")
            self.assertEqual(report["objects"][0]["status"], "IN_PROGRESS")


if __name__ == "__main__":
    unittest.main()
