"""Pre-registered sentiment-v1 (+ v1.1 Binance-history stage) rules, discovery/confirmation selection and gates (pure, no network).

Protocol: research/results/sentiment-protocol-2026-11-05.json. Descriptive only: the day-block
sign-flip test is NOT validated (v1-v3 failed size control under serial dependence). No efficacy
claim, no trading advice.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import io
import signal
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

BAR_MS = 300_000
DAY_MS = 86_400_000
H = 12
COSTS_BP = (12, 22, 37)
PRIMARY_COST_BP = 22
ALPHA = 0.05
MIN_EVENTS = 30
MIN_EFFECT_BP = 5.0
MIN_CONF_BLOCKS = 20
MIN_DAYS = 60
MIN_COVERAGE_PCT = 95.0
MAX_GAP_SECONDS = 60.0
DISCOVERY_FRACTION = 0.60
EMBARGO_DAYS = 1
PLATEAU_KEEP = 0.5
MAX_RUNTIME = 100
PERM_SEED = 20261105

RULES = {
    "R1_crowded_long_squeeze": {"side": -1, "default": 0.70,
                                "grid": (0.60, 0.65, 0.70, 0.75, 0.80, 0.85)},
    "R2_crowded_short_squeeze": {"side": 1, "default": 0.70,
                                 "grid": (0.60, 0.65, 0.70, 0.75, 0.80, 0.85)},
    "R3_healthy_trend_rising_oi": {"side": 1, "default": 0.02, "grid": (0.01, 0.02, 0.03, 0.05)},
    "R4_oi_flush_after_squeeze": {"side": 1, "default": 0.02, "grid": (0.01, 0.02, 0.03, 0.05)},
    "R5_exhaustion": {"side": -1, "default": 0.02, "grid": (0.01, 0.02, 0.03, 0.04)},
    # v1.2 community priors (recalled, unverified); side 0 => direction taken per bar by side_for()
    "R6_funding_extreme_contrarian": {"side": 0, "default": 0.0005,
                                      "grid": (0.0002, 0.0003, 0.0005, 0.0010),
                                      "source": "community_prior (recalled, unverified)"},
    "R7_top_vs_crowd_divergence": {"side": 0, "default": 0.10, "grid": (0.05, 0.10, 0.15, 0.20),
                                   "source": "community_prior (recalled, unverified)"},
    "R8_oi_price_divergence": {"side": 1, "default": 0.02, "grid": (0.01, 0.02, 0.03, 0.05),
                               "source": "community_prior (recalled, unverified)"},
}
assert len(RULES) <= 8
FUNDING_MAX_AGE_BARS = 96  # 8h funding interval; older values are not carried forward
GRID_TOTAL = sum(len(r["grid"]) for r in RULES.values())
TREND_MIN_RET = 0.005


def signal_fires(rule, level, f):
    """f: feature dict for one bar (None values => no signal)."""
    try:
        if rule == "R1_crowded_long_squeeze":
            return f["long_ratio"] >= level - 1e-12
        if rule == "R2_crowded_short_squeeze":
            return f["long_ratio"] <= 1 - level + 1e-12
        if rule == "R3_healthy_trend_rising_oi":
            return f["ret"] >= TREND_MIN_RET and f["oi_chg"] >= level - 1e-12
        if rule == "R4_oi_flush_after_squeeze":
            return f["oi_chg"] <= -level + 1e-12 and f["ret"] <= 0
        if rule == "R5_exhaustion":
            return f["ret"] >= level - 1e-12 and f["taker_buy_share"] <= 0.5
        if rule == "R6_funding_extreme_contrarian":
            return abs(f["funding"]) >= level - 1e-12
        if rule == "R7_top_vs_crowd_divergence":
            return abs(f["top_long_ratio"] - f["long_ratio"]) >= level - 1e-12
        if rule == "R8_oi_price_divergence":
            return f["oi_chg"] >= level - 1e-12 and f["ret"] <= 0
    except (KeyError, TypeError):
        return False
    raise ValueError("unknown rule " + rule)


def side_for(rule, f):
    """Trade side for a fired signal. R6 contrarian to funding sign; R7 follows top traders vs crowd."""
    if rule == "R6_funding_extreme_contrarian":
        return -1 if f["funding"] > 0 else 1
    if rule == "R7_top_vs_crowd_divergence":
        return 1 if f["top_long_ratio"] > f["long_ratio"] else -1
    return RULES[rule]["side"]


def build_table(rows):
    """rows: dict bar_index -> {'close','oi','long_ratio','taker_buy_share'} (any may be missing).

    Returns sorted list of per-bar dicts with 12-bar lookbacks computed only from past bars.
    """
    table = []
    for i in sorted(rows):
        r = rows[i]
        p = rows.get(i - H, {})
        f = {"bar": i, "close": r.get("close"), "long_ratio": r.get("long_ratio")}
        if r.get("close") and p.get("close"):
            f["ret"] = r["close"] / p["close"] - 1
        if r.get("oi") and p.get("oi"):
            f["oi_chg"] = r["oi"] / p["oi"] - 1
        shares = [rows.get(j, {}).get("taker_buy_share") for j in range(i - H + 1, i + 1)]
        if all(s is not None for s in shares):
            f["taker_buy_share"] = sum(shares) / H
        if r.get("top_long_ratio") is not None:
            f["top_long_ratio"] = r["top_long_ratio"]
        for j in range(i, i - FUNDING_MAX_AGE_BARS, -1):  # latest settled funding, past bars only
            fv = rows.get(j, {}).get("funding")
            if fv is not None:
                f["funding"] = fv
                break
        table.append(f)
    return table


def events(rule, level, table, closes, lo_bar, hi_bar):
    """Non-overlapping events with signal bar in [lo_bar, hi_bar); returns [(bar, gross_return)]."""
    out, free_at = [], -1
    for f in table:
        b = f["bar"]
        if b < lo_bar or b >= hi_bar or b < free_at:
            continue
        if not signal_fires(rule, level, f):
            continue
        entry, exit_ = closes.get(b + 1), closes.get(b + 1 + H)
        if not entry or not exit_:
            continue
        out.append((b, side_for(rule, f) * (exit_ / entry - 1)))
        free_at = b + 1 + H
    return out


def summarize(evs, cost_bp=PRIMARY_COST_BP):
    n = len(evs)
    gross = sum(g for _, g in evs) / n if n else 0.0
    return {"n": n, "gross_mean_bp": gross * 1e4, "net_mean_bp": gross * 1e4 - cost_bp}


def segment_bounds(first_bar, last_bar):
    """Discovery / embargo / confirmation bar ranges by whole days."""
    days = (last_bar - first_bar + 1) * BAR_MS // DAY_MS
    disc_days = int(days * DISCOVERY_FRACTION)
    per_day = DAY_MS // BAR_MS
    d_hi = first_bar + disc_days * per_day
    c_lo = d_hi + EMBARGO_DAYS * per_day
    return (first_bar, d_hi), (c_lo, last_bar + 1)


def select_level(rule, table, closes, disc):
    """Discovery-only selection. Returns frozen selection dict (status candidate or narrative_default)."""
    spec = RULES[rule]
    per_level = []
    for lvl in spec["grid"]:
        s = summarize(events(rule, lvl, table, closes, *disc))
        per_level.append({"level": lvl, **s})
    eligible = [p for p in per_level if p["n"] >= MIN_EVENTS]
    best = max(eligible, key=lambda p: (round(p["net_mean_bp"], 9), -spec["grid"].index(p["level"])),
               default=None)
    sel = {"rule": rule, "discovery": per_level, "selected_level": spec["default"],
           "status": "narrative_default", "reason": None}
    if best is None:
        sel["reason"] = "no level reaches %d discovery events" % MIN_EVENTS
    elif best["net_mean_bp"] <= 0:
        sel["reason"] = "best discovery net mean <= 0 at %dbp" % PRIMARY_COST_BP
    elif not plateau_ok(per_level, best["level"], spec["grid"]):
        sel["reason"] = "discovery spike, not a plateau"
    else:
        sel.update(selected_level=best["level"], status="candidate")
    sel["frozen_sha256"] = hashlib.sha256(json.dumps(
        {k: sel[k] for k in ("rule", "selected_level", "status")}, sort_keys=True).encode()).hexdigest()
    return sel


def neighbours(level, grid):
    i = grid.index(level)
    return [grid[j] for j in (i - 1, i + 1) if 0 <= j < len(grid)]


def plateau_ok(per_level, level, grid):
    """Neighbouring levels must keep the sign and >= 50% of the selected level's gross effect."""
    by = {p["level"]: p for p in per_level}
    sel = by[level]["gross_mean_bp"]
    if sel <= 0:
        return False
    for nb in neighbours(level, grid):
        p = by[nb]
        if p["n"] < MIN_EVENTS or p["gross_mean_bp"] < PLATEAU_KEEP * sel:
            return False
    return True


