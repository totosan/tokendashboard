"""Third-party approximation of the Bitget USDT-futures universe in the saved window.

Two bounded GETs (Tardis exchange metadata, current Bitget /contracts), no redirects,
host allowlist, size cap, timeout. availableSince/availableTo are Tardis DATA
availability dates, not Bitget listing/delisting dates.
"""

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

TARDIS_URL = "https://api.tardis.dev/v1/exchanges/bitget-futures"
BITGET_URL = "https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES"
ALLOWED_HOSTS = {"api.tardis.dev", "api.bitget.com"}
MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 20
WINDOW_START = "2026-09-17"
WINDOW_END = "2026-11-01"
PANEL = ["AAPLUSDT", "ADAUSDT", "BNBUSDT", "BTCUSDT", "COINUSDT", "DOGEUSDT",
         "ETHUSDT", "LINKUSDT", "NVDAUSDT", "SOLUSDT", "TSLAUSDT", "XRPUSDT"]
OUTPUT = Path("research/data/bitget-universe-tardis-approx-2026-11-05.json")
TIER = "third-party approximation, not official PIT ledger"


class FetchError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(url, opener=None):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username:
        raise FetchError("host/scheme not allowed")
    opener = opener or urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            body = resp.read(MAX_BYTES + 1)
            status = resp.status
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}") from exc
    if status != 200:
        raise FetchError(f"HTTP {status}")
    if len(body) > MAX_BYTES:
        raise FetchError("response exceeds size cap")
    return body


def day(value):
    return value[:10] if value else None


def classify(symbol):
    if symbol["type"] == "future":
        return "future"
    sid = symbol["id"]
    if sid.endswith("USDT"):
        return "usdt_perpetual"
    return "other_perpetual"


def derive(symbols, panel=PANEL, inventory=None, start=WINDOW_START, end=WINDOW_END):
    rows = []
    for s in symbols:
        since, to = day(s.get("availableSince")), day(s.get("availableTo"))
        if since is None or since >= end:
            continue
        if to is not None and to < start:
            continue
        rows.append({"symbol": s["id"], "type": s["type"], "class": classify(s),
                     "since": since, "to": to})
    rows.sort(key=lambda r: r["symbol"])
    out = {"window_start_inclusive": start, "window_end_exclusive": end,
           "active_count": len(rows), "counts_by_class": {}, "active": {}}
    for r in rows:
        out["counts_by_class"][r["class"]] = out["counts_by_class"].get(r["class"], 0) + 1
        out["active"].setdefault(r["class"], []).append(r)
    ended = [r for r in rows if r["to"] is not None and r["to"] < end]
    started = [r for r in rows if r["since"] >= start]
    out["ended_in_window"] = ended
    out["started_in_window"] = started
    active_ids = {r["symbol"] for r in rows}
    panel_set = set(panel)
    usdt_ids = {r["symbol"] for r in rows if r["class"] == "usdt_perpetual"}
    out["panel_overlap"] = {
        "panel": sorted(panel_set),
        "panel_in_tardis_active": sorted(panel_set & active_ids),
        "panel_not_in_tardis_active": sorted(panel_set - active_ids),
        "usdt_perpetual_active_not_in_panel": len(usdt_ids - panel_set),
        "panel_share_of_usdt_perpetual_active": round(len(panel_set & usdt_ids) / len(usdt_ids), 6) if usdt_ids else None,
    }
    ended_usdt = [r for r in ended if r["class"] == "usdt_perpetual"]
    bias = {
        "ended_usdt_perpetual_in_window": len(ended_usdt),
        "ended_usdt_perpetual_not_in_panel": sorted(r["symbol"] for r in ended_usdt if r["symbol"] not in panel_set),
        "panel_symbols_ended_in_window": sorted(r["symbol"] for r in ended if r["symbol"] in panel_set),
        "panel_is_survivor_only": not any(r["symbol"] in panel_set for r in ended),
    }
    if inventory is not None:
        inv = set(inventory)
        missing = sorted(r["symbol"] for r in ended_usdt if r["symbol"] not in inv)
        bias["ended_usdt_perpetual_absent_from_current_contracts"] = missing
        bias["usdt_perpetual_active_absent_from_current_contracts"] = sorted(usdt_ids - inv)
        bias["current_contracts_not_in_tardis_active"] = sorted(inv - active_ids)
        bias["current_contracts_count"] = len(inv)
        bias["panel_not_in_current_contracts"] = sorted(panel_set - inv)
    out["survivor_bias_exposure"] = bias
    return out


def main():
    started = time.monotonic()
    raw = fetch(TARDIS_URL)
    meta = json.loads(raw)
    t_retrieved = datetime.now(timezone.utc).isoformat()
    inv_raw = fetch(BITGET_URL)
    inv_doc = json.loads(inv_raw)
    inventory = [c["symbol"] for c in inv_doc["data"]]
    result = {
        "schema_version": 1,
        "tier": TIER,
        "caveat": "availableSince/availableTo describe Tardis data availability, not Bitget listing/delisting; "
                  "dates are day-granular UTC. Not an official point-in-time ledger.",
        "issue": 10,
        "requests": [
            {"url": TARDIS_URL, "method": "GET", "retrieved_at_utc": t_retrieved,
             "bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
             "symbols_total": len(meta["availableSymbols"])},
            {"url": BITGET_URL, "method": "GET",
             "bytes": len(inv_raw), "raw_sha256": hashlib.sha256(inv_raw).hexdigest(),
             "symbols_total": len(inventory)},
        ],
        "derived": derive(meta["availableSymbols"], inventory=inventory),
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result["derived"][k] for k in ("active_count", "counts_by_class")}))
    print(json.dumps(result["derived"]["survivor_bias_exposure"], indent=1)[:1500])


if __name__ == "__main__":
    sys.exit(main())
