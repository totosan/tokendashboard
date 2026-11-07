"""One bounded historic minute; endpoint completeness is not ledger completeness.

Run: timeout 180s python -m research.trade_profile_window
Offline: timeout 120s python -m unittest research.test_trade_profile_window

Endpoint reference:
https://www.bitget.com/legacy-docs/classic/contract/market/Get-Fills-History
No endpoint-only experiment establishes an independently complete trade ledger.
"""

import base64
import json
import signal
import time
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from research.trade_pagination import (
    ENDPOINT, END_MS, START_MS, NoRedirect, ProbeError, canonical, digest,
    utc_now, validate_page,
)

MAX_REQUESTS = 12
TIMEOUT = 10
MAX_BYTES = 2 * 1024 * 1024
PARAMETERS = {
    "symbol": "AAPLUSDT", "productType": "USDT-FUTURES",
    "startTime": str(START_MS), "endTime": str(END_MS), "limit": "1000",
}
RULES = {
    "version": 1, "weight": "base size, not quote notional", "bins": 20,
    "edges": "observed min/max; equal width; [left,right), final includes max",
    "flat_price": "all volume in bin 0; all edges equal observed price",
    "poc_tie": "lowest price bin",
    "value_area": (
        "Start at POC, expand one adjacent bin with larger volume until >=70% "
        "of base volume; ties choose lower bin; include intervening zero bins."
    ),
}


def profile(rows):
    """Frozen descriptive profile; never evidence of trading efficacy."""
    if not rows:
        raise ProbeError("cannot profile an empty endpoint window")
    values = []
    for row in rows:
        try:
            price, size = Decimal(str(row["price"])), Decimal(str(row["size"]))
        except (ValueError, ArithmeticError, KeyError) as exc:
            raise ProbeError("invalid profile price/size") from exc
        if not price.is_finite() or not size.is_finite() or price <= 0 or size <= 0:
            raise ProbeError("profile price/size must be finite and positive")
        values.append((price, size))
    low, high = min(p for p, _ in values), max(p for p, _ in values)
    width = (high - low) / 20
    edges = [low + width * i for i in range(21)]
    edges[-1] = high
    volumes = [Decimal(0) for _ in range(20)]
    for price, size in values:
        # Compare frozen edges directly, avoiding division rounding at an edge.
        index = 0 if width == 0 else next(
            (i for i in range(20) if price < edges[i + 1]), 19
        )
        volumes[index] += size
    total = sum(volumes)
    poc = max(range(20), key=lambda i: volumes[i])
    left = right = poc
    area = volumes[poc]
    while area < total * Decimal("0.70"):
        if left == 0:
            right += 1
            area += volumes[right]
        elif right == 19 or volumes[left - 1] >= volumes[right + 1]:
            left -= 1
            area += volumes[left]
        else:
            right += 1
            area += volumes[right]
    return {
        "rules": RULES, "trade_count": len(rows),
        "bin_edges": list(map(str, edges)), "base_volume": list(map(str, volumes)),
        "total_base_volume": str(total), "poc_bin": poc,
        "value_area_bins_inclusive": [left, right],
        "value_area_price_bounds": [str(edges[left]), str(edges[right + 1])],
        "value_area_base_volume": str(area),
    }


def deadline(signum, frame):
    raise TimeoutError("10-second whole-request deadline exceeded")


class Client:
    def __init__(self, evidence):
        self.evidence = evidence
        self.opener = build_opener(NoRedirect)

    def fetch(self, parameters, page):
        if len(self.evidence["requests"]) >= MAX_REQUESTS:
            raise ProbeError("12-request budget exhausted")
        url = ENDPOINT + "?" + urlencode(parameters)
        record = {
            "request_number": len(self.evidence["requests"]) + 1, "page": page,
            "method": "GET", "parameters": dict(parameters), "url": url,
            "started_utc": utc_now(), "status": "failed",
        }
        self.evidence["requests"].append(record)
        start = time.monotonic()
        try:
            signal.setitimer(signal.ITIMER_REAL, TIMEOUT)
            try:
                reply = self.opener.open(
                    Request(url, headers={"User-Agent": "BitgetWindowProfile/1.0"}),
                    timeout=TIMEOUT,
                )
            except HTTPError as exc:
                reply = exc
            with reply:
                record.update(http_status=reply.code, actual_url=reply.geturl())
                raw = reply.read(MAX_BYTES)
            record.update(
                raw_response_base64=base64.b64encode(raw).decode("ascii"),
                raw_response_sha256=digest(raw), raw_response_bytes=len(raw),
            )
            if len(raw) >= MAX_BYTES:
                raise ProbeError("body reached byte cap; completeness unknown")
            if record["http_status"] != 200:
                raise ProbeError(f"HTTP {record['http_status']}")
            decoded = json.loads(raw)
            record["response_canonical_sha256"] = digest(canonical(decoded))
            record["status"] = "received_not_yet_validated"
            return decoded, record
        except (URLError, OSError, TimeoutError, ValueError) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise ProbeError(record["error"]) from exc
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            record["finished_utc"] = utc_now()
            record["elapsed_seconds"] = round(time.monotonic() - start, 6)