def sign_flip_p(block_means):
    """Exact one-sided day-block sign-flip p (descriptive; size control NOT validated).

    Refuses (None) below MIN_CONF_BLOCKS blocks.
    """
    k = len(block_means)
    if k < MIN_CONF_BLOCKS:
        return None
    obs = sum(block_means)
    if k <= 16:
        count = 0
        for mask in range(1 << k):
            s = sum(m if mask >> i & 1 else -m for i, m in enumerate(block_means))
            count += s >= obs - 1e-12
        return count / (1 << k)
    import random
    rng = random.Random(PERM_SEED)
    n = 20000
    count = sum(sum(m if rng.random() < 0.5 else -m for m in block_means) >= obs - 1e-12
                for _ in range(n))
    return (count + 1) / (n + 1)


def holm(pvalues, m):
    """Holm over m hypotheses (m = full grid size); returns adjusted p for the supplied ones."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adj, running = [None] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj


def confirm_once(frozen, table, closes, conf, ledger, block_days=1):
    """Evaluate the FROZEN level once on confirmation. No re-selection, no other levels chosen."""
    rule, level = frozen["rule"], frozen["selected_level"]
    spec = RULES[rule]
    check = hashlib.sha256(json.dumps({k: frozen[k] for k in ("rule", "selected_level", "status")},
                                      sort_keys=True).encode()).hexdigest()
    if check != frozen["frozen_sha256"]:
        raise ValueError("frozen selection was modified")
    if rule in ledger:
        raise RuntimeError("confirmation already used for " + rule)
    ledger[rule] = frozen["frozen_sha256"]
    evs = events(rule, level, table, closes, *conf)
    out = {"rule": rule, "level": level, "prior_status": frozen["status"],
           "scenarios": {str(c): summarize(evs, c) for c in COSTS_BP}}
    blocks = {}
    for b, g in evs:
        blocks.setdefault(b // (block_days * DAY_MS // BAR_MS), []).append(g * 1e4 - PRIMARY_COST_BP)
    means = [sum(v) / len(v) for _, v in sorted(blocks.items())]
    out["day_blocks"] = len(means)
    out["block_days"] = block_days
    out["p_raw"] = sign_flip_p(means)
    out["neighbour_gross_bp"] = {str(nb): summarize(events(rule, nb, table, closes, *conf))["gross_mean_bp"]
                                 for nb in neighbours(level, spec["grid"])}
    return out


def verdict(frozen, conf_result, p_holm):
    """Final label for one rule. 'proven' needs every pre-declared criterion."""
    if frozen["status"] != "candidate":
        return "not_proven", ["not a discovery candidate: " + str(frozen["reason"])]
    s = conf_result["scenarios"][str(PRIMARY_COST_BP)]
    fails = []
    if s["n"] < MIN_EVENTS:
        fails.append("events<%d" % MIN_EVENTS)
    if s["net_mean_bp"] < MIN_EFFECT_BP:
        fails.append("net_mean<%gbp" % MIN_EFFECT_BP)
    if s["gross_mean_bp"] > 0 and any(v <= 0 for v in conf_result["neighbour_gross_bp"].values()):
        fails.append("confirmation_plateau")
    if conf_result["p_raw"] is None:
        fails.append("insufficient_blocks")
    elif p_holm is None or p_holm >= ALPHA:
        fails.append("holm_p>=%g" % ALPHA)
    return ("proven" if not fails else "not_proven"), fails


def gate_report(n_days, integrity):
    """integrity: dict from recorder.integrity_report.scan (needs ok, coverage_ok)."""
    failed = []
    if n_days < MIN_DAYS:
        failed.append("days %d < %d" % (n_days, MIN_DAYS))
    if not integrity.get("ok"):
        failed.append("integrity_not_ok")
    if not integrity.get("coverage_ok"):
        failed.append("coverage_below_%g%%" % MIN_COVERAGE_PCT)
    if int(n_days * (1 - DISCOVERY_FRACTION)) - EMBARGO_DAYS < MIN_CONF_BLOCKS:
        failed.append("confirmation_blocks<%d" % MIN_CONF_BLOCKS)
    return failed


def load_rows(root, symbol="BTCUSDT"):
    """Read recorder partitions into bar_index -> fields (last value per 5m bucket by available_ms)."""
    rows = {}
    for path in sorted(Path(root).glob("*/*/*/*/records.jsonl.gz")):
        try:
            text = gzip.decompress(path.read_bytes()).decode()
        except (OSError, EOFError, ValueError):
            continue
        for line in text.splitlines():
            try:
                rec = json.loads(line)
                if rec["instrument"]["symbol"] != symbol:
                    continue
                fl = rec["fields"]
                if fl.get("no_data"):
                    continue
                row = rows.setdefault(rec["available_ms"] // BAR_MS, {})
                kind = rec["kind"]
                if kind == "ticker" and fl.get("last"):
                    row["close"] = float(fl["last"])
                elif kind == "open_interest" and fl.get("open_interest"):
                    row["oi"] = float(fl["open_interest"])
                elif kind == "long_short" and fl.get("long_ratio"):
                    v = float(fl["long_ratio"])
                    row["long_ratio"] = v / 100 if v > 1 else v
                elif kind == "taker_buy_sell" and fl.get("buy_volume") and fl.get("sell_volume"):
                    b, s = float(fl["buy_volume"]), float(fl["sell_volume"])
                    if b + s > 0:
                        row["taker_buy_share"] = b / (b + s)
            except (ValueError, KeyError, TypeError):
                continue
    return rows


def run(root):
    """Dry, finite runner: returns (verdict_dict, exit_code). NOT_READY => exit 2."""
    root = Path(root)
    rows = load_rows(root) if root.is_dir() else {}
    if not rows:
        return {"verdict": "NOT_READY", "label": "INCONCLUSIVE", "failed_gates": ["no_recorder_data"],
                "claim": "none"}, 2
    try:
        from research.recorder.integrity_report import scan
    except ImportError:
        from recorder.integrity_report import scan
    integrity = scan(root, MAX_GAP_SECONDS, MIN_COVERAGE_PCT)
    sent = [b for b, r in rows.items() if "oi" in r or "long_ratio" in r]
    n_days = ((max(sent) - min(sent) + 1) * BAR_MS // DAY_MS) if sent else 0
    failed = gate_report(n_days, integrity)
    if failed:
        return {"verdict": "NOT_READY", "label": "INCONCLUSIVE", "failed_gates": failed,
                "days": n_days, "claim": "none"}, 2
    table = build_table(rows)
    closes = {b: r["close"] for b, r in rows.items() if r.get("close")}
    disc, conf = segment_bounds(min(rows), max(rows))
    ledger, results, ps = {}, [], []
    for rule in RULES:
        frozen = select_level(rule, table, closes, disc)
        res = confirm_once(frozen, table, closes, conf, ledger)
        results.append((frozen, res))
        ps.append(res["p_raw"] if res["p_raw"] is not None else 1.0)
    adj = holm(ps, GRID_TOTAL)
    out = []
    for (frozen, res), p in zip(results, adj):
        label, fails = verdict(frozen, res, p)
        out.append({"rule": frozen["rule"], "level": frozen["selected_level"], "label": label,
                    "failed_criteria": fails, "p_holm_descriptive": p, "confirmation": res})
    return {"verdict": "COMPLETE_DESCRIPTIVE", "claim": "none; descriptive, test size control not validated",
            "rules": out}, 0


# ---- Binance USD-M archive stage (protocol v1.1): source-venue study, never a Bitget claim ----
BINANCE_START = date(2022, 1, 1)
BINANCE_END = date(2026, 10, 31)
BINANCE_DISC_END = date(2024, 11, 24)
BINANCE_EMBARGO = date(2024, 11, 25)
BINANCE_CONF_START = date(2024, 11, 26)
BINANCE_BLOCK_DAYS = 5
BINANCE_MIN_DAY_COVERAGE_PCT = 95.0
BINANCE_MIN_BARS_PER_DAY_PCT = 95.0


def _day_bar(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000) // BAR_MS


def binance_segments():
    """Frozen declared split: discovery [start, 2024-11-24], embargo 2024-11-25, confirmation after."""
    return ((_day_bar(BINANCE_START), _day_bar(BINANCE_DISC_END) + DAY_MS // BAR_MS),
            (_day_bar(BINANCE_CONF_START), _day_bar(BINANCE_END) + DAY_MS // BAR_MS))


def _ts_ms(v):
    v = v.strip()
    if v.isdigit():
        n = int(v)
        return n // 1000 if n > 10 ** 14 else n
    dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _csv_text(data):
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return z.read(z.namelist()[0]).decode()
    return data.decode()


def _ratio_share(v):
    r = float(v)
    return r / (1 + r) if r >= 0 else None


def parse_metrics_csv(data, rows):
    """Binance metrics CSV (bytes of csv or zip) -> rows[bar]: oi, long_ratio, taker_buy_share.

    long_ratio = share of accounts long from count_long_short_ratio (global accounts ratio L/S);
    taker_buy_share = buy/(buy+sell) from sum_taker_long_short_vol_ratio. Rows with unparsable
    fields are skipped per field, never filled.
    """
    n = 0
    for rec in csv.DictReader(io.StringIO(_csv_text(data))):
        try:
            bar = _ts_ms(rec["create_time"]) // BAR_MS
        except (ValueError, KeyError, AttributeError):
            continue
        row = rows.setdefault(bar, {})
        try:
            oi = float(rec["sum_open_interest"])
            if oi > 0:
                row["oi"] = oi
        except (ValueError, KeyError, TypeError):
            pass
        for key, field, conv in (("long_ratio", "count_long_short_ratio", _ratio_share),
                                 ("top_long_ratio", "sum_toptrader_long_short_ratio", _ratio_share),
                                 ("taker_buy_share", "sum_taker_long_short_vol_ratio", _ratio_share)):
            try:
                v = conv(rec[field])
                if v is not None:
                    row[key] = v
            except (ValueError, KeyError, TypeError):
                pass
        n += 1
    return n


def parse_funding_csv(data, rows):
    """Binance fundingRate CSV (calc_time, funding_interval_hours, last_funding_rate) -> rows[bar]['funding'].

    Bar = settlement-time bucket; the value is only used from that bar onward (no look-ahead).
    """
    n = 0
    for rec in csv.DictReader(io.StringIO(_csv_text(data))):
        try:
            bar = _ts_ms(rec["calc_time"]) // BAR_MS
            rows.setdefault(bar, {})["funding"] = float(rec["last_funding_rate"])
            n += 1
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return n


def parse_klines_csv(data, rows):
    """Binance 5m kline CSV -> rows[bar]['close']; bar = close-time bucket (open + 5m), no look-ahead."""
    n = 0
    for line in csv.reader(io.StringIO(_csv_text(data))):
        if len(line) < 5 or not line[0].strip().isdigit():
            continue
        try:
            bar = _ts_ms(line[0]) // BAR_MS + 1
            c = float(line[4])
        except ValueError:
            continue
        if c > 0:
            rows.setdefault(bar, {})["close"] = c
            n += 1
    return n


def load_binance(metrics_dir, klines_dir, symbol, funding_dir=None):
    rows = {}
    for p in sorted((Path(funding_dir) / symbol).glob("*.zip")) if funding_dir else []:
        try:
            parse_funding_csv(p.read_bytes(), rows)
        except (zipfile.BadZipFile, OSError, KeyError, UnicodeDecodeError):
            continue
    for p in sorted((Path(metrics_dir) / symbol).glob("*.zip")) if metrics_dir else []:
        try:
            parse_metrics_csv(p.read_bytes(), rows)
        except (zipfile.BadZipFile, OSError, KeyError, UnicodeDecodeError):
            continue
    for p in sorted((Path(klines_dir) / symbol).glob("*.zip")) if klines_dir else []:
        try:
            parse_klines_csv(p.read_bytes(), rows)
        except (zipfile.BadZipFile, OSError, KeyError, UnicodeDecodeError):
            continue
    return rows


def binance_gate(rows, start=None, end=None):
    """Day coverage: a day counts only if >=95% of its 288 bars have oi+long_ratio+taker and a close."""
    start = start or BINANCE_START
    end = end or BINANCE_END
    per_day = DAY_MS // BAR_MS
    need = math.ceil(per_day * BINANCE_MIN_BARS_PER_DAY_PCT / 100)
    b0, total = _day_bar(start), (end - start).days + 1
    good = 0
    for d in range(total):
        cnt = sum(1 for b in range(b0 + d * per_day, b0 + (d + 1) * per_day)
                  if all(k in rows.get(b, {}) for k in ("oi", "long_ratio", "taker_buy_share", "close")))
        good += cnt >= need
    pct = 100.0 * good / total
    failed = []
    if pct < BINANCE_MIN_DAY_COVERAGE_PCT:
        failed.append("day_coverage %.1f%% < %g%%" % (pct, BINANCE_MIN_DAY_COVERAGE_PCT))
    conf_days = (BINANCE_END - BINANCE_CONF_START).days + 1
    if conf_days // BINANCE_BLOCK_DAYS < MIN_CONF_BLOCKS:
        failed.append("confirmation_blocks<%d" % MIN_CONF_BLOCKS)
    return failed, pct


V12_FIELD_NEEDS = {"R6_funding_extreme_contrarian": "funding", "R7_top_vs_crowd_divergence": "top_long_ratio"}
V12_MIN_FIELD_DAY_PCT = 95.0


def rule_data_ok(rule, rows, start=None, end=None):
    """v1.2 per-rule data gate: >=95% of declared days carry the extra field (funding: >=2 settlements)."""
    field = V12_FIELD_NEEDS.get(rule)
    if field is None:
        return True
    start, end = start or BINANCE_START, end or BINANCE_END
    per_day, b0, total = DAY_MS // BAR_MS, _day_bar(start), (end - start).days + 1
    need = 2 if field == "funding" else math.ceil(per_day * 0.95)
    good = sum(1 for d in range(total)
               if sum(1 for b in range(b0 + d * per_day, b0 + (d + 1) * per_day)
                      if rows.get(b, {}).get(field) is not None) >= need)
    return 100.0 * good / total >= V12_MIN_FIELD_DAY_PCT


def run_binance(metrics_dir, klines_dir, symbol="BTCUSDT", funding_dir=None):
    """Binance-history stage (source venue). Gate failure => NOT_READY exit 2, nothing evaluated."""
    rows = load_binance(metrics_dir, klines_dir, symbol, funding_dir)
    if not rows:
        return {"stage": "binance_history", "verdict": "NOT_READY", "label": "INCONCLUSIVE",
                "failed_gates": ["no_binance_data"], "claim": "none"}, 2
    failed, pct = binance_gate(rows)
    if failed:
        return {"stage": "binance_history", "verdict": "NOT_READY", "label": "INCONCLUSIVE",
                "failed_gates": failed, "day_coverage_pct": pct, "claim": "none"}, 2
    table = build_table(rows)
    closes = {b: r["close"] for b, r in rows.items() if r.get("close")}
    disc, conf = binance_segments()
    ledger, results, ps, skipped = {}, [], [], []
    for rule in RULES:
        if not rule_data_ok(rule, rows):
            skipped.append(rule)  # Holm family size stays GRID_TOTAL (conservative)
            continue
        frozen = select_level(rule, table, closes, disc)
        res = confirm_once(frozen, table, closes, conf, ledger, BINANCE_BLOCK_DAYS)
        results.append((frozen, res))
        ps.append(res["p_raw"] if res["p_raw"] is not None else 1.0)
    adj = holm(ps, GRID_TOTAL)
    out = []
    for (frozen, res), p in zip(results, adj):
        label, fails = verdict(frozen, res, p)
        out.append({"rule": frozen["rule"], "level": frozen["selected_level"], "label": label,
                    "failed_criteria": fails, "p_holm_descriptive": p, "confirmation": res})
    return {"stage": "binance_history", "symbol": symbol, "verdict": "COMPLETE_DESCRIPTIVE",
            "claim": "source-venue (Binance) screen only; no Bitget execution claim; test size control not validated",
            "transfer_to_bitget": "transfer_pending", "rules_skipped_data_gate": skipped,
            "rules": out}, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path, nargs="?", help="Bitget recorder dir (transfer stage)")
    ap.add_argument("--binance-metrics", type=Path, help="Binance history stage: metrics zip dir")
    ap.add_argument("--binance-klines", type=Path, help="Binance history stage: 5m kline zip dir")
    ap.add_argument("--binance-funding", type=Path, help="v1.2: fundingRate zip dir (monthly)")
    ap.add_argument("--symbol", default="BTCUSDT")
    args = ap.parse_args(argv)
    signal.alarm(MAX_RUNTIME)
    if args.binance_metrics:
        result, code = run_binance(args.binance_metrics, args.binance_klines, args.symbol, args.binance_funding)
    elif args.root:
        result, code = run(args.root)
    else:
        ap.error("give a recorder dir or --binance-metrics")
    print(json.dumps(result, indent=1, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
