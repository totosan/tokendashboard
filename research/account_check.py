"""Finite, read-only Bitget private-API account check (issue #7).

Cloud-agent usage (env: BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PHRASE;
the key MUST be read-only):

    timeout --signal=TERM --kill-after=5s 90 python research/account_check.py

Exit codes: 0 ok, 1 request/runtime failure, 3 missing credentials.
Only GET requests to a hard-coded path allowlist on api.bitget.com are sent.
Output research/results/account-check-<date>.json holds only fee rates,
presence flags, counts and a content sha256. No secret, signature,
passphrase, balance or identifier is printed or written.
Endpoint names are from Bitget v2 docs as known; marked unverified in output.
"""
import base64
import hashlib
import hmac
import http.client
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

HOST = "api.bitget.com"
ALLOWED_PATHS = frozenset({
    "/api/v2/common/trade-rate",
    "/api/v2/mix/account/accounts",
    "/api/v2/mix/account/bill",
    "/api/v2/spot/account/info",
    "/api/v3/account/settings",
    "/api/v3/account/fee-rate",
})
MAX_REQUESTS = 8
MIN_INTERVAL = 0.3
TIMEOUT = 10
WALL_CAP = 60
SYMBOLS = ("AAPLUSDT", "BTCUSDT")
ENV = ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_API_PHRASE")
DANGEROUS = ("trade", "withdraw", "transfer")


def sign(secret, timestamp, method, path, query="", body=""):
    msg = timestamp + method.upper() + path + ("?" + query if query else "") + body
    digest = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def salted_hash(value, salt):
    return hashlib.sha256((salt + str(value)).encode()).hexdigest()[:12]


class Client:
    def __init__(self, key, secret, phrase, conn_factory=None, clock=time.time, sleep=time.sleep):
        self._key, self._secret, self._phrase = key, secret, phrase
        self._factory = conn_factory or (lambda: http.client.HTTPSConnection(HOST, timeout=TIMEOUT))
        self._clock, self._sleep = clock, sleep
        self.start = clock()
        self.count = 0
        self._last = 0.0

    def get(self, path, params=None, method="GET"):
        if method != "GET":
            raise ValueError("only GET allowed")
        if path not in ALLOWED_PATHS:
            raise ValueError("path not allowed")
        if self.count >= MAX_REQUESTS:
            raise RuntimeError("request budget exhausted")
        if self._clock() - self.start > WALL_CAP:
            raise RuntimeError("wall cap exceeded")
        wait = MIN_INTERVAL - (self._clock() - self._last)
        if wait > 0:
            self._sleep(wait)
        query = urlencode(params or {})
        ts = str(int(self._clock() * 1000))
        headers = {
            "ACCESS-KEY": self._key,
            "ACCESS-SIGN": sign(self._secret, ts, "GET", path, query),
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self._phrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }
        conn = self._factory()
        self.count += 1
        self._last = self._clock()
        try:
            conn.request("GET", path + ("?" + query if query else ""), headers=headers)
            resp = conn.getresponse()
            raw = resp.read(1_000_000)
            status = resp.status
        finally:
            conn.close()
        if 300 <= status < 400:
            raise RuntimeError("redirect refused")
        try:
            data = json.loads(raw)
        except ValueError:
            raise RuntimeError("non-JSON response (HTTP %d)" % status)
        if status != 200 or data.get("code") != "00000":
            raise RuntimeError("API error HTTP %d code %s" % (status, data.get("code")))
        return data.get("data")


def first(data):
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}


def check_fees(client):
    out = {}
    for sym in SYMBOLS:
        try:
            d = first(client.get("/api/v3/account/fee-rate",
                                 {"symbol": sym, "category": "USDT-FUTURES"}))
        except RuntimeError:
            d = first(client.get("/api/v2/common/trade-rate",
                                 {"symbol": sym, "businessType": "mix"}))
        out[sym] = {"makerFeeRate": d.get("makerFeeRate"), "takerFeeRate": d.get("takerFeeRate")}
    return out


def safe(fn, *args):
    """Classic v2 account endpoints are rejected (40085) on Unified Trading Accounts."""
    try:
        return fn(*args)
    except RuntimeError as exc:
        return {"unavailable": str(exc)[:60], "warnings": []}


def check_uta_settings(client):
    d = first(client.get("/api/v3/account/settings"))
    return {"assetMode": d.get("assetMode"), "holdMode": d.get("holdMode"),
            "accountMode": d.get("accountMode"), "accountLevel": d.get("accountLevel"),
            "symbolConfigCount": len(d.get("symbolConfigList") or [])}


def check_mix_account(client):
    data = client.get("/api/v2/mix/account/accounts", {"productType": "USDT-FUTURES"})
    rows = data if isinstance(data, list) else []
    return {
        "accountCount": len(rows),
        "marginModes": sorted({str(r.get("marginMode")) for r in rows if r.get("marginMode")}),
        "positionModes": sorted({str(r.get("posMode")) for r in rows if r.get("posMode")}),
        "marginCoins": sorted({str(r.get("marginCoin")) for r in rows if r.get("marginCoin")}),
        "balancePresent": any(r.get("available") not in (None, "") for r in rows),
    }


def check_bills(client, now_ms):
    data = client.get("/api/v2/mix/account/bill", {
        "productType": "USDT-FUTURES", "businessType": "contract_settle_fee",
        "startTime": str(now_ms - 7 * 86400 * 1000), "endTime": str(now_ms), "limit": "100"})
    bills = (data or {}).get("bills", []) if isinstance(data, dict) else []
    return {"fundingEntries7d": len(bills), "truncatedAtLimit": len(bills) >= 100}


def check_permissions(client):
    """Spot account info lists API-key authorities; flag anything beyond read."""
    d = first(client.get("/api/v2/spot/account/info"))
    auth = d.get("authorities")
    if auth is None:
        return {"authoritiesPresent": False, "warnings": []}
    auth = [str(a) for a in auth]
    bad = [a for a in auth if any(w in a.lower() for w in DANGEROUS)]
    warn = ["WARNING: key has non-read permission(s): " + ", ".join(bad)] if bad else []
    return {"authoritiesPresent": True, "authorityCount": len(auth),
            "nonReadPermissions": bad, "warnings": warn}


def run(client, now=None):
    now = now or datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    result = {
        "generatedAt": now.isoformat(),
        "endpointsUnverified": True,
        "fees": check_fees(client),
        "utaSettings": safe(check_uta_settings, client),
        "mixAccount": safe(check_mix_account, client),
        "fundingBills": safe(check_bills, client, now_ms),
        "permissions": safe(check_permissions, client),
    }
    result["requestCount"] = client.count
    result["warnings"] = result["permissions"].get("warnings", [])
    body = json.dumps(result, sort_keys=True)
    result["contentSha256"] = hashlib.sha256(body.encode()).hexdigest()
    return result


def write(result, outdir):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "account-check-%s.json" % result["generatedAt"][:10])
    with open(path, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    return path


def main():
    missing = [n for n in ENV if not os.environ.get(n)]
    if missing:
        print("Missing required env vars: " + ", ".join(missing), file=sys.stderr)
        return 3
    client = Client(*(os.environ[n] for n in ENV))
    try:
        result = run(client)
    except Exception as e:
        print("account check failed: %s" % type(e).__name__ + ": " + str(e)[:120], file=sys.stderr)
        return 1
    here = os.path.dirname(os.path.abspath(__file__))
    print("wrote", write(result, os.path.join(here, "results")))
    for w in result["warnings"]:
        print(w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