def run(client, evidence):
    parameters, seen, rows = dict(PARAMETERS), set(), []
    previous_ts = None
    evidence.update(status="TRUNCATED", endpoint_complete=False,
                    trade_ledger_complete=False, profile=None)
    try:
        for page in range(1, MAX_REQUESTS + 1):
            response, record = client.fetch(parameters, page)
            try:
                if (isinstance(response, dict) and response.get("code") == "00000"
                        and response.get("data") == []):
                    record["status"] = "verified_empty_terminal"
                    evidence.update(status="ENDPOINT_COMPLETE", endpoint_complete=True)
                    break
                candidate_seen = set(seen)
                cursor = validate_page(response, parameters, candidate_seen)
                timestamps = [int(row["ts"]) for row in response["data"]]
                joined = ([previous_ts] if previous_ts is not None else []) + timestamps
                if any(a < b for a, b in zip(joined, joined[1:])):
                    raise ProbeError("timestamps not descending within/across pages")
                seen = candidate_seen
                previous_ts = timestamps[-1]
                rows.extend(response["data"])
                record.update(status="verified", next_idLessThan=cursor)
                parameters = {**parameters, "idLessThan": cursor}
            except ProbeError as exc:
                record.update(status="failed", validation_error=str(exc))
                raise
        if not evidence["endpoint_complete"]:
            raise ProbeError("no empty terminal page within request budget")
        if rows:
            evidence["profile"] = profile(rows)
        else:
            evidence["profile_unavailable"] = "Endpoint returned no trades."
    except ProbeError as exc:
        evidence["error"] = str(exc)
    evidence["verified_unique_trades"] = len(seen)
    evidence["verified_nonempty_pages"] = sum(
        r.get("status") == "verified" for r in evidence["requests"]
    )
    evidence["candle_comparison"] = {
        "status": "MISSING_EVIDENCE",
        "reason": (
            "No genuine same-window 1-minute candle supplied or fetched. Existing "
            "5m/15m candles cannot establish this minute's OHLC/base volume. "
            "No candle-style profile or comparison fabricated."
        ),
    }


def main():
    stamp = utc_now().replace(":", "").replace("+0000", "Z")
    path = Path("research/data") / f"recovery-trade-profile-{stamp}.json"
    evidence = {
        "schema_version": 1, "story": "#13; related #7; epic #3",
        "started_utc": utc_now(), "requests": [],
        "requested_window_utc": ["2026-09-17T14:30:00Z", "2026-09-17T14:31:00Z"],
        "timestamp_policy": "startTime <= ts < endTime",
        "frozen_profile_rules": RULES,
        "limits": {"requests_including_retries": MAX_REQUESTS,
                   "retries": 0, "whole_request_seconds": TIMEOUT,
                   "response_body_bytes": MAX_BYTES},
        "limitations": (
            "An empty next page proves only endpoint exhaustion under these exact "
            "parameters, not completeness of the real exchange trade ledger. "
            "IDs need not be consecutive; unavailable exchange prints cannot be "
            "independently detected. Descriptive volume only, not trading/efficacy."
        ),
        "cursor_policy": "exclusive idLessThan = preceding validated page minimum tradeId",
        "reproduce": "timeout 180s python -m research.trade_profile_window",
        "hash_scheme": "SHA256 raw bytes and sorted compact UTF-8 JSON, no NaN; payload excludes its own hash",
    }
    previous = signal.signal(signal.SIGALRM, deadline)
    try:
        run(Client(evidence), evidence)
    finally:
        signal.signal(signal.SIGALRM, previous)
        evidence["finished_utc"] = utc_now()
        evidence["actual_market_requests"] = len(evidence["requests"])
        evidence["artifact_payload_sha256"] = digest(canonical(evidence))
        with path.open("x") as output:
            json.dump(evidence, output, indent=2, allow_nan=False)
            output.write("\n")
        print(f"{path}: {evidence['status']}; {len(evidence['requests'])} GETs")
    return 0 if evidence["endpoint_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
