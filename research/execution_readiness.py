#!/usr/bin/env python3
"""Offline G12 input/interval audit, not a fill or account model.

Run from the repository root:
  timeout --signal=TERM --kill-after=5s 30s python research/execution_readiness.py

Exit 2 deliberately means NOT_READY (also for non-authorizing synthetic tests).
Exit 1 means malformed input / I/O error; the requested output records the error.
Only the output is written. No network, subprocesses, or raw-data acquisition.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = "research/results/execution-input-contract-2026-11-04.json"
DEFAULT_OUTPUT = "research/results/execution-readiness-2026-11-04.json"
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 1000
MAX_REFS = 16
MAX_TIMESTAMP = 253402300799999  # Integer UTC milliseconds, through year 9999.


def stamp(value: int) -> int:
    if type(value) is not int or not 0 <= value <= MAX_TIMESTAMP:
        raise ValueError("timestamp must be bounded integer UTC milliseconds")
    return value


def number(value: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise ValueError("decimal values must be strings of at most 80 characters")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError("nonfinite or nonpositive decimal")
    return result


def text(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("expected nonempty bounded text")
    return value


def duration(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 86400000:
        raise ValueError("duration must be integer milliseconds in [0, one day]")
    return value


@dataclass(frozen=True)
class Instrument:
    venue: str
    product: str
    symbol: str
    quote_currency: str
    settlement_currency: str
    contract_multiplier: str

    def __post_init__(self):
        for value in (self.venue, self.product, self.symbol,
                      self.quote_currency, self.settlement_currency):
            text(value)
        number(self.contract_multiplier, positive=True)


@dataclass(frozen=True)
class Source:
    """Content address and record locator, not an attestation of source truth."""

    path: str
    sha256: str
    locator: str

    def __post_init__(self):
        text(self.path)
        text(self.locator)
        if (not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.sha256)):
            raise ValueError("source sha256 must be lowercase hex")


@dataclass(frozen=True)
class Signal:
    instrument: Instrument
    source: Source
    event_ms: int
    available_ms: int
    scan_ms: int
    manual_latency_ms: int
    quote_stream: str

    def __post_init__(self):
        for t in (self.event_ms, self.available_ms, self.scan_ms):
            stamp(t)
        duration(self.manual_latency_ms)
        text(self.quote_stream)
        if not self.event_ms <= self.available_ms <= self.scan_ms:
            raise ValueError("signal event <= availability <= scan is required")
        stamp(self.decision_ms)

    @property
    def decision_ms(self) -> int:
        return self.scan_ms + self.manual_latency_ms


@dataclass(frozen=True)
class Quote:
    instrument: Instrument
    source: Source
    stream: str
    event_ms: int
    available_ms: int
    bid: str
    ask: str
    bid_quantity: str
    ask_quantity: str

    def __post_init__(self):
        text(self.stream)
        stamp(self.event_ms)
        stamp(self.available_ms)
        if self.available_ms < self.event_ms:
            raise ValueError("quote available before event")
        for value in (self.bid, self.ask, self.bid_quantity, self.ask_quantity):
            number(value, positive=True)
        if number(self.bid) > number(self.ask):
            raise ValueError("crossed quote")


@dataclass(frozen=True)
class Fee:
    instrument: Instrument
    source: Source
    account: str
    liquidity: str
    currency: str
    start_ms: int
    end_ms: int
    available_ms: int
    rate: str

    def __post_init__(self):
        text(self.account)
        text(self.currency)
        if self.liquidity not in ("maker", "taker"):
            raise ValueError("fee liquidity must be maker or taker")
        interval(self.start_ms, self.end_ms)
        stamp(self.available_ms)
        number(self.rate)  # Signed fees permit rebates; no cost assumptions here.


@dataclass(frozen=True)
class Funding:
    instrument: Instrument
    source: Source
    settlement_ms: int
    available_ms: int
    rate: str

    def __post_init__(self):
        stamp(self.settlement_ms)
        stamp(self.available_ms)
        number(self.rate)


@dataclass(frozen=True)
class Holding:
    instrument: Instrument
    source: Source
    account: str
    entry_ms: int
    exit_ms: int
    quantity: str

    def __post_init__(self):
        text(self.account)
        interval(self.entry_ms, self.exit_ms)
        number(self.quantity, positive=True)


def interval(start: int, end: int) -> None:
    if stamp(start) >= stamp(end):
        raise ValueError("interval requires start < end")


def bounded(rows: list) -> None:
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError(f"rows must be a list with at most {MAX_ROWS} entries")


def quote_asof(signal: Signal, quotes: list[Quote], max_age_ms: int,
               max_latency_ms: int) -> tuple[Quote | None, list[str]]:
    """Latest compatible event available at decision; no hindsight or fill claim.

    Input order is irrelevant. Conflicting same-event quotes require sequencing
    evidence this contract does not have, so they are rejected rather than tied.
    """
    bounded(quotes)
    duration(max_age_ms)
    duration(max_latency_ms)
    if signal.decision_ms - signal.event_ms > max_latency_ms:
        return None, ["LATENCY_LIMIT_EXCEEDED"]
    matching = [q for q in quotes if q.instrument == signal.instrument
                and q.stream == signal.quote_stream]
    if not matching:
        return None, ["QUOTE_IDENTITY_OR_SOURCE_MISMATCH" if quotes else "MISSING_QUOTES"]
    eligible = [q for q in matching
                if q.event_ms <= signal.decision_ms and q.available_ms <= signal.decision_ms]
    if not eligible:
        return None, ["QUOTE_FUTURE_OR_UNAVAILABLE"]
    latest = max(q.event_ms for q in eligible)
    tied = [q for q in eligible if q.event_ms == latest]
    states = {(q.bid, q.ask, q.bid_quantity, q.ask_quantity) for q in tied}
    if len(states) != 1:
        return None, ["QUOTE_ORDER_AMBIGUOUS"]
    selected = min(tied, key=lambda q: (q.available_ms, q.source.path,
                                      q.source.sha256, q.source.locator))
    if signal.decision_ms - selected.event_ms > max_age_ms:
        return None, ["QUOTE_STALE"]
    return selected, []


def fee_asof(fees: list[Fee], instrument: Instrument, account: str,
             liquidity: str, currency: str, at_ms: int) -> tuple[Fee | None, list[str]]:
    """Join effective [start,end), requiring known account and availability."""
    bounded(fees)
    stamp(at_ms)
    text(account)
    if account == "UNKNOWN":
        return None, ["ACCOUNT_UNKNOWN"]
    matching = sorted((f for f in fees if f.instrument == instrument
                       and (f.account, f.liquidity, f.currency) ==
                       (account, liquidity, currency)), key=lambda f: f.start_ms)
    if any(a.end_ms > b.start_ms for a, b in zip(matching, matching[1:])):
        return None, ["FEE_INTERVAL_OVERLAP"]
    active = [f for f in matching if f.start_ms <= at_ms < f.end_ms]
    if not active:
        return None, ["FEE_MISSING_OR_INAPPLICABLE"]
    if active[0].available_ms > at_ms:
        return None, ["FEE_FUTURE_UNAVAILABLE"]
    return active[0], []


def funding_for_holding(holding: Holding, rows: list[Funding]) -> list[Funding]:
    """Scenario assignment only: entry inclusive, exit exclusive.

    Public settlement rates and this convention do NOT establish actual exchange
    ownership, historical schedule completeness, or measured account funding.
    Availability is preserved; realized settlements may be published after entry.
    A predictive entry-time feature must separately filter available_ms <= entry.
    """
    bounded(rows)
    if any(r.instrument != holding.instrument for r in rows):
        raise ValueError("funding instrument mismatch")
    ordered = sorted(rows, key=lambda r: r.settlement_ms)
    if any(a.settlement_ms == b.settlement_ms for a, b in zip(ordered, ordered[1:])):
        raise ValueError("duplicate funding settlement requires reconciliation")
    return [r for r in ordered if holding.entry_ms <= r.settlement_ms < holding.exit_ms]


def local_path(root: Path, name: str) -> Path:
    text(name)
    candidate = (root / name).resolve()
    if Path(name).is_absolute() or not candidate.is_relative_to(root.resolve()):
        raise ValueError("evidence paths must remain inside repository")
    return candidate


def read_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"file exceeds {MAX_BYTES} bytes: {path.name}")
    return raw


def reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(raw: bytes):
    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)


def decode_row(cls, row):
    if not isinstance(row, dict):
        raise ValueError("candidate row must be an object")
    values = dict(row)
    values["instrument"] = Instrument(**values["instrument"])
    values["source"] = Source(**values["source"])
    return cls(**values)


def object_value(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


LIMITATIONS = [
    "Hashes bind saved bytes, not provider truth, completeness or source applicability.",
    "Instrument identity/multiplier and policy are requested declarations, not historical contract evidence.",
    "No historical source verifier is implemented; non-synthetic candidates remain NOT_READY.",
    "As-of quotes/visible quantities are not depth continuity, executable fills or impact.",
    "Latency/staleness limits are declared policy, not measured scan/manual latency.",
    "Funding [entry,exit) is a scenario convention; actual exchange/account ownership UNKNOWN.",
    "Sparse funding pages/provisional current settlement grid do not prove historical coverage.",
    "12/22/37 bps are assumptions, not measured historical execution costs.",
    "Current margin tiers are not historical rules; G13 portfolio/margin/liquidation is outside scope.",
    "No orders, account cashflows, PnL or empirical execution validation.",
]


def audit(contract: dict, root: Path = ROOT) -> dict:
    """Audit supplied structural joins and saved manifests, never authorize trading."""
    required = {"schema_version", "mode", "instrument", "window", "policy",
                "manifest_refs", "candidate"}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError("contract fields must exactly match schema_version 1")
    if type(contract["schema_version"]) is not int or contract["schema_version"] != 1:
        raise ValueError("unsupported schema_version")
    if contract["mode"] not in ("EXISTING_EVIDENCE", "SYNTHETIC_ONLY"):
        raise ValueError("unsupported mode")
    instrument = Instrument(**contract["instrument"])
    window = contract["window"]
    if set(window) != {"start_ms", "end_ms"}:
        raise ValueError("window requires start_ms/end_ms")
    interval(**{"start": window["start_ms"], "end": window["end_ms"]})
    policy = contract["policy"]
    if set(policy) != {"max_quote_age_ms", "max_total_latency_ms"}:
        raise ValueError("invalid policy fields")
    for value in policy.values():
        duration(value)
    refs = contract["manifest_refs"]
    if not isinstance(refs, list) or len(refs) > MAX_REFS:
        raise ValueError("too many manifest references")
    reasons = set()
    evidence = []
    sources = {}
    for ref in refs:
        if set(ref) != {"path", "sha256", "role"}:
            raise ValueError("manifest reference requires path/sha256/role")
        Source(ref["path"], ref["sha256"], ref["role"])
        if ref["path"] in sources:
            raise ValueError("duplicate manifest path")
        path = local_path(root, ref["path"])
        record = dict(ref)
        sources[ref["path"]] = ref["sha256"]
        if not path.exists():
            record.update(status="MISSING", observed_sha256=None)
            reasons.add("MISSING_SOURCE_MANIFEST")
        else:
            raw = read_bytes(path)
            observed = hashlib.sha256(raw).hexdigest()
            doc = load_json(raw)
            if not isinstance(doc, dict):
                raise ValueError("source manifest must be JSON object")
            record.update(observed_sha256=observed, bytes=len(raw),
                          status="HASH_MATCH" if observed == ref["sha256"] else "HASH_MISMATCH")
            if observed != ref["sha256"]:
                reasons.add("EVIDENCE_HASH_MISMATCH")
            # Report actual saved source status, not caller readiness booleans.
            gate_doc = object_value(doc.get("execution_input_gate", {}), "execution_input_gate")
            saved_status = doc.get("status", gate_doc.get("status"))
            record["saved_status"] = str(saved_status)[:256]
            if ref["role"] == "funding_history":
                reasons.add("FUNDING_HISTORICAL_SCHEDULE_SOURCE_UNVERIFIED")
                symbols = object_value(doc.get("symbols", {}), "funding symbols")
                symbol = object_value(symbols.get(instrument.symbol, {}), "funding symbol")
                record["symbol_rows_reported"] = symbol.get("window_rows")
                record["historical_completeness"] = str(symbol.get("historical_completeness"))[:256]
            if ref["role"] in ("recent_replay", "cross_hour_replay"):
                record["use"] = "Internal replay consistency only; no historical fill authorization."
            if ref["role"] == "execution_metadata":
                reasons.add("HISTORICAL_DEPTH_AND_FEE_METADATA_SOURCE_UNVERIFIED")
            if ref["role"] == "acquisition":
                objects = doc.get("objects", [])
                if not isinstance(objects, list) or len(objects) > MAX_REFS:
                    raise ValueError("acquisition manifest exceeds object bound")
                record["book_objects"] = []
                for obj in objects:
                    object_value(obj, "acquisition object")
                    text(obj.get("object"))
                    if not obj.get("object", "").endswith("_orderbook.parquet"):
                        continue
                    clocks = object_value(obj.get("clock_ranges", {}), "clock ranges")
                    event_range = clocks.get("event_time", [])
                    if len(event_range) != 2:
                        reasons.add("BOOK_EVENT_CLOCK_MISSING")
                        continue
                    first, last = map(stamp, event_range)
                    if first > last:
                        raise ValueError("book event range reversed")
                    overlaps = first < window["end_ms"] and last >= window["start_ms"]
                    record["book_objects"].append({
                        "object": obj["object"], "event_time_ms": event_range,
                        "receive_time_ns": clocks.get("received_time"),
                        "requested_window_relation": "OVERLAPS_NOT_COMPLETENESS" if overlaps else "MISMATCH",
                        "reported_raw_sha256": obj.get("sha256"),
                    })
                    if not overlaps:
                        reasons.add("BOOK_TIME_WINDOW_MISMATCH")
        evidence.append(record)
    candidate = contract["candidate"]
    classes = {"signals": Signal, "quotes": Quote, "fees": Fee,
               "funding": Funding, "holdings": Holding}
    if not isinstance(candidate, dict) or set(candidate) != set(classes):
        raise ValueError("candidate requires signals/quotes/fees/funding/holdings lists")
    decoded = {}
    for name, cls in classes.items():
        bounded(candidate[name])
        rows = [decode_row(cls, row) for row in candidate[name]]
        decoded[name] = rows
        if not rows:
            reasons.add("MISSING_" + name.upper())
        for row in rows:
            if row.instrument != instrument:
                reasons.add("CANDIDATE_INSTRUMENT_MISMATCH")
            if sources.get(row.source.path) != row.source.sha256:
                reasons.add("ROW_SOURCE_NOT_BOUND_TO_MANIFEST")
            local_path(root, row.source.path)
    joins = []
    for signal in decoded["signals"]:
        if not window["start_ms"] <= signal.event_ms <= signal.decision_ms < window["end_ms"]:
            reasons.add("SIGNAL_OUTSIDE_REQUESTED_WINDOW")
        quote, errors = quote_asof(signal, decoded["quotes"], policy["max_quote_age_ms"],
                                   policy["max_total_latency_ms"])
        reasons.update(errors)
        joins.append({"decision_ms": signal.decision_ms,
                      "quote_event_ms": quote.event_ms if quote else None,
                      "reasons": errors})
    funding_counts = []
    for holding in decoded["holdings"]:
        if not window["start_ms"] <= holding.entry_ms < holding.exit_ms <= window["end_ms"]:
            reasons.add("HOLDING_OUTSIDE_REQUESTED_WINDOW")
        for at_ms in (holding.entry_ms, holding.exit_ms):
            _, errors = fee_asof(decoded["fees"], instrument, holding.account,
                                 "taker", instrument.settlement_currency, at_ms)
            reasons.update(errors)
        matched = funding_for_holding(holding, decoded["funding"])
        funding_counts.append(len(matched))
    if contract["mode"] != "SYNTHETIC_ONLY":
        reasons.update(("SOURCE_UNVERIFIED", "HISTORICAL_DEPTH_COVERAGE_UNVERIFIED",
                        "SCAN_MANUAL_LATENCY_SOURCE_UNVERIFIED",
                        "FUNDING_COVERAGE_UNVERIFIED", "ACCOUNT_OWNERSHIP_UNKNOWN"))
    status = "SYNTHETIC_ONLY" if not reasons else "NOT_READY"
    return {
        "schema_version": 1, "status": status, "authorizes_execution": False,
        "mode": contract["mode"], "instrument": asdict(instrument), "window": window,
        "policy_assumptions": policy, "reasons": sorted(reasons),
        "manifest_evidence": evidence, "candidate_counts": {k: len(v) for k, v in decoded.items()},
        "asof_joins": joins, "scenario_funding_counts": funding_counts,
        "actual_exchange_account_ownership": "UNKNOWN",
        "limitations": LIMITATIONS,
        "next_gates": {
            "G06": "Historical same-symbol/day depth initial state, clocks, gaps and cross-file continuity.",
            "G12": "Source-verified historical quotes/depth, measured latency, effective account fees, settlement schedules and ownership.",
            "G13": "After G12 and #8 inference: predeclared sizing/overlap and historical margin/liquidation/account rules; outside this package.",
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        output = local_path(ROOT, args.output)
        if output.suffix != ".json":
            raise ValueError("output must be a JSON report")
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}), file=sys.stderr)
        return 1
    protected = set()
    try:
        input_path = local_path(ROOT, args.contract)
        protected.add(input_path)
        if output in protected:
            raise ValueError("output must not overwrite the contract")
        raw = read_bytes(input_path)
        contract = load_json(raw)
        # Never overwrite any declared source, even when explicitly requested.
        if isinstance(contract, dict):
            for ref in contract.get("manifest_refs", []):
                if isinstance(ref, dict) and "path" in ref:
                    protected.add(local_path(ROOT, ref["path"]))
            if output in protected:
                raise ValueError("output must not overwrite an evidence source")
        report = audit(contract)
        report["contract"] = {"path": args.contract, "sha256": hashlib.sha256(raw).hexdigest()}
        code = 2
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, RecursionError) as exc:
        report = {"schema_version": 1, "status": "ERROR", "authorizes_execution": False,
                  "error": f"{type(exc).__name__}: {exc}"[:1000]}
        code = 1
    if output in protected:
        print(json.dumps(report, allow_nan=False), file=sys.stderr)
        return 1
    try:
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    except OSError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)[:1000]}), file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "output": args.output,
                      "reason_count": len(report.get("reasons", []))}))
    return code


if __name__ == "__main__":
    sys.exit(main())
