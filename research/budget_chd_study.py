"""Offline trade-first CHD study and book readiness audit; no strategy validation."""

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from itertools import groupby
from pathlib import Path

from research.trade_profile_window import profile


def number(value, positive=True):
    result = Decimal(str(value))
    if not result.is_finite() or (result <= 0 if positive else result < 0):
        raise ValueError("Expected finite positive price/quantity")
    return result


def integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Expected nonnegative integer timestamp/ID")
    return value


def trade_study(rows, symbol, start_ms, end_ms):
    """Trade-time bars; file presence alone never certifies a complete ledger."""
    if start_ms >= end_ms or start_ms % 60000 or end_ms % 60000:
        raise ValueError("Window must have ordered UTC minute boundaries")
    seen, trades, duplicates, outside = {}, [], 0, 0
    for row in rows:
        if row["symbol"] != symbol:
            raise ValueError("Unexpected symbol")
        stamp = integer(row["trade_time"])
        received = integer(row["received_time"])
        identity = integer(row["trade_id"])
        price, size = number(row["price"]), number(row["quantity"])
        if not isinstance(row["is_buyer_maker"], bool):
            raise ValueError("Maker flag must be boolean")
        fingerprint = (stamp, price, size, row["is_buyer_maker"])
        if identity in seen:
            if seen[identity] != fingerprint:
                raise ValueError("Conflicting duplicate trade ID")
            duplicates += 1
            continue
        seen[identity] = fingerprint
        if not start_ms <= stamp < end_ms:
            outside += 1
            continue
        trades.append({
            "stamp": stamp, "received": received, "price": price, "size": size,
            "maker": row["is_buyer_maker"],
        })
    if not trades:
        raise ValueError("No observed trades inside requested interval")
    # Stable ties preserve input ordering; tied exchange timestamps do not prove fill order.
    trades.sort(key=lambda t: t["stamp"])
    groups = defaultdict(list)
    for trade in trades:
        groups[trade["stamp"] // 60000 * 60000].append(trade)
    bars = []
    for stamp in range(start_ms, end_ms, 60000):
        group = groups.get(stamp, [])
        if not group:
            bars.append({"timestamp": stamp, "status": "NO_OBSERVED_TRADES_UNKNOWN_COVERAGE"})
            continue
        volume = sum(t["size"] for t in group)
        quote = sum(t["price"] * t["size"] for t in group)
        bars.append({
            "timestamp": stamp, "status": "OBSERVED_NOT_LEDGER_CERTIFIED",
            "open": str(group[0]["price"]), "high": str(max(t["price"] for t in group)),
            "low": str(min(t["price"] for t in group)), "close": str(group[-1]["price"]),
            "base_volume": str(volume), "quote_volume": str(quote),
            "vwap": str(quote / volume), "trades": len(group),
            "maker_flag_true_base_volume": str(sum(t["size"] for t in group if t["maker"])),
            "maker_flag_false_base_volume": str(sum(t["size"] for t in group if not t["maker"])),
            "available_not_before_receive_ns": max(
                (stamp + 60000) * 10**6, max(t["received"] for t in group)
            ),
        })
    return {
        "status": "DESCRIPTIVE_TRADE_ONLY", "symbol": symbol,
        "trade_time_window_ms": [start_ms, end_ms], "boundary": "[start,end)",
        "unique_observed_trades": len(trades), "identical_duplicates_removed": duplicates,
        "outside_window_trades": outside,
        "base_volume": str(sum(t["size"] for t in trades)),
        "minute_bars": bars,
        "whole_window_profile_ex_post": profile([
            {"price": str(t["price"]), "size": str(t["size"])} for t in trades
        ]),
        "cost_scenarios_round_trip_bps": [12, 22, 37],
        "limitations": [
            "Cost scenarios are assumptions, not measured spread/fills/slippage",
            "No strategy returns, significance, portfolio or efficacy claim",
            "Missing observations are not zero-volume bars; source file is not a ledger certificate",
            "Whole-window bins use the full observed range: descriptive, not a causal signal",
            "OHLC ordering among equal trade timestamps follows source row order",
            "Maker flags are reported without inferring universal aggressor-side semantics",
            "One receive-hour file may omit late trades needed for event-time boundary bars",
        ],
    }


def compare_candles(report, candles):
    """Compare like-for-like five-minute aggregates, never force a match."""
    groups = defaultdict(list)
    for bar in report["minute_bars"]:
        groups[bar["timestamp"] // 300000 * 300000].append(bar)
    comparisons = []
    for candle in candles:
        stamp = int(candle["timestamp"])
        if candle["symbol"] != report["symbol"] or stamp not in groups:
            continue
        bars = groups[stamp]
        if len(bars) != 5 or any("base_volume" not in b for b in bars):
            comparisons.append({"timestamp": stamp, "status": "INSUFFICIENT_OBSERVATIONS"})
            continue
        derived = {
            "open": Decimal(bars[0]["open"]), "close": Decimal(bars[-1]["close"]),
            "high": max(Decimal(b["high"]) for b in bars),
            "low": min(Decimal(b["low"]) for b in bars),
            "base_volume": sum(Decimal(b["base_volume"]) for b in bars),
            "quote_volume": sum(Decimal(b["quote_volume"]) for b in bars),
        }
        differences = {key: str(value - Decimal(candle[key])) for key, value in derived.items()}
        comparisons.append({
            "timestamp": stamp,
            "status": "EXACT_MATCH" if all(Decimal(v) == 0 for v in differences.values()) else "DIFFERENCES",
            "trade_minus_saved_candle": differences,
        })
    return {
        "interval_ms": 300000, "comparisons": comparisons,
        "limitation": "Agreement is sampled consistency, not independent ledger completeness; no values adjusted",
    }


def book_readiness(rows, symbol):
    counts = defaultdict(int)
    snapshots = set()
    update_messages = {}
    missing_previous = set()
    for row in rows:
        if row["symbol"] != symbol or row["event_type"] not in ("snapshot", "update"):
            raise ValueError("Unexpected book symbol/event type")
        counts[row["event_type"]] += 1
        key = (integer(row["received_time"]), row["final_update_id"])
        if row["event_type"] == "snapshot":
            snapshots.add(key)
        else:
            previous = row["prev_final_update_id"]
            if key in update_messages and update_messages[key] != previous:
                raise ValueError("Inconsistent sequence fields within a book message")
            update_messages[key] = previous
            if previous is None or row["final_update_id"] is None:
                missing_previous.add(key)
    if not counts:
        raise ValueError("Empty book source")
    return {
        "symbol": symbol,
        "status": "CANDIDATE_REQUIRES_REPLAY" if snapshots and not missing_previous
        else "NOT_REPLAY_READY",
        "rows_by_event": dict(counts), "snapshot_message_candidates": len(snapshots),
        "update_message_candidates": len(update_messages),
        "updates_without_chain_fields": len(missing_previous),
        "limitations": [
            "Readiness audit only; message grouping is provisional and no book reconstructed",
            "Presence of snapshots/IDs does not prove continuity, completeness or executable liquidity",
            "Separate exploratory period: never replaces reserved or original study observations",
        ],
    }


def checkpoint_book(checkpoint, symbol):
    if (checkpoint.get("schema") != "chd-bitget-derived-checkpoint-v1"
            or checkpoint.get("exchange") != "bitget_futures"
            or checkpoint.get("symbol") != symbol
            or not re.fullmatch(r"[a-f0-9]{64}", checkpoint.get("source_sha256", ""))):
        raise ValueError("Incompatible checkpoint provenance/schema/symbol")
    integer(checkpoint["received_ns"])
    integer(checkpoint["final_update_id"])
    book = {"bid": {}, "ask": {}}
    for side, key in (("bid", "bids"), ("ask", "asks")):
        for price, size in checkpoint[key]:
            price, size = number(price), number(size)
            if price in book[side]:
                raise ValueError("Duplicate checkpoint level")
            book[side][price] = size
    if sum(map(len, book.values())) > 10000:
        raise ValueError("Checkpoint exceeds level budget")
    if book["bid"] and book["ask"] and max(book["bid"]) >= min(book["ask"]):
        raise ValueError("Locked or crossed checkpoint")
    return book


def replay_book(rows, symbol, initial_checkpoint=None):
    """Conservative message-level seq/pseq replay; never bridge an unproved gap."""
    book = {"bid": {}, "ask": {}}
    previous_seq, previous_receive = None, None
    valid, messages, snapshots, gaps, discarded, quoted = False, 0, 0, 0, 0, 0
    errors = []
    last_summary = None
    spread_sum, spread_min, spread_max = Decimal(0), None, None
    last_stamp = None
    handover = "NO_IMPORTED_STATE"
    if initial_checkpoint is not None:
        book = checkpoint_book(initial_checkpoint, symbol)
        previous_seq = initial_checkpoint["final_update_id"]
        previous_receive = initial_checkpoint["received_ns"]
        valid = True
        handover = "PENDING"
    for key, iterator in groupby(rows, key=lambda r: (
        r["received_time"], r["event_type"], r["final_update_id"],
    )):
        message = []
        for row in iterator:
            if len(message) >= 2000:
                raise ValueError("Book message exceeds 2000-level budget")
            message.append(row)
        received, event, seq = key
        integer(received)
        integer(seq)
        if event not in ("snapshot", "update"):
            raise ValueError("Unknown book event")
        if previous_receive is not None and received < previous_receive:
            raise ValueError("Published receive order moved backward")
        previous_receive = received
        prev = message[0]["prev_final_update_id"]
        if prev is not None:
            integer(prev)
        event_time = integer(message[0]["event_time"])
        for row in message:
            if (row["symbol"] != symbol or row["prev_final_update_id"] != prev
                    or row["event_time"] != event_time):
                raise ValueError("Inconsistent metadata within message")
        messages += 1
        if event == "snapshot":
            prior_book = book
            prior_seq = previous_seq
            snapshots += 1
            book = {"bid": {}, "ask": {}}
            valid = True
        elif not valid:
            discarded += 1
            continue
        elif prev is None or prev != previous_seq or seq <= previous_seq:
            gaps += 1
            if len(errors) < 100:
                errors.append({"received_ns": received, "expected_previous": previous_seq,
                               "observed_previous": prev, "final_update_id": seq})
            valid = False
            book = {"bid": {}, "ask": {}}
            discarded += 1
            if messages == 1 and initial_checkpoint is not None:
                handover = "UNVERIFIED_GAP"
            continue
        levels = set()
        for row in message:
            side = row["side"]
            if side == "noop":
                if len(message) != 1 or Decimal(row["price"]) != 0 or Decimal(row["quantity"]) != 0:
                    raise ValueError("Malformed noop message")
                continue
            if side not in book:
                raise ValueError("Unknown order-book side")
            price, size = number(row["price"]), number(row["quantity"], positive=False)
            if (side, price) in levels:
                raise ValueError("Duplicate level within message")
            levels.add((side, price))
            if event == "snapshot" and size == 0:
                raise ValueError("Snapshot contains zero quantity")
            if size == 0:
                book[side].pop(price, None)
            else:
                book[side][price] = size
        if messages == 1 and initial_checkpoint is not None:
            if event == "snapshot":
                handover = (
                    "EXACT_SNAPSHOT_HANDOVER"
                    if seq == prior_seq and book == prior_book else "RESET_WITHOUT_CONTINUITY"
                )
            else:
                handover = "PSEQ_LINKED_HANDOVER"
        if sum(map(len, book.values())) > 10000:
            raise ValueError("Replayed state exceeds 10000-level budget")
        previous_seq, last_stamp = seq, received
        if book["bid"] and book["ask"]:
            bid, ask = max(book["bid"]), min(book["ask"])
            if bid >= ask:
                valid = False
                gaps += 1
                if len(errors) < 100:
                    errors.append({"received_ns": received, "reason": "LOCKED_OR_CROSSED_BOOK"})
                book = {"bid": {}, "ask": {}}
                continue
            spread = Decimal(10000) * (ask - bid) / ((ask + bid) / 2)
            quoted += 1
            spread_sum += spread
            spread_min = spread if spread_min is None else min(spread_min, spread)
            spread_max = spread if spread_max is None else max(spread_max, spread)
            last_summary = {"best_bid": str(bid), "best_ask": str(ask), "spread_bps": str(spread)}
        else:
            last_summary = None
    if not messages:
        raise ValueError("Empty book source")
    checkpoint = None
    if valid:
        checkpoint = {
            "schema": "chd-bitget-derived-checkpoint-v1", "exchange": "bitget_futures",
            "symbol": symbol, "received_ns": last_stamp, "final_update_id": previous_seq,
            "semantics": "Derived observed state; import requires verified source/hash and boundary continuity",
            "bids": [[str(p), str(q)] for p, q in sorted(book["bid"].items(), reverse=True)],
            "asks": [[str(p), str(q)] for p, q in sorted(book["ask"].items())],
        }
    return {
        "symbol": symbol,
        "status": "SEQUENCE_CONSISTENT_SAMPLE" if checkpoint and quoted and gaps == 0 and discarded == 0
        and handover in ("NO_IMPORTED_STATE", "EXACT_SNAPSHOT_HANDOVER", "PSEQ_LINKED_HANDOVER")
        else "REPLAY_HAS_UNVERIFIED_INTERVALS",
        "messages": messages, "snapshots": snapshots, "gap_or_cross_events": gaps,
        "imported_state_handover": handover,
        "discarded_before_valid_snapshot_or_after_gap": discarded,
        "quoted_message_states": quoted, "final_state_sequence_consistent": valid,
        "last_valid_quote": last_summary if valid else None,
        "message_weighted_spread_bps": {
            "minimum": str(spread_min) if quoted else None,
            "maximum": str(spread_max) if quoted else None,
            "mean": str(spread_sum / quoted) if quoted else None,
        },
        "gap_examples_capped_at_100": errors,
        "limitations": [
            "Within-file seq/pseq consistency, not independent exchange completeness or checksum certification",
            "Provider snapshot and message grouping assumed as documented; missing entire snapshot levels cannot be independently detected",
            "Event-weighted spreads, not time-weighted averages, guaranteed fills or realized trading costs",
            "Separate exploratory window only; original September and reserved future samples unchanged",
        ],
    }, checkpoint


def parse_ms(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Explicit timezone required")
    return int(stamp.timestamp() * 1000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("trades", "book", "replay"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--symbol", default="AAPLUSDT")
    parser.add_argument("--start", default="2026-09-17T14:00:00Z")
    parser.add_argument("--end", default="2026-09-17T15:00:00Z")
    parser.add_argument("--candles", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, help="Optional NEW local checkpoint path for replay")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing report")
    if args.checkpoint and (args.mode != "replay" or args.checkpoint.exists()):
        parser.error("Checkpoint requires replay mode and a new path")
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("Use the CHD virtual environment with PyArrow installed") from exc
    try:
        if args.source.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Offline sample exceeds 20MiB budget")
        parquet = pq.ParquetFile(args.source)
        if parquet.metadata.num_rows > 2_000_000:
            raise ValueError("Offline sample exceeds two-million-row budget")
        rows = (r for batch in parquet.iter_batches(batch_size=8192) for r in batch.to_pylist())
        if args.mode == "trades":
            report = trade_study(rows, args.symbol, parse_ms(args.start), parse_ms(args.end))
            if args.candles:
                with gzip.open(args.candles, "rt") as source:
                    report["saved_5m_candle_comparison"] = compare_candles(report, csv.DictReader(source))
                report["saved_candle_source_sha256"] = hashlib.sha256(args.candles.read_bytes()).hexdigest()
        elif args.mode == "book":
            report = book_readiness(rows, args.symbol)
        else:
            report, checkpoint = replay_book(rows, args.symbol)
            if args.checkpoint and checkpoint is not None:
                checkpoint["source_sha256"] = hashlib.sha256(args.source.read_bytes()).hexdigest()
                with args.checkpoint.open("x") as output:
                    json.dump(checkpoint, output, indent=2)
                    output.write("\n")
                report["derived_checkpoint"] = {
                    "path": str(args.checkpoint),
                    "sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
                }
        report["source"] = {
            "path": str(args.source), "sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
            "bytes": args.source.stat().st_size, "parquet_rows": parquet.metadata.num_rows,
        }
        with args.output.open("x") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
        print(json.dumps({"status": report["status"], "output": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise SystemExit(f"Study failed; no success report: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
