"""Bounded anonymous inspection of Bitget's official archive client.

No listing request is enabled until the client proves its complete transport.
Run with ``--inspect`` to preserve the two previously identified official assets,
or ``--review`` for an offline evidence check. Both exit nonzero while blocked.
This intentionally does not infer anonymous access from endpoint names.
"""

import argparse
import base64
import hashlib
import http.client
import json
from pathlib import Path
import signal
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit


PAGE_CLIENT = "https://www.bitget.com/landing-static/client/js/pages-data-download-index-page.1f14c0d0ddfaba7e1f21.chunk.js"
SHARED_CLIENT = "https://www.bitget.com/landing-static/client/js/client.ef4a4af7640f8baa29c0.main.js"
OUTPUT = Path("research/data/archive-listing-2026-11-02.json")
LIMIT = 2 * 1024 * 1024


def public_headers(headers):
    return {
        name: value for name, value in headers.items()
        if name.lower() not in ("set-cookie", "cookie", "authorization", "proxy-authorization")
    }


class ProbeError(Exception):
    """Explicit bounded-probe failure."""


def utc():
    return datetime.now(timezone.utc).isoformat()


def guard(method, url, body=None):
    """Deny unproved listing requests, credentials, query changes and redirects."""
    parsed = urlsplit(url)
    if (
        method != "GET"
        or url not in (PAGE_CLIENT, SHARED_CLIENT)
        or parsed.scheme != "https"
        or parsed.netloc != "www.bitget.com"
        or parsed.username is not None
        or parsed.query
        or parsed.fragment
        or body is not None
    ):
        raise ProbeError("Request denied: only the two exact official client GETs are proved")


