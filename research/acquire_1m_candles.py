"""Bounded, read-only, anonymous public Bitget USDT-futures 1m candle acquisition.

Walks backwards from now in round-robin over symbols so depth is even when a cap
stops the run. Raw pages stay local (--directory, not committed); the manifest
holds only request parameters, byte counts, SHA-256 per page and coverage/gaps.
No credentials are read or sent. No retries.
"""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://api.bitget.com/api/v2/mix/market/history-candles"
PANEL = ["AAPLUSDT", "ADAUSDT", "BNBUSDT", "BTCUSDT", "COINUSDT", "DOGEUSDT",
         "ETHUSDT", "LINKUSDT", "NVDAUSDT", "SOLUSDT", "TSLAUSDT", "XRPUSDT"]
MINUTE = 60_000
PAGE = 200
MAX_SYMBOLS = 12
MAX_PAGES_PER_SYMBOL = 60
MAX_REQUESTS = 600
MAX_PAGE_BYTES = 256 * 1024
TIMEOUT = 10
MIN_INTERVAL = 1.0  # 0.12s tripped HTTP 429 after 14 requests on 2026-11-05
WALL = 105


def coverage(times, start, end):
    """Gap/duplicate summary over [start, end) in ms for sorted unique minute opens."""
    if not times:
        return {"bars": 0}
    gaps, prev = [], times[0]
    for t in times[1:]:
        if t - prev != MINUTE:
            gaps.append([prev + MINUTE, t])
        prev = t
    iso = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
    return {"bars": len(times), "first_open_utc": iso(times[0]), "last_open_utc": iso(times[-1]),
            "expected_bars_first_to_last": (times[-1] - times[0]) // MINUTE + 1,
            "gap_count": len(gaps), "missing_bars": sum((b - a) // MINUTE for a, b in gaps),
            "gaps_utc": [[iso(a), iso(b)] for a, b in gaps[:20]]}


def run(symbols, directory, pages, max_requests):
    if not 1 <= len(symbols) <= MAX_SYMBOLS or not 1 <= pages <= MAX_PAGES_PER_SYMBOL:
        raise ValueError("symbol/page count outside hard caps")
    max_requests = min(max_requests, MAX_REQUESTS)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    manifest = {"endpoint": ENDPOINT, "authentication": "none (public, read-only GET)",
                "started_utc": datetime.now(timezone.utc).isoformat(), "granularity": "1m",
                "productType": "USDT-FUTURES", "symbols": symbols,
                "caps": {"symbols": MAX_SYMBOLS, "pages_per_symbol": pages, "max_requests": max_requests,
                         "page_limit": PAGE, "timeout_s": TIMEOUT, "min_interval_s": MIN_INTERVAL,
                         "wall_s": WALL, "retries": 0},
                "pages": [], "stop_reason": None}
    state = {s: {"end": int(time.time() * 1000), "pages": 0, "done": False, "times": set()} for s in symbols}
    requests = 0
    last = 0.0
    while manifest["stop_reason"] is None:
        active = [s for s in symbols if not state[s]["done"] and state[s]["pages"] < pages]
        if not active:
            manifest["stop_reason"] = "page_cap_or_history_exhausted"
            break
        for sym in active:
            if requests >= max_requests:
                manifest["stop_reason"] = "request_cap"
                break
            if time.monotonic() - started >= WALL:
                manifest["stop_reason"] = "wall_cap"
                break
            time.sleep(max(0.0, MIN_INTERVAL - (time.monotonic() - last)))
            st = state[sym]
            params = {"symbol": sym, "productType": "USDT-FUTURES", "granularity": "1m",
                      "endTime": st["end"], "limit": PAGE}
            rec = {"symbol": sym, "endTime": st["end"], "limit": PAGE}
            requests += 1
            last = time.monotonic()
            try:
                with urlopen(Request(ENDPOINT + "?" + urlencode(params),
                                     headers={"User-Agent": "tokendashboard-research/1.0"}),
                             timeout=TIMEOUT) as resp:
                    body = resp.read(MAX_PAGE_BYTES + 1)
                    rec["http_status"] = resp.status
            except HTTPError as exc:
                rec.update(http_status=exc.code, status="HTTP_ERROR")
                manifest["pages"].append(rec)
                manifest["stop_reason"] = "http_error_%d" % exc.code
                break
            except (URLError, OSError) as exc:
                rec.update(status="NETWORK_ERROR", error_type=type(exc).__name__)
                manifest["pages"].append(rec)
                manifest["stop_reason"] = "network_error"
                break
            if len(body) > MAX_PAGE_BYTES:
                rec["status"] = "OVERSIZE"
                manifest["pages"].append(rec)
                manifest["stop_reason"] = "oversize_page"
                break
            rec.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            try:
                payload = json.loads(body)
                rows = payload["data"] if payload.get("code") == "00000" else None
                rec["api_code"] = payload.get("code")
                if rows is None:
                    raise ValueError(payload.get("msg"))
                opens = sorted(int(r[0]) for r in rows)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                rec.update(status="BAD_PAYLOAD", detail=str(exc)[:80])
                manifest["pages"].append(rec)
                manifest["stop_reason"] = "bad_payload"
                break
            name = "%s-%04d.json" % (sym, st["pages"])
            (directory / name).write_bytes(body)
            rec.update(status="OK", file=name, rows=len(opens))
            if opens:
                rec.update(first_open=opens[0], last_open=opens[-1])
            manifest["pages"].append(rec)
            st["pages"] += 1
            st["times"].update(opens)
            if len(opens) < PAGE:
                st["done"] = True
            else:
                st["end"] = opens[0]  # endTime is exclusive on the provider side; -1 dropped one bar per page
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    manifest["http_requests"] = requests
    manifest["elapsed_s"] = round(time.monotonic() - started, 1)
    manifest["coverage_by_symbol"] = {s: coverage(sorted(state[s]["times"]), None, None) for s in symbols}
    manifest["history_exhausted_symbols"] = [s for s in symbols if state[s]["done"]]
    manifest["limitations"] = ["Raw pages are local only; reacquisition may differ (rolling window, revisions)",
                               "Depth is bounded by caps, not necessarily by provider history",
                               "Completeness beyond observed bars is not certified; gaps are reported, not filled"]
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--directory", type=Path, required=True, help="new local directory for raw pages + manifest")
    ap.add_argument("--symbols", nargs="+", default=PANEL)
    ap.add_argument("--pages", type=int, default=48)
    ap.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    a = ap.parse_args()
    m = run(a.symbols, a.directory, a.pages, a.max_requests)
    print(json.dumps({"stop_reason": m["stop_reason"], "requests": m["http_requests"],
                      "manifest": str(a.directory / "manifest.json")}))


if __name__ == "__main__":
    main()
