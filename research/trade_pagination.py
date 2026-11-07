"""Bounded public Bitget paging check, not a complete trade-history download.

Run: timeout 140s python -m research.trade_pagination
Offline tests: python -m unittest research.test_trade_pagination
"""

import base64
import hashlib
import json
import signal
import socket
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


ENDPOINT = "https://api.bitget.com/api/v2/mix/market/fills-history"
DOCUMENTATION = "https://www.bitget.com/legacy-docs/classic/contract/market/Get-Fills-History"
START_MS = 1789655400000
END_MS = 1789655460000
LIMIT = 3
MAX_REQUESTS = 8
TIMEOUT = 15
MAX_BYTES = 1_000_000


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class ProbeError(ValueError):
    pass


def integer(value, field):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise ProbeError(f"{field} must be a decimal integer string")
    return int(value)


def validate_page(response, parameters, seen):
    """Return the last (minimum) ID as the next exclusive older-data cursor."""
    if not isinstance(response, dict) or response.get("code") != "00000":
        raise ProbeError("API code is not 00000")
    rows = response.get("data")
    if not isinstance(rows, list) or not 1 <= len(rows) <= int(parameters["limit"]):
        raise ProbeError("expected a nonempty page within requested limit")
    ids = []
    boundary = parameters.get("idLessThan")
    for row in rows:
        if not isinstance(row, dict):
            raise ProbeError("trade row must be an object")
        trade_id = integer(row.get("tradeId"), "tradeId")
        if trade_id <= 0:
            raise ProbeError("tradeId must be positive")
        if trade_id in seen or trade_id in ids:
            raise ProbeError("duplicate tradeId within/across pages")
        if boundary is not None and trade_id >= integer(boundary, "idLessThan"):
            raise ProbeError("tradeId violates exclusive idLessThan boundary")
        if ids and trade_id >= ids[-1]:
            raise ProbeError("tradeIds are not strictly descending integers")
        if row.get("symbol") != parameters["symbol"]:
            raise ProbeError("symbol mismatch")
        ts = integer(row.get("ts"), "ts")
        if not int(parameters["startTime"]) <= ts < int(parameters["endTime"]):
            raise ProbeError("timestamp outside exact requested half-open minute")
        for field in ("price", "size"):
            try:
                number = Decimal(str(row.get(field)))
            except InvalidOperation as exc:
                raise ProbeError(f"invalid {field}") from exc
            if not number.is_finite() or number <= 0:
                raise ProbeError(f"{field} must be finite and positive")
        ids.append(trade_id)
    seen.update(ids)
    return str(ids[-1])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect would be another market request outside our explicit counter.
        return None


def deadline(signum, frame):
    raise TimeoutError("15-second whole-request deadline exceeded")


class Client:
    def __init__(self, evidence):
        self.evidence = evidence
        self.retry_used = False
        self.opener = build_opener(NoRedirect)

    def fetch(self, parameters, page):
        for attempt in range(2):
            if len(self.evidence["requests"]) >= MAX_REQUESTS:
                raise ProbeError("market request budget exhausted")
            copied = dict(parameters)
            url = ENDPOINT + "?" + urlencode(copied)
            record = {
                "request_number": len(self.evidence["requests"]) + 1,
                "page": page, "attempt": attempt + 1, "method": "GET",
                "parameters": copied, "url": url, "started_utc": utc_now(),
                "status": "failed",
            }
            self.evidence["requests"].append(record)
            started = time.monotonic()
            retryable = False
            try:
                signal.setitimer(signal.ITIMER_REAL, TIMEOUT)
                try:
                    reply = self.opener.open(
                        Request(url, method="GET", headers={"User-Agent": "BitgetPagingIntegrity/1.0"}),
                        timeout=TIMEOUT,
                    )
                except HTTPError as exc:
                    reply = exc
                with reply:
                    record.update(http_status=reply.code, actual_url=reply.geturl())
                    raw = reply.read(MAX_BYTES + 1)
                record.update(
                    raw_response_base64=base64.b64encode(raw).decode("ascii"),
                    raw_response_sha256=digest(raw), raw_response_bytes=len(raw),
                )
                if len(raw) > MAX_BYTES:
                    raise ProbeError("response exceeded bounded byte limit")
                try:
                    decoded = json.loads(raw)
                    record["response"] = decoded
                    record["response_canonical_sha256"] = digest(canonical(decoded))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ProbeError(f"invalid JSON response: {exc}") from exc
                if record["http_status"] != 200:
                    retryable = record["http_status"] >= 500
                    raise ProbeError(f"HTTP status {record['http_status']}")
                record["status"] = "received_not_yet_validated"
                return decoded, record
            except (URLError, TimeoutError, socket.timeout, OSError, ProbeError) as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
                retryable = retryable or isinstance(exc, (URLError, OSError))
                if not retryable or self.retry_used or attempt == 1:
                    raise ProbeError(record["error"]) from exc
                self.retry_used = True
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                record["retrieved_utc"] = utc_now()
                record["elapsed_seconds"] = round(time.monotonic() - started, 6)
        raise ProbeError("retry exhausted")


