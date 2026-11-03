import base64
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from research.archive_listing_probe import (
    LIMIT, OUTPUT, PAGE_CLIENT, SHARED_CLIENT, Probe, ProbeError, guard,
    parse_listing, review,
    public_headers,
)


class Response:
    def __init__(self, status=200, body=b"source", headers=None):
        self.status, self.body = status, body
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def getheaders(self):
        return list(self.headers.items())

    def read1(self, size):
        value, self.body = self.body[:size], self.body[size:]
        return value


class Connection:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class ProbeTests(unittest.TestCase):
    def test_sensitive_headers_are_excluded_without_changing_public_headers(self):
        self.assertEqual(
            public_headers({"Set-Cookie": "test", "Authorization": "test", "Content-Type": "text/plain"}),
            {"Content-Type": "text/plain"},
        )

    def request(self, response, probe=None):
        probe = probe or Probe()
        connection = Connection(response)
        return probe, connection, lambda *args, **kwargs: connection

    def test_exact_source_gets_only(self):
        for url in (PAGE_CLIENT, SHARED_CLIENT):
            guard("GET", url)
        for method, url, body in [
            ("POST", "https://www.bitget.com/v1/statistics/public/download/getPublicDataV2", b"{}"),
            ("GET", PAGE_CLIENT + "?x=1", None),
            ("GET", PAGE_CLIENT + "#fragment", None),
            ("GET", PAGE_CLIENT.replace("www.bitget.com", "api.bitget.com"), None),
            ("GET", PAGE_CLIENT.replace("www.bitget.com", "user@www.bitget.com"), None),
            ("DELETE", PAGE_CLIENT, None), ("GET", PAGE_CLIENT, b"{}"),
        ]:
            with self.subTest(url=url, method=method), self.assertRaises(ProbeError):
                guard(method, url, body)

    def test_raw_capture_hash_and_no_credentials(self):
        p, c, factory = self.request(Response(
            body=b"\x00\xffraw", headers={"Set-Cookie": "test", "Content-Type": "text/plain"},
        ))
        raw = p.request("GET", PAGE_CLIENT, connection_factory=factory)
        record = p.artifact["requests"][0]
        self.assertEqual(record["response_headers"], {"Content-Type": "text/plain"})
        self.assertEqual(raw, base64.b64decode(record["raw_response_base64"]))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), record["raw_response_sha256"])
        self.assertEqual(c.calls[0][1]["headers"], {"Accept-Encoding": "identity"})
        self.assertTrue(c.closed)
        self.assertEqual(p.artifact["budget"]["body_bytes"], len(raw))
        with self.assertRaises(ProbeError):
            p.request("GET", PAGE_CLIENT, connection_factory=factory)
        self.assertEqual(len(c.calls), 1)

    def test_non200_and_redirect_not_followed(self):
        for status in (301, 404, 405, 500):
            p, c, factory = self.request(Response(status, b"error", {"Location": "https://example.org"}))
            with self.assertRaises(ProbeError):
                p.request("GET", PAGE_CLIENT, connection_factory=factory)
            self.assertEqual(len(c.calls), 1)
            self.assertEqual(p.artifact["budget"]["transactions"], 1)
            self.assertEqual(p.artifact["requests"][0]["raw_response_bytes"], 5)
            self.assertTrue(c.closed)

    def test_budget_guards_before_network(self):
        for key, value in (("transactions", 10), ("body_bytes", LIMIT)):
            p = Probe()
            p.artifact["budget"][key] = value
            with self.assertRaises(ProbeError):
                p.request("GET", PAGE_CLIENT, connection_factory=lambda *a, **k: self.fail("network"))

    def test_declared_oversize(self):
        p, c, factory = self.request(Response(headers={"Content-Length": str(LIMIT + 1)}))
        with self.assertRaises(ProbeError):
            p.request("GET", PAGE_CLIENT, connection_factory=factory)
        self.assertEqual(p.artifact["budget"]["body_bytes"], 0)
        self.assertFalse(p.artifact["requests"][0].get("body_complete", False))

    def test_streaming_cumulative_oversize(self):
        p = Probe()
        p.artifact["budget"]["body_bytes"] = LIMIT - 3
        p, c, factory = self.request(Response(body=b"123456"), p)
        with self.assertRaises(ProbeError):
            p.request("GET", PAGE_CLIENT, connection_factory=factory)
        self.assertEqual(p.artifact["budget"]["body_bytes"], LIMIT)
        self.assertEqual(p.artifact["requests"][0]["raw_response_bytes"], 3)

    def test_deadline_is_whole_request_and_failure_preserved(self):
        p, c, factory = self.request(Response())
        c.getresponse = lambda: (_ for _ in ()).throw(TimeoutError("deadline"))
        with patch("research.archive_listing_probe.signal.setitimer") as timer:
            with self.assertRaises(ProbeError):
                p.request("GET", PAGE_CLIENT, connection_factory=factory)
            self.assertEqual(timer.call_args_list[0].args[1], 10)
        self.assertIn("TimeoutError", p.artifact["requests"][0]["error"])
        self.assertEqual(len(c.calls), 1)

    def test_api_error_non200_and_invalid_envelopes(self):
        for body, status in [
            (b'{"code":"00000","data":[]}', 405),
            (b'{"code":"40000","data":[]}', 200),
            (b'{"code":"00000","data":{}}', 200),
            (b"[]", 200), (b"not json", 200), (b"\xff", 200),
        ]:
            with self.subTest(body=body), self.assertRaises(ProbeError):
                parse_listing(body, status)
        self.assertEqual(parse_listing(b'{"code":"00000","data":[]}', 200), [])

    def test_saved_evidence_offline(self):
        artifact = json.loads(OUTPUT.read_text())
        for record in artifact["requests"]:
            self.assertEqual(record["response_headers"], public_headers(record["response_headers"]))
        review(artifact)
        self.assertEqual(artifact["budget"]["transactions"], 2)
        self.assertEqual(artifact["budget"]["post_requests"], 0)
        self.assertFalse(artifact["result"]["quote_coverage_claimed"])
        broken = copy.deepcopy(artifact)
        broken["requests"][0]["raw_response_sha256"] = "0" * 64
        with self.assertRaises(ProbeError):
            review(broken)
        broken = copy.deepcopy(artifact)
        broken["budget"]["body_bytes"] += 1
        with self.assertRaises(ProbeError):
            review(broken)


if __name__ == "__main__":
    unittest.main()
