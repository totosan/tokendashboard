import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from research import account_check as ac

SECRET, PHRASE, KEY = "s3cr3t-x", "phrase-x", "key-x"


class FakeResp:
    def __init__(self, payload, status=200):
        self.status, self._raw = status, json.dumps(payload).encode()

    def read(self, n=-1):
        return self._raw


class FakeConn:
    log = []

    def __init__(self, router):
        self.router = router

    def request(self, method, url, headers=None):
        FakeConn.log.append((method, url, headers))
        self.url = url

    def getresponse(self):
        return self.router(self.url)

    def close(self):
        pass


def router(url):
    ok = lambda d: FakeResp({"code": "00000", "data": d})
    if "v3/account/fee-rate" in url:
        return ok({"makerFeeRate": "0.0002", "takerFeeRate": "0.0006"})
    if "v3/account/settings" in url:
        return ok({"assetMode": "multi_assets", "holdMode": "hedge_mode", "uid": "999",
                   "symbolConfigList": []})
    if "trade-rate" in url:
        return ok({"makerFeeRate": "0.0002", "takerFeeRate": "0.0006"})
    if "mix/account/accounts" in url:
        return ok([{"marginMode": "crossed", "posMode": "one_way_mode", "marginCoin": "USDT",
                    "available": "123.4", "userId": "999"}])
    if "bill" in url:
        return ok({"bills": [{"amount": "1"}, {"amount": "2"}]})
    if "spot/account/info" in url:
        return ok({"userId": "999", "authorities": ["readonly", "trade"]})
    return FakeResp({"code": "1"}, 404)


def make_client(r=router):
    FakeConn.log = []
    t = [1000.0]

    def clock():
        t[0] += 0.01
        return t[0]
    return ac.Client(KEY, SECRET, PHRASE, lambda: FakeConn(r), clock, lambda s: None)


class Tests(unittest.TestCase):
    def test_sign(self):
        exp = base64.b64encode(hmac.new(b"k", b"1GET/p?a=1", hashlib.sha256).digest()).decode()
        self.assertEqual(ac.sign("k", "1", "get", "/p", "a=1"), exp)

    def test_refusals(self):
        c = make_client()
        with self.assertRaises(ValueError):
            c.get("/api/v2/spot/trade/place-order")
        with self.assertRaises(ValueError):
            c.get("/api/v2/common/trade-rate", method="POST")
        self.assertEqual(FakeConn.log, [])

    def test_budget(self):
        c = make_client()
        for _ in range(ac.MAX_REQUESTS):
            c.get("/api/v2/spot/account/info")
        with self.assertRaises(RuntimeError):
            c.get("/api/v2/spot/account/info")

    def test_redirect_and_error(self):
        with self.assertRaisesRegex(RuntimeError, "redirect"):
            make_client(lambda u: FakeResp({}, 302)).get("/api/v2/spot/account/info")
        with self.assertRaisesRegex(RuntimeError, "API error"):
            make_client(lambda u: FakeResp({"code": "40009"}, 400)).get("/api/v2/spot/account/info")

    def test_run_output_clean(self):
        c = make_client()
        res = ac.run(c)
        self.assertEqual(res["requestCount"], 6)
        self.assertEqual(res["fees"]["AAPLUSDT"]["takerFeeRate"], "0.0006")
        self.assertEqual(res["fundingBills"]["fundingEntries7d"], 2)
        self.assertTrue(res["warnings"])
        self.assertTrue(all(m == "GET" for m, _, _ in FakeConn.log))
        text = json.dumps(res)
        for bad in (SECRET, PHRASE, KEY, "999", "123.4"):
            self.assertNotIn(bad, text)
        for _, _, h in FakeConn.log:
            self.assertEqual(h["ACCESS-PASSPHRASE"], PHRASE)
        with tempfile.TemporaryDirectory(dir=os.path.dirname(__file__)) as d:
            p = ac.write(res, d)
            self.assertIn("account-check-", p)

    def test_missing_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ac.main(), 3)

    def test_salted_hash(self):
        self.assertNotIn("999", ac.salted_hash("999", "salt"))


if __name__ == "__main__":
    unittest.main()