def parse_listing(body, status):
    """Conservative JSON envelope check, not a proved archive response schema."""
    if status != 200:
        raise ProbeError(f"Listing HTTP status {status}, not success")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProbeError("Listing is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("code") != "00000":
        raise ProbeError("Listing API error or unverified response contract")
    if not isinstance(value.get("data"), list):
        raise ProbeError("Listing data is not a list")
    return value["data"]


class Probe:
    def __init__(self, artifact=None):
        self.artifact = artifact if artifact is not None else {
            "schema_version": 1,
            "issue": 23,
            "parent_issue": 7,
            "epic_issue": 3,
            "started_utc": utc(),
            "requests": [],
            "budget": {
                "max_transactions": 10,
                "max_body_bytes": LIMIT,
                "whole_request_seconds": 10,
                "live_command_seconds": 180,
                "transactions": 0,
                "body_bytes": 0,
                "redirects_followed": 0,
                "post_requests": 0,
            },
        }

    def request(self, method, url, body=None, connection_factory=None):
        guard(method, url, body)
        budget = self.artifact["budget"]
        if budget["transactions"] >= 10 or budget["body_bytes"] >= LIMIT:
            raise ProbeError("HTTP transaction/body budget exhausted")
        if any(record["url"] == url for record in self.artifact["requests"]):
            raise ProbeError("Duplicate request denied; no retries")
        budget["transactions"] += 1
        record = {
            "method": method, "url": url, "query_parameters": {},
            "body_parameters": None, "request_body_base64": "",
            "headers": {"Accept-Encoding": "identity"},
            "started_utc": utc(), "redirect_chain": [],
            "method_assertion": "Anonymous official static client GET, no listing or mutation",
            "status": None,
        }
        self.artifact["requests"].append(record)
        raw = bytearray()
        connection = None
        started = time.monotonic()

        def expired(signum, frame):
            raise TimeoutError("10-second whole-request deadline exceeded")

        old_handler = signal.signal(signal.SIGALRM, expired)
        old_timer = signal.setitimer(signal.ITIMER_REAL, 10)
        try:
            parsed = urlsplit(url)
            factory = connection_factory or http.client.HTTPSConnection
            connection = factory(parsed.hostname, timeout=10)
            connection.request(method, parsed.path, headers=record["headers"])
            response = connection.getresponse()
            record.update(status=response.status, response_headers=public_headers(dict(response.getheaders())))
            if 300 <= response.status < 400:
                record["redirect_chain"] = [{
                    "status": response.status,
                    "location": response.getheader("Location"),
                    "followed": False,
                }]
            remaining = LIMIT - budget["body_bytes"]
            declared = response.getheader("Content-Length")
            if declared is not None and int(declared) > remaining:
                raise ProbeError("Declared response exceeds cumulative body budget; body not read")
            while remaining:
                chunk = response.read1(min(65536, remaining))
                if not chunk:
                    break
                raw.extend(chunk)
                budget["body_bytes"] += len(chunk)
                remaining -= len(chunk)
            else:
                raise ProbeError("Cumulative body budget reached; response completeness unproved")
            record["body_complete"] = True
            if response.status != 200:
                raise ProbeError(f"HTTP {response.status}; redirect/retry not followed")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ProbeError("Unexpected content encoding; no decompression attempted")
            return bytes(raw)
        except (OSError, TimeoutError, ValueError, http.client.HTTPException, ProbeError) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise ProbeError(record["error"]) from exc
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
            if old_timer[0]:
                signal.setitimer(signal.ITIMER_REAL, *old_timer)
            if connection is not None:
                connection.close()
            record.update(
                finished_utc=utc(),
                elapsed_seconds=round(time.monotonic() - started, 6),
                raw_response_bytes=len(raw),
                raw_response_sha256=hashlib.sha256(raw).hexdigest(),
                raw_response_base64=base64.b64encode(raw).decode("ascii"),
            )

    def save(self, path=OUTPUT):
        self.artifact["completed_utc"] = utc()
        path.write_text(json.dumps(self.artifact, indent=2) + "\n")


def review(artifact):
    """Verify raw captures and record selected-only source evidence offline."""
    sources = {}
    total = 0
    for record in artifact["requests"]:
        record["response_headers"] = public_headers(record.get("response_headers", {}))
        guard(record["method"], record["url"])
        raw = base64.b64decode(record["raw_response_base64"], validate=True)
        if (
            record["status"] != 200
            or not record.get("body_complete")
            or len(raw) != record["raw_response_bytes"]
            or hashlib.sha256(raw).hexdigest() != record["raw_response_sha256"]
        ):
            raise ProbeError("Captured source integrity/status/completeness check failed")
        total += len(raw)
        sources[record["url"]] = raw.decode("utf-8")
    budget = artifact["budget"]
    if (
        len(sources) != 2 or len(artifact["requests"]) != budget["transactions"]
        or total != budget["body_bytes"] or total > LIMIT
        or budget["transactions"] > 10 or budget["post_requests"] != 0
    ):
        raise ProbeError("Evidence accounting mismatch")
    selections = [
        (PAGE_CLIENT, 'value:"2-3",label:`${e("vip_fee.contract")} - ${e("data_download.data_deep")}`'),
        (PAGE_CLIENT, 'const s=U(a.split("-").map(Number),2),r=s[0],i=s[1]'),
        (PAGE_CLIENT, 'displaySymbol:t,businessLine:r,businessType:i,dateType:n,beginTimeStr:c,endTimeStr:m'),
        (PAGE_CLIENT, 'e[e.Day=1]="Day",e[e.Month=2]="Month"'),
        (PAGE_CLIENT, 'e[e.Level1=1]="Level1",e[e.Level500=2]="Level500"'),
        (PAGE_CLIENT, 'const R=(0,E.$)({endpoint:"/statistics/public/download/getPublicDataV2"})'),
        (SHARED_CLIENT, 'i=void 0===n?"POST":n'),
        (SHARED_CLIENT, 'return r.cl.post({url:t,data:e,...n},l)'),
        (SHARED_CLIENT, 'headers:{"Content-Type":a.TA.JSON}'),
        (SHARED_CLIENT, 'e.JSON="application/json;charset=UTF-8"'),
        (SHARED_CLIENT, 'const T=S({requestOptions:{urlPrefix:"/v1"}})'),
        (SHARED_CLIENT, 'i&&(e.url=`${p}${e.url}`),r&&(0,l.Kg)(r)&&(e.url=`${r}${e.url}`)'),
        (SHARED_CLIENT, 'e.data=await c.gZ.requestInterceptLoginUrl(w,A)'),
        (SHARED_CLIENT, 'const S=await c.gZ.requestInterceptCoreUrl(w,A,e.headers)'),
        (SHARED_CLIENT, 'e.headers["dy-token"]=u.w.getDyToken()'),
    ]
    evidence = []
    for url, text in selections:
        offset = sources[url].find(text)
        if offset < 0:
            raise ProbeError(f"Expected client source changed: {text}")
        evidence.append({"source_url": url, "character_offset": offset, "exact_source": text})
    artifact["official_client_evidence"] = evidence
    artifact["header_privacy"] = (
        "Cookie and authorization headers are excluded; raw response body hashes "
        "cover bodies only, not redacted headers."
    )
    artifact["findings"] = {
        "filter_mapping": {
            "businessLine": 2, "businessType": 3,
            "evidence": "UI contract/depth option is 2-3; split('-').map(Number) feeds the two fields.",
            "dateType_day": 1, "deptType_level1": 1, "deptType_level500": 2,
            "displaySymbol": "Passed from tradingPairs selection, not proved to be a scalar string.",
        },
        "listing_semantics": "Page helper feeds downloadable file records; no order/account action called.",
        "method": "POST explicitly defaults in the official endpoint wrapper.",
        "browser_host": "Relative /v1 browser path; www.bitget.com same-origin is conditional on the runtime client configuration, not an absolute host literal.",
        "configured_encoding": "application/json;charset=UTF-8; POST passes data rather than query. Final payload is replaced by a delegated interceptor.",
        "unresolved": [
            "requestInterceptLoginUrl(w,A) replaces outgoing data, but its implementation and endpoint-specific effect were not established in the captured assets.",
            "requestInterceptCoreUrl(w,A,e.headers) may supply additional headers; mandatory versus optional anonymous requirements are not established.",
            "No final anonymous wire payload, exact effective browser host, or response contract was observed; do not promote default configuration to a proved anonymous contract.",
        ],
    }
    artifact["result"] = {
        "status": "BLOCKED_ANONYMOUS_WIRE_CONTRACT_UNPROVED",
        "blocker": "Futures-depth numeric mapping and POST default are now evidenced, but final anonymous request encoding/headers and effective host remain unproved after runtime hooks. No speculative POST was authorized or sent.",
        "next_step": "Inspect the official runtime implementation of requestInterceptLoginUrl/requestInterceptCoreUrl and client configuration, or obtain Bitget's supported anonymous listing contract. Only then authorize one exact listing POST.",
        "sample_recovered": False, "quote_coverage_claimed": False,
        "historical_coverage": "NOT_TESTED",
        "snapshot_delta_sequence_utc_product_symbol": "NOT_TESTED: no file/listing fetched",
        "parent_7": "BLOCKED; bounded source inspection is not historical executable coverage",
        "absence_or_private_access_inferred": False,
    }
    artifact["reused_evidence"] = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (
            Path("research/data/execution-inputs-2026-11-02.json"),
            Path("research/data/bitget-archive-feasibility-2026-11-02.json"),
        )
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--inspect", action="store_true")
    modes.add_argument("--review", action="store_true")
    args = parser.parse_args()
    if args.review:
        probe = Probe(json.loads(OUTPUT.read_text()))
        try:
            review(probe.artifact)
        except ProbeError as exc:
            print(f"Offline review failed: {exc}")
            return 1
        probe.save()
        print(json.dumps({"result": probe.artifact["result"], "budget": probe.artifact["budget"]}))
        return 2
    if OUTPUT.exists():
        parser.error("Evidence already exists; refusing an implicit repeat live run")
    probe = Probe()
    try:
        for url in (PAGE_CLIENT, SHARED_CLIENT):
            probe.request("GET", url)
        probe.artifact["result"] = {
            "status": "BLOCKED_PENDING_OFFICIAL_CLIENT_REVIEW",
            "blocker": "Source captured; host, encoding and futures-depth mapping require review before any POST.",
            "sample_recovered": False,
            "quote_coverage_claimed": False,
        }
        return 2
    except ProbeError as exc:
        probe.artifact["result"] = {
            "status": "FAILED_BOUNDED_INSPECTION", "blocker": str(exc),
            "sample_recovered": False, "quote_coverage_claimed": False,
        }
        return 1
    finally:
        probe.save()
        print(json.dumps({"result": probe.artifact["result"], "budget": probe.artifact["budget"]}))


if __name__ == "__main__":
    raise SystemExit(main())
