"""Pre-registered sentiment-v1 rules, discovery/confirmation selection and gates (pure, no network).

Protocol: research/results/sentiment-protocol-2026-11-05.json. Descriptive only: the day-block
sign-flip test is NOT validated (v1-v3 failed size control under serial dependence). No efficacy
claim, no trading advice.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import signal
import sys
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
}
assert len(RULES) <= 6
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
    except (KeyError, TypeError):
        return False
    raise ValueError("unknown rule " + rule)


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
        table.append(f)
    return table


def events(rule, level, table, closes, lo_bar, hi_bar):
    """Non-overlapping events with signal bar in [lo_bar, hi_bar); returns [(bar, gross_return)]."""
    side = RULES[rule]["side"]
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
        out.append((b, side * (exit_ / entry - 1)))
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


def confirm_once(frozen, table, closes, conf, ledger):
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
        blocks.setdefault(b // (DAY_MS // BAR_MS), []).append(g * 1e4 - PRIMARY_COST_BP)
    means = [sum(v) / len(v) for _, v in sorted(blocks.items())]
    out["day_blocks"] = len(means)
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    args = ap.parse_args(argv)
    signal.alarm(MAX_RUNTIME)
    result, code = run(args.root)
    print(json.dumps(result, indent=1, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
