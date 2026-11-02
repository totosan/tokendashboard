#!/usr/bin/env python3
"""Bounded public Bitget funding evidence for #16 (standard library only).

Run: timeout 300s python research/funding_history.py
The fixed window is [2026-09-17T00:00Z, 2026-11-01T00:00Z).
Current metadata is a PROVISIONAL historical grid, not a schedule-change log.
Even an exact grid match cannot establish historical completeness. Differences
may represent missing records OR schedule changes; neither is silently repaired.

Hypothetical holdings may assign settlements to [entry, exit), including entry
and excluding exit. This is a scenario convention, NOT verified venue ownership.
Public rates are not account cashflows: position, notional, actual ownership and
account-ledger evidence would be needed. No funding P&L is computed here.
"""

import base64
import hashlib
import json
import signal
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT",
    "SOLUSDT", "BNBUSDT", "TSLAUSDT", "NVDAUSDT", "AAPLUSDT", "COINUSDT",
)
START = 1789603200000
END = 1793491200000
BASE = "https://api.bitget.com"
METADATA = "/api/v3/market/instruments"
HISTORY = "/api/v2/mix/market/history-fund-rate"
ROOT = Path(__file__).resolve().parent


def utc(ms=None):
    value = datetime.now(timezone.utc) if ms is None else datetime.fromtimestamp(ms / 1000, timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def validate_page(rows, symbol, now_ms):
    if symbol not in SYMBOLS or not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("invalid requested symbol or page shape/size")
    result = []
    for row in rows:
        if not isinstance(row, dict) or row.get("symbol") != symbol:
            raise ValueError("invalid response symbol")
        raw_time = row.get("fundingTime")
        if isinstance(raw_time, bool) or not str(raw_time).isdigit():
            raise ValueError("invalid funding timestamp")
        stamp = int(raw_time)
        if stamp < 1000000000000 or stamp > now_ms:
            raise ValueError("timestamp outside plausible millisecond history")
        raw_rate = row.get("fundingRate")
        if not isinstance(raw_rate, (str, int, float)) or isinstance(raw_rate, bool):
            raise ValueError("invalid funding rate")
        try:
            rate = Decimal(str(raw_rate))
        except InvalidOperation as exc:
            raise ValueError("invalid funding rate") from exc
        if not rate.is_finite():
            raise ValueError("non-finite funding rate")
        result.append((stamp, str(rate)))
    if any(a[0] < b[0] for a, b in zip(result, result[1:])):
        raise ValueError("page must be reverse chronological")
    return result


def merge_page(seen, page, previous_oldest=None):
    """Identical overlap is accepted; conflicting same-time rates are fatal."""
    overlap = 0
    old_keys = set(seen)
    if page and previous_oldest is not None:
        if any(t > previous_oldest and t not in old_keys for t, _ in page):
            raise ValueError("page moved forward with previously unseen records")
        if min(t for t, _ in page) >= previous_oldest:
            raise ValueError("pagination did not move backwards")
    for stamp, rate in page:
        if stamp in seen:
            if Decimal(seen[stamp]) != Decimal(rate):
                raise ValueError("contradictory funding rates at same timestamp")
            overlap += 1
        else:
            seen[stamp] = rate
    return overlap


def coverage(seen, interval_ms, crossed_start):
    stamps = sorted(t for t in seen if START <= t < END)
    # UTC epoch alignment is explicitly a scenario, not metadata-proven phase.
    first = ((START + interval_ms - 1) // interval_ms) * interval_ms
    expected = set(range(first, END, interval_ms))
    missing = sorted(expected - set(stamps))
    off_grid = sorted(set(stamps) - expected)
    gaps = [
        {"from_utc": utc(a), "to_utc": utc(b), "elapsed_ms": b - a}
        for a, b in zip(stamps, stamps[1:]) if b - a != interval_ms
    ]
    return {
        "window_rows": len(stamps),
        "first_utc": utc(stamps[0]) if stamps else None,
        "last_utc": utc(stamps[-1]) if stamps else None,
        "start_boundary_present": START in seen,
        "excluded_end_boundary_present": END in seen,
        "pagination_crossed_start": crossed_start,
        "provisional_interval_ms": interval_ms,
        "provisional_expected_rows": len(expected),
        "missing_provisional_grid_utc": [utc(t) for t in missing],
        "off_provisional_grid_utc": [utc(t) for t in off_grid],
        "observed_interval_deviations": gaps,
        "observed_delta_ms": sorted({b - a for a, b in zip(stamps, stamps[1:])}),
        "grid_match_only": bool(stamps) and not missing and not off_grid,
        "historical_completeness": "unverified: historical schedule changes unavailable",
        "schedule_uncertainty": (
            "Current fundInterval and assumed UTC epoch phase are provisional; "
            "deviations could be schedule changes or missing data, not proof of either."
        ),
        "rows": [{"symbol_time_utc": utc(t), "fundingTime": t, "fundingRate": seen[t]} for t in stamps],
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect refused: public fixed endpoint requests only")


class Collector:
    def __init__(self, path):
        self.path = path
        self.deadline = time.monotonic() + 260
        self.opener = urllib.request.build_opener(NoRedirect)
        self.report = {
            "schema_version": 1, "started_utc": utc(),
            "window": {"start_utc": utc(START), "end_exclusive_utc": utc(END)},
            "limits": {"max_requests_including_metadata_and_retries": 36,
                       "per_attempt_seconds": 10, "max_retries": 1, "wall_seconds": 260},
            "request_count": 0, "requests": [], "symbols": {},
            "errors": [], "status": "in_progress",
            "methodology": __doc__,
            "provenance": [],
        }

    def save(self):
        self.path.write_text(json.dumps(self.report, indent=2, allow_nan=False) + "\n")

    def get(self, endpoint, parameters):
        if endpoint not in (METADATA, HISTORY):
            raise ValueError("endpoint not permitted")
        for attempt in range(2):
            if self.report["request_count"] >= 36 or time.monotonic() >= self.deadline:
                raise RuntimeError("request/wall budget exhausted")
            record = {
                "id": self.report["request_count"] + 1,
                "method": "GET", "endpoint": endpoint, "parameters": dict(parameters),
                "url": BASE + endpoint + "?" + urllib.parse.urlencode(parameters),
                "started_utc": utc(), "attempt": attempt + 1,
            }
            self.report["request_count"] += 1
            self.report["requests"].append(record)
            self.save()
            started = time.monotonic()
            previous = signal.signal(signal.SIGALRM, self._alarm)
            signal.setitimer(signal.ITIMER_REAL, min(10, self.deadline - started))
            try:
                request = urllib.request.Request(record["url"], headers={"User-Agent": "tokendashboard-research/1.8.2"})
                try:
                    response = self.opener.open(request, timeout=10)
                except urllib.error.HTTPError as exc:
                    response = exc
                with response:
                    record["http_status"] = response.code
                    record["http_date"] = response.headers.get("Date")
                    raw = response.read()
                record["raw_response_base64"] = base64.b64encode(raw).decode()
                record["raw_response_sha256"] = digest(raw)
                record["raw_response_bytes"] = len(raw)
                decoded = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                record["response"] = decoded
                record["canonical_response_sha256"] = canonical(decoded)
                if not isinstance(decoded, dict):
                    raise ValueError("API response is not an object")
                record["api_code"] = decoded.get("code")
                record["api_msg"] = decoded.get("msg")
                if record["http_status"] != 200 or record["api_code"] != "00000":
                    raise ValueError("HTTP/API failure")
                return decoded
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
                if attempt == 1:
                    raise RuntimeError(record["error"]) from exc
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
                record["finished_utc"] = utc()
                record["elapsed_seconds"] = round(time.monotonic() - started, 6)
                self.save()
        raise RuntimeError("attempts exhausted")

    @staticmethod
    def _alarm(signum, frame):
        raise TimeoutError("hard per-attempt deadline")

    def run(self):
        seen_by_symbol = {symbol: {} for symbol in SYMBOLS}
        intervals = {}
        try:
            for name in ("bitget-instruments-2026-11-01.json", "bitget-followup-feasibility-2026-11-01.json"):
                raw = (ROOT / "data" / name).read_bytes()
                self.report["provenance"].append({
                    "file": "research/data/" + name, "file_sha256": digest(raw),
                    "use": "reviewed context only; no old API rows reused",
                })
            metadata = self.get(METADATA, {"category": "USDT-FUTURES"})
            if not isinstance(metadata.get("data"), list):
                raise ValueError("metadata data must be a list")
            for symbol in SYMBOLS:
                matches = [r for r in metadata["data"] if r.get("symbol") == symbol]
                if len(matches) != 1:
                    raise ValueError(f"{symbol}: missing/duplicate current metadata")
                row = matches[0]
                hours = Decimal(str(row.get("fundInterval")))
                if not hours.is_finite() or hours <= 0 or hours > 24 or hours * 3600000 != int(hours * 3600000):
                    raise ValueError(f"{symbol}: invalid current funding interval")
                if row.get("category") != "USDT-FUTURES" or row.get("type") != "perpetual":
                    raise ValueError(f"{symbol}: wrong metadata product")
                intervals[symbol] = int(hours * 3600000)
            for symbol in SYMBOLS:
                result = {"status": "collecting", "pages": [], "duplicate_overlap_rows": 0}
                self.report["symbols"][symbol] = result
                seen = seen_by_symbol[symbol]
                previous_oldest = None
                crossed = False
                try:
                    for number in range(1, 4):
                        payload = self.get(HISTORY, {
                            "symbol": symbol, "productType": "USDT-FUTURES",
                            "pageSize": 100, "pageNo": number,
                        })
                        result["pages"].append({"pageNo": number, "request_id": self.report["request_count"]})
                        page = validate_page(payload.get("data"), symbol, int(time.time() * 1000))
                        result["duplicate_overlap_rows"] += merge_page(seen, page, previous_oldest)
                        if page:
                            previous_oldest = min(t for t, _ in page)
                            crossed = previous_oldest <= START
                        if crossed or len(page) < 100:
                            break
                    result.update(coverage(seen, intervals[symbol], crossed))
                    if not crossed or not result["grid_match_only"]:
                        raise ValueError("incomplete traversal or provisional grid discrepancy; inspect uncertainty")
                    result["status"] = "validated_provisional_grid_only"
                except Exception as exc:
                    result.update(coverage(seen, intervals[symbol], crossed))
                    result["status"] = "failed"
                    result["error"] = f"{type(exc).__name__}: {exc}"
                    raise
        except Exception as exc:
            self.report["errors"].append(f"{type(exc).__name__}: {exc}")
        finally:
            for symbol in SYMBOLS:
                self.report["symbols"].setdefault(symbol, {
                    "status": "not_collected", "error": "collection stopped before symbol",
                    "window_rows": 0, "missing_data": "entire window unmeasured",
                })
            self.report["status"] = "failed" if self.report["errors"] else "validated_provisional_grid_only"
            self.report["completed_utc"] = utc()
            self.save()
        return 1 if self.report["errors"] else 0


def main():
    stamp = utc().replace(":", "").replace("+", "")
    path = ROOT / "data" / f"bitget-funding-history-{stamp}.json"
    collector = Collector(path)
    code = collector.run()
    print(json.dumps({"file": str(path), "status": collector.report["status"],
                      "request_count": collector.report["request_count"],
                      "errors": collector.report["errors"]}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