def run(client, evidence):
    for symbol in ("BTCUSDT", "AAPLUSDT"):
        result = {"symbol": symbol, "status": "failed", "verified_pages": 0}
        evidence["symbols"].append(result)
        parameters = {
            "symbol": symbol, "productType": "USDT-FUTURES",
            "startTime": str(START_MS), "endTime": str(END_MS), "limit": str(LIMIT),
        }
        seen = set()
        try:
            for page in (1, 2):
                response, record = client.fetch(parameters, page)
                try:
                    cursor = validate_page(response, parameters, seen)
                except ProbeError as exc:
                    record.update(status="failed", validation_error=str(exc))
                    raise
                record.update(status="verified", next_idLessThan=cursor)
                # Never mutate a mapping already captured as request evidence.
                parameters = {**parameters, "idLessThan": cursor}
                result["verified_pages"] += 1
            result.update(status="verified", unique_sample_trades=len(seen))
        except ProbeError as exc:
            result["error"] = str(exc)
    evidence["status"] = (
        "verified" if all(item["status"] == "verified" for item in evidence["symbols"])
        else "failed"
    )


def main():
    started = datetime.now(timezone.utc)
    path = Path("research/data") / (
        "bitget-trade-pagination-" + started.strftime("%Y-%m-%dT%H%M%S.%fZ") + ".json"
    )
    evidence = {
        "schema_version": 1, "story": "#15; parent #7; epic #3",
        "started_utc": started.isoformat(), "status": "failed",
        "documentation": DOCUMENTATION,
        "cursor_semantics": (
            "idLessThan exclusively requests older IDs; use preceding response endId. "
            "This endpoint returns a descending data array without endId; its last "
            "(minimum integer) tradeId is the page end ID."
        ),
        "requested_window_utc": ["2026-09-17T14:30:00Z", "2026-09-17T14:31:00Z"],
        "timestamp_policy": "startTime <= ts < endTime (exact half-open minute)",
        "max_market_requests": MAX_REQUESTS, "per_request_deadline_seconds": TIMEOUT,
        "max_retries_total": 1, "requests": [], "symbols": [],
        "limitations": (
            "Two tiny pages per symbol test sequential cursor consistency only. "
            "Even verified pages do not establish complete trades, gap-free coverage, "
            "market representativeness or strategy efficacy. Original six-print "
            "evidence is unchanged and does not verify paging."
        ),
        "reproduce": "timeout 140s python -m research.trade_pagination",
        "hash_scheme": "SHA256; canonical JSON: sorted keys, compact separators, UTF-8, no NaN",
    }
    previous_handler = signal.signal(signal.SIGALRM, deadline)
    try:
        run(Client(evidence), evidence)
    finally:
        signal.signal(signal.SIGALRM, previous_handler)
        evidence["finished_utc"] = utc_now()
        evidence["actual_market_requests"] = len(evidence["requests"])
        evidence["artifact_payload_sha256"] = digest(canonical(evidence))
        with path.open("x") as output:
            json.dump(evidence, output, indent=2, allow_nan=False)
            output.write("\n")
        print(f"{path}: {evidence['status']}; {len(evidence['requests'])} market requests")
    return 0 if evidence["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
