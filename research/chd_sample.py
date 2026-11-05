"""Bounded anonymous CHD acquisition; hourly objects are receive-time partitions."""

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.cryptohftdata.com/v1/download"
MAX_OBJECTS = 8
MAX_TRANSACTIONS = 16
TOTAL_BYTES = 16 * 1024 * 1024
MAX_BYTES = TOTAL_BYTES
MAX_ROWS = 2_000_000
PATTERN = re.compile(
    r"bitget_futures/(\d{4}-\d{2}-\d{2})/([01]\d|2[0-3])/([A-Z0-9]+)_(trades|orderbook)\.parquet"
)


def validate_object(value):
    match = PATTERN.fullmatch(value)
    if not match:
        raise ValueError("Expected a Bitget futures hourly trade/orderbook object")
    date = datetime.strptime(match[1], "%Y-%m-%d")
    if not datetime(2026, 9, 17) <= date <= datetime(2026, 11, 3):
        raise ValueError("This development sampler only accepts 2026-09-17 through 2026-11-03")
    return match


class BudgetRedirects(HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.transactions = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if self.transactions >= MAX_TRANSACTIONS or urlsplit(newurl).scheme != "https":
            raise ValueError("Redirect request budget or HTTPS requirement violated")
        self.transactions += 1
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def inspect_parquet(path, object_name):
    import pyarrow.parquet as pq

    match = validate_object(object_name)
    parquet = pq.ParquetFile(path)
    rows = parquet.metadata.num_rows
    if rows > MAX_ROWS:
        raise ValueError("Parquet exceeds two-million-row budget")
    names = parquet.schema_arrow.names
    clocks = ["received_time", "event_time"]
    if match[4] == "trades":
        clocks.append("trade_time")
    if not {"symbol", *clocks}.issubset(names):
        raise ValueError("Missing symbol/clock columns")
    ranges = {name: [None, None] for name in clocks}
    for batch in parquet.iter_batches(columns=["symbol", *clocks], batch_size=8192):
        for row in batch.to_pylist():
            if row["symbol"] != match[3]:
                raise ValueError("Parquet symbol differs from requested object")
            for name in clocks:
                stamp = row[name]
                if type(stamp) is not int or stamp < 0:
                    raise ValueError("Invalid clock value")
                lo, hi = ranges[name]
                ranges[name] = [stamp if lo is None else min(lo, stamp),
                                stamp if hi is None else max(hi, stamp)]
    start = int(datetime.strptime(f"{match[1]} {match[2]}", "%Y-%m-%d %H")
                .replace(tzinfo=timezone.utc).timestamp()) * 10**9
    received = ranges["received_time"]
    if rows and not start <= received[0] <= received[1] < start + 3600 * 10**9:
        raise ValueError("Receive timestamp outside requested storage hour")
    return {
        "status": "OBSERVED" if rows else "EMPTY",
        "rows": rows,
        "schema": [{"name": field.name, "type": str(field.type)}
                   for field in parquet.schema_arrow],
        "clock_ranges": ranges,
        "clock_units": {name: "ns" if name == "received_time" else "ms" for name in clocks},
    }


def acquire(objects, directory):
    if not 1 <= len(objects) <= MAX_OBJECTS or len(set(objects)) != len(objects):
        raise ValueError("Request one to eight unique objects")
    for value in objects:
        validate_object(value)
    import pyarrow

    directory.mkdir(parents=True, exist_ok=False)
    redirects = BudgetRedirects()
    opener = build_opener(redirects)
    manifest = {
        "provider": "CryptoHFTData; third-party collector, not official Bitget archive",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "pyarrow_version": pyarrow.__version__,
        "api": API, "authentication": "anonymous; no credentials loaded",
        "requested_objects": objects,
        "budgets": {"objects": MAX_OBJECTS, "http_transactions": MAX_TRANSACTIONS, "bytes_per_object": MAX_BYTES,
                    "total_bytes": TOTAL_BYTES, "rows_per_object": MAX_ROWS,
                    "socket_timeout_seconds": 10, "wall_budget_seconds": 120, "retries": 0},
        "objects": [],
        "limitations": [
            "Receive-hour storage partitions are not event-time completeness certificates",
            "No retries; stop on rate limit and honor Retry-After before a separate invocation",
            "Signed redirect URLs, response cookies and authentication headers are not persisted",
            "Raw files stay local; reacquisition may change availability or hashes",
        ],
    }
    started, consumed = time.monotonic(), 0
    halted = False
    for index, value in enumerate(objects):
        record = {"object": value, "request": {"file": value},
                  "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                  "status": "IN_PROGRESS"}
        manifest["objects"].append(record)
        manifest["status"] = "IN_PROGRESS"
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if (halted or consumed >= TOTAL_BYTES or redirects.transactions >= MAX_TRANSACTIONS
                or time.monotonic() - started >= 120):
            record["status"] = "NOT_REQUESTED_BUDGET_OR_RATE_LIMIT"
        else:
            path = directory / f"{index:02d}-{Path(value).name}"
            size = 0
            try:
                redirects.transactions += 1
                req = Request(API + "?" + urlencode({"file": value}),
                              headers={"User-Agent": "tokendashboard-research/1.0"})
                with opener.open(req, timeout=10) as response:
                    record["http_status"] = response.status
                    if response.status != 200:
                        raise ValueError("Unexpected successful HTTP status")
                    digest = hashlib.sha256()
                    with path.open("xb") as output:
                        while True:
                            if time.monotonic() - started >= 120:
                                raise ValueError("Wall-time budget exhausted")
                            chunk = response.read(min(65536, MAX_BYTES - size + 1,
                                                      TOTAL_BYTES - consumed + 1))
                            if not chunk:
                                break
                            size += len(chunk)
                            consumed += len(chunk)
                            if size > MAX_BYTES or consumed > TOTAL_BYTES:
                                raise ValueError("Download byte budget exceeded")
                            output.write(chunk)
                            digest.update(chunk)
                record.update(bytes=size, sha256=digest.hexdigest(), local_file=path.name)
                record.update(inspect_parquet(path, value))
            except HTTPError as exc:
                record.update(status="MISSING" if exc.code == 404 else "HTTP_ERROR",
                              http_status=exc.code)
                if exc.code == 429:
                    record["retry_after"] = exc.headers.get("Retry-After")
                    halted = True
            except (OSError, URLError, ValueError) as exc:
                # Do not log exception URLs: a redirect may contain a temporary credential.
                record.update(status="DOWNLOAD_OR_VALIDATION_FAILED",
                              error_type=type(exc).__name__, bytes_received=size)
            if path.exists() and record["status"] not in ("OBSERVED", "EMPTY"):
                record["retained_failed_file"] = path.name
        manifest["http_transactions"] = redirects.transactions
        manifest["bytes_received"] = consumed
        manifest["status"] = (
            "BOUNDED_SAMPLE_OBSERVED"
            if all(row["status"] == "OBSERVED" for row in manifest["objects"])
            else "PARTIAL_OR_UNAVAILABLE"
        )
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object", action="append", required=True, dest="objects")
    parser.add_argument("--directory", type=Path, required=True, help="New local cache directory")
    args = parser.parse_args()
    try:
        report = acquire(args.objects, args.directory)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"Sample acquisition failed: {exc}\n")
    print(json.dumps({"status": report["status"], "manifest": str(args.directory / "manifest.json")}))
    return 0 if report["status"] == "BOUNDED_SAMPLE_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
