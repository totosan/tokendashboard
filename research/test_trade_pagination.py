import copy
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from research.trade_pagination import (
    Client, END_MS, ProbeError, START_MS, canonical, digest, run, validate_page,
)


def params():
    return {"symbol": "BTCUSDT", "productType": "USDT-FUTURES",
            "startTime": str(START_MS), "endTime": str(END_MS), "limit": "3"}


def response(ids=("100", "99", "98"), symbol="BTCUSDT"):
    return {"code": "00000", "data": [
        {"tradeId": value, "symbol": symbol, "ts": str(START_MS),
         "price": "1.25", "size": "0.01"} for value in ids
    ]}


class ValidationTests(unittest.TestCase):
    def test_numeric_order_and_derived_cursor(self):
        self.assertEqual(validate_page(response(), params(), set()), "98")

    def test_exclusive_boundary(self):
        for ids in (("100",), ("101",)):
            with self.subTest(ids=ids), self.assertRaisesRegex(ProbeError, "boundary"):
                validate_page(response(ids), {**params(), "idLessThan": "100"}, set())

    def test_duplicates_within_and_across_pages(self):
        for payload, seen in ((response(("99", "99")), set()), (response(), {99})):
            with self.subTest(seen=seen), self.assertRaisesRegex(ProbeError, "duplicate"):
                validate_page(payload, params(), seen)

    def test_exact_timestamp_window(self):
        for ts in (START_MS - 1, END_MS):
            payload = response()
            payload["data"][0]["ts"] = str(ts)
            with self.subTest(ts=ts), self.assertRaisesRegex(ProbeError, "timestamp"):
                validate_page(payload, params(), set())
        payload["data"][0]["ts"] = str(END_MS - 1)
        validate_page(payload, params(), set())

    def test_invalid_finite_positive_fields(self):
        for field in ("price", "size"):
            for value in ("NaN", "Infinity", "-Infinity", "0", "-1", "bad", None):
                payload = response()
                payload["data"][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ProbeError):
                    validate_page(payload, params(), set())

    def test_wrong_symbol_api_code_and_order(self):
        for payload in (response(symbol="AAPLUSDT"), {"code": "40000", "data": []},
                        response(("98", "99")), response(())):
            with self.subTest(payload=payload), self.assertRaises(ProbeError):
                validate_page(payload, params(), set())

    def test_invalid_integer_ids(self):
        for value in ("1.5", "-1", "0", "NaN", 1, True):
            with self.subTest(value=value), self.assertRaises(ProbeError):
                validate_page(response((value,)), params(), set())

    def test_failed_validation_does_not_mutate_seen(self):
        seen = {123}
        payload = response()
        payload["data"][-1]["size"] = "NaN"
        with self.assertRaises(ProbeError):
            validate_page(payload, params(), seen)
        self.assertEqual(seen, {123})


class Reply:
    code = 200

    def __init__(self, url, payload):
        self.url = url
        self.payload = payload

    def geturl(self):
        return self.url

    def read(self, limit):
        return json.dumps(self.payload).encode()[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ExecutionTests(unittest.TestCase):
    def test_sequential_requests_and_immutable_parameters(self):
        evidence = {"requests": [], "symbols": []}
        client = Client(evidence)

        def opened(request, timeout):
            query = parse_qs(urlsplit(request.full_url).query)
            ids = ("97", "96", "95") if "idLessThan" in query else ("100", "99", "98")
            return Reply(request.full_url, response(ids, query["symbol"][0]))

        with patch.object(client.opener, "open", side_effect=opened):
            run(client, evidence)
        self.assertEqual(evidence["status"], "verified")
        self.assertEqual(len(evidence["requests"]), 4)
        first = copy.deepcopy(evidence["requests"][0])
        self.assertNotIn("idLessThan", first["parameters"])
        self.assertEqual(evidence["requests"][1]["parameters"]["idLessThan"], "98")
        for record in evidence["requests"]:
            query = parse_qs(urlsplit(record["actual_url"]).query)
            self.assertEqual(query, {k: [v] for k, v in record["parameters"].items()})
            self.assertEqual(record["response_canonical_sha256"],
                             digest(canonical(record["response"])))

    def test_single_total_retry_and_honest_failure(self):
        evidence = {"requests": [], "symbols": []}
        client = Client(evidence)
        with patch.object(client.opener, "open", side_effect=URLError("offline")):
            run(client, evidence)
        self.assertEqual(len(evidence["requests"]), 3)
        self.assertEqual(evidence["status"], "failed")
        self.assertTrue(all(r["status"] == "failed" for r in evidence["requests"]))

    def test_budget_is_enforced_before_request(self):
        client = Client({"requests": [{} for _ in range(8)]})
        with patch.object(client.opener, "open") as opened, self.assertRaises(ProbeError):
            client.fetch(params(), 1)
        opened.assert_not_called()

    def test_bad_cursor_response_fails_without_retry(self):
        evidence = {"requests": [], "symbols": []}
        client = Client(evidence)

        def opened(request, timeout):
            query = parse_qs(urlsplit(request.full_url).query)
            return Reply(request.full_url, response(symbol=query["symbol"][0]))

        with patch.object(client.opener, "open", side_effect=opened):
            run(client, evidence)
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(len(evidence["requests"]), 4)
        self.assertIn("duplicate", evidence["requests"][1]["validation_error"])


if __name__ == "__main__":
    unittest.main()
