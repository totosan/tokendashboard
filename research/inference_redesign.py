"""Candidate synthetic Gaussian oracle calibration; never a market-data test."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import signal
import sys
import time
from pathlib import Path


ROOT = Path(__file__).parent
PROTOCOL_PATH = ROOT / "results/inference-redesign-protocol.json"
OUTPUT_PATH = ROOT / "results/inference-redesign.json"
SOURCES = (
    ROOT / "inference_calibration.py",
    ROOT / "results/inference-calibration.json",
    ROOT / "results/walkforward-protocol.json",
)
CONFIG = {
    "seed": 2026110224,
    "days": 28,
    "hypotheses": 132,
    "replicates_per_scenario": 600,
    "maximum_total_replicates": 2400,
    "alpha": 0.05,
    "confidence_z": 1.959963984540054,
    "minimum_independent_family_replicates": 2000,
    "maximum_family_wilson_width": 0.02,
    "upper_type_i_tolerance": 0.075,
    "runtime_budget_seconds": 90,
    "maximum_artifact_bytes": 8 * 1024 * 1024,
    "working_panel_element_limit": 2 * 28 * 132,
}
SCENARIOS = (
    "iid_day_null", "shared_crossarm_factor", "ar1_day_null", "sparse_empty_days",
)


def source_hashes():
    return {
        str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SOURCES
    }


def prospective_protocol():
    frozen = json.loads(SOURCES[2].read_text())
    family = [
        f"{arm}|{timeframe}|{group}|{side}"
        for arm in frozen["fixed_arm_family"]["arms"]
        for timeframe in frozen["frozen_inputs"]["timeframes"]
        for group in frozen["frozen_inputs"]["groups"]
        for side in ("long", "short")
    ]
    if len(family) != 132 or frozen["dependence_and_multiplicity"]["primary_hypothesis_count"] != 132:
        raise ValueError("REFUSE: expected the complete v2 11 x 2 x 3 x 2 family")
    return {
        "protocol_id": "issue-24-candidate-known-covariance-gaussian-oracle-v1",
        "status": "PROSPECTIVE_CANDIDATE_BEFORE_THIS_SIMULATION_NOT_RETROSPECTIVE",
        "frozen_walkforward_protocol_id": frozen["protocol_id"],
        "does_not_amend_frozen_future_protocol": True,
        "source_sha256": source_hashes(),
        "config": CONFIG,
        "family": family,
        "scenario_order": list(SCENARIOS),
        "scenario_seeds": {
            name: CONFIG["seed"] + (index + 1) * 100003
            for index, name in enumerate(SCENARIOS)
        },
        "single_design": {
            "null": "All 132 event means are zero in the specified synthetic Gaussian factor model, conditional on the exogenous event counts/activity mask.",
            "statistic": "Z_j = sum_d daily_sum[d,j] / sqrt(V_j); equivalently the event-weighted mean divided by its KNOWN conditional standard deviation.",
            "p_value": "One-sided analytic Gaussian survival probability erfc(Z/sqrt(2))/2. No bootstrap, signs, fitted covariance, or simulation-ranked p-values.",
            "known_variance": "V_j = a^2 c_j' K_global c_j + b^2 c_j' K_arm c_j + noise^2 sum(c_j). K=I for independent dates. For zero-initialized AR1, K[t,u]=rho^abs(t-u)*(1-rho^(2*(min(t,u)+1))), with zero-based dates.",
            "cross_cell_dependence": "One shared global Gaussian trajectory and eleven arm trajectories, with independent Gaussian noise per event. Whole panels are generated together; no independent simulation of individual hypothesis tests. Holm needs marginal superuniformity, not independent cells.",
            "assumptions": [
                "Gaussian zero-mean factors and event errors with exactly known model loadings, innovation variances, AR coefficients and initialization.",
                "Activity masks and counts are independent of all Gaussian outcomes; condition on them when computing variance.",
                "IID scenarios have independent UTC-day vectors. AR1 is NOT day independent and is calibrated only with its known temporal covariance.",
                "No market validity from Gaussianity, estimated covariance, marginal symmetry, or independent-day sign flips is asserted.",
            ],
            "empty_days": "Retain all 28 calendar rows. Count zero requires sum zero. A completely empty cell has no statistic/p-value, not Z=0; refuse the entire fixed Holm family without dropping cells.",
            "finite_resolution": {
                "simulation_p_values": False,
                "simulation_draws": 0,
                "analytic_numerical_floor": sys.float_info.min,
                "first_holm_threshold": CONFIG["alpha"] / 132,
                "if_simulation_p_values_were_used": "At least 2640 random draws would be required for 1/(B+1)<=0.05/132; they are not used in this design.",
            },
        },
        "preserved_scenarios": {
            "iid_day_null": "a=.55, b=.35, noise=.75; independent Gaussian days.",
            "shared_crossarm_factor": "a=.90, b=.20, noise=.25; independent days, strong global dependence.",
            "ar1_day_null": "a=.55, b=.35, noise=.75; global rho=.65, arm rho=.45, both initialized at zero before first innovation, as in old generator.",
            "sparse_empty_days": "a=.65, b=.25, noise=.70; independent days; shared date activity .35 and conditional cell activity .55. Empty families are possible and must be refused.",
            "counts": "Each active cell/date has 1+Bernoulli(.35)+Bernoulli(.10) events; Gaussian factors shared by events on a day; independent event noise.",
        },
        "failure_hypothesis_and_change": [
            "The original saved result remains FAIL: marginal medians .1083/.0917/.1167/.1604 and 14 sparse invalid families. This redesign does not explain that failure away.",
            "Old bootstrap compares an observed event ratio to ratios from sample-mean-centered overlapping nonwrapping blocks. This is not a finite-sample pivotal/exchangeable null distribution. Estimated centering, random denominators, edge weights and effective block count (~28/5) can distort tails even under iid dates.",
            "Five-day moving-block consistency requires suitable weak dependence/mixing, increasing block length with block length / sample size tending to zero, sufficient moments, and stable denominators. Twenty-eight dates with block length five gives no exact guarantee; AR1 dependence crosses block boundaries.",
            "Assigning zero to an empty bootstrap ratio invents a statistic; missing original cells cannot become evidence. B=199 has floor .005, above .0003788, so zero Holm rejections were structurally uninformative.",
            "Change to one exact synthetic Gaussian oracle, NOT a practical replacement estimator. Known covariance removes centering/bootstrap mismatch and is a mathematical reference benchmark only.",
        ],
        "predeclared_mismatch_diagnostic": "For AR1 only, also compute the same oracle formula with deliberately false K=I. Report INCONCLUSIVE_ASSUMPTIONS_VIOLATED regardless of its observed rates; FAIL if any marginal Wilson lower bound exceeds .075. Never select between methods using results.",
        "monte_carlo_and_gate": {
            "unit": "One independently generated whole 132-cell panel per replicate; 132 correlated cells never multiply Monte Carlo N. Marginal Wilson intervals use each cell's available independent replicate count.",
            "missing": "Any incomplete family is REFUSED. If any replicate is refused, no unconditional FWER estimate/interval or PASS; do not silently condition FWER on complete families.",
            "intervals": "Two-sided 95% Wilson per cell and per complete-family any-rejection indicator. Per-cell intervals are pointwise, not simultaneous; no pooled-cell binomial interval.",
            "fail": "Any marginal lower Wilson bound > .075 or complete-family lower bound > .075 gives FAIL. Intervals describe simulation uncertainty, not market uncertainty.",
            "pass": "Only if no refusals, every upper Wilson bound <=.075, >=2000 independent families, family interval width<=.02, and assumptions apply. Otherwise INCONCLUSIVE.",
            "budget_power": "600 planned families/scenario <2000 required; family Monte Carlo precision is intentionally insufficient for PASS, even with zero rejections. Resolution of analytic p-values is not Monte Carlo calibration power.",
            "overall": "FAIL if any in-scope scenario fails; otherwise INCONCLUSIVE unless every scenario passes. Mismatch diagnostic cannot validate the oracle or markets.",
        },
        "execution": {
            "commands": [
                "timeout 30s python -B -m research.inference_redesign --write-protocol",
                "timeout 120s python -B -m unittest research.test_inference_redesign",
                "timeout 120s python -B -m research.inference_redesign --run",
            ],
            "budget_failure": "Check monotonic deadline each replicate. On deadline, SIGTERM, or exception, persist partial honest RUNTIME_OR_EXECUTION_FAILURE with nonzero exit; no tuning/retry selection.",
            "allocation": "No stored replicate panels, covariance matrices, resample matrices, or massive loops. <=2400 panels, each two 28x132 lists, plus O(132) counters; variance uses O(days) AR recurrence. Serialized protocol/result each <=8 MiB.",
            "scope": "Synthetic only; no data acquisition, reserved observations, returns/profitability claims, production integration, or changes to old results/frozen future protocol. Walkforward NOT_READY/NOT_RUN.",
        },
    }


def validate_panel(sums, counts):
    if not sums or len(sums) != len(counts):
        raise ValueError("nonempty aligned calendars required")
    cells = len(sums[0])
    if not cells or any(len(row) != cells for row in sums + counts):
        raise ValueError("rectangular aligned panels required")
    for row, count_row in zip(sums, counts):
        for value, count in zip(row, count_row):
            if not isinstance(count, int) or count < 0 or not math.isfinite(value):
                raise ValueError("finite sums and nonnegative integer counts required")
            if count == 0 and value != 0:
                raise ValueError("empty dates must have zero sum")


def ar_quadratic(counts, rho):
    """c' K c in linear time, with the old generator's zero initialization."""
    if not 0 <= rho < 1:
        raise ValueError("rho must be in [0,1)")
    lag_sum = total = initial_projection = 0.0
    power = rho
    for count in counts:
        total += count * count + 2 * count * lag_sum
        initial_projection += count * power
        lag_sum = rho * (lag_sum + count)
        power *= rho
    return max(0.0, total - initial_projection * initial_projection)


def parameters(scenario):
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    if scenario == "shared_crossarm_factor":
        return .90, .20, .25, 0.0, 0.0
    if scenario == "sparse_empty_days":
        return .65, .25, .70, 0.0, 0.0
    return .55, .35, .75, .65 if scenario == "ar1_day_null" else 0.0, .45 if scenario == "ar1_day_null" else 0.0


def normal_survival(z):
    if not math.isfinite(z):
        raise ValueError("finite Z required")
    return max(sys.float_info.min, .5 * math.erfc(z / math.sqrt(2)))


def oracle_pvalues(sums, counts, scenario, *, false_independent_days=False):
    validate_panel(sums, counts)
    a, b, noise, global_rho, arm_rho = parameters(scenario)
    if false_independent_days:
        global_rho = arm_rho = 0.0
    result = []
    for cell in range(len(sums[0])):
        c = [row[cell] for row in counts]
        if not sum(c):
            result.append(None)
            continue
        variance = (
            a * a * ar_quadratic(c, global_rho)
            + b * b * ar_quadratic(c, arm_rho)
            + noise * noise * sum(c)
        )
        result.append(normal_survival(sum(row[cell] for row in sums) / math.sqrt(variance)))
    return result


def holm(pvalues, expected_size=132, alpha=.05):
    if len(pvalues) != expected_size or len(pvalues) == 0 or any(
        p is None or not math.isfinite(p) or not 0 <= p <= 1 for p in pvalues
    ):
        return {"status": "REFUSE_MISSING_OR_INVALID_FAMILY", "rejected": None}
    rejected = [False] * expected_size
    for rank, (cell, p) in enumerate(sorted(enumerate(pvalues), key=lambda x: (x[1], x[0]))):
        if p > alpha / (expected_size - rank):
            break
        rejected[cell] = True
    return {"status": "COMPLETE_FAMILY", "rejected": rejected}


def wilson(successes, trials):
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("positive independent binomial trial count required")
    z = CONFIG["confidence_z"]
    rate = successes / trials
    denominator = 1 + z * z / trials
    center = (rate + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / trials + z * z / (4 * trials * trials)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def synthetic_panel(rng, scenario, days=28, cells=132):
    if cells != 132:
        raise ValueError("do not shrink the 11-arm family")
    a, b, noise, global_rho, arm_rho = parameters(scenario)

    def trajectory(rho):
        previous = 0.0
        values = []
        for _ in range(days):
            previous = rho * previous + math.sqrt(1 - rho * rho) * rng.gauss(0, 1)
            values.append(previous)
        return values

    common = trajectory(global_rho)
    arms = [trajectory(arm_rho) for _ in range(11)]
    sums = [[0.0] * cells for _ in range(days)]
    counts = [[0] * cells for _ in range(days)]
    active = (
        {d for d in range(days) if rng.random() < .35}
        if scenario == "sparse_empty_days" else set(range(days))
    )
    for day in range(days):
        for cell in range(cells):
            if scenario == "sparse_empty_days" and (day not in active or rng.random() >= .55):
                continue
            count = 1 + int(rng.random() < .35) + int(rng.random() < .10)
            counts[day][cell] = count
            sums[day][cell] = sum(
                a * common[day] + b * arms[cell // 12][day] + noise * rng.gauss(0, 1)
                for _ in range(count)
            )
    return sums, counts


class Tally:
    def __init__(self):
        self.trials = [0] * 132
        self.rejections = [0] * 132
        self.attempted = self.refused = self.family_rejections = 0

    def add(self, pvalues):
        self.attempted += 1
        for cell, p in enumerate(pvalues):
            if p is not None:
                self.trials[cell] += 1
                self.rejections[cell] += p <= CONFIG["alpha"]
        family = holm(pvalues)
        if family["rejected"] is None:
            self.refused += 1
        else:
            self.family_rejections += any(family["rejected"])

    def report(self):
        marginal = [
            {
                "cell_index": cell, "independent_replicates": n,
                "rejections": k, "rate": k / n if n else None,
                "wilson_95": wilson(k, n) if n else None,
            }
            for cell, (k, n) in enumerate(zip(self.rejections, self.trials))
        ]
        family_n = self.attempted - self.refused
        interval = wilson(self.family_rejections, family_n) if family_n and not self.refused else None
        return {
            "attempted_independent_panels": self.attempted,
            "marginal_type_i": marginal,
            "marginal_scope": "Available-cell diagnostics conditional on nonempty cells; pointwise intervals, never pooled across correlated cells.",
            "holm_132": {
                "status": "REFUSE_MISSING_FAMILIES" if self.refused else "COMPLETE_FAMILIES",
                "refused_families": self.refused,
                "complete_independent_families": family_n,
                "rejections_in_complete_families_diagnostic_only": self.family_rejections,
                "unconditional_rate": self.family_rejections / family_n if interval else None,
                "wilson_95": interval,
                "required_minimum_independent_families": CONFIG["minimum_independent_family_replicates"],
                "monte_carlo_precision_sufficient": bool(
                    interval and family_n >= CONFIG["minimum_independent_family_replicates"]
                    and interval[1] - interval[0] <= CONFIG["maximum_family_wilson_width"]
                ),
            },
        }


def gate(report, assumptions_apply=True):
    intervals = [cell["wilson_95"] for cell in report["marginal_type_i"]]
    family = report["holm_132"]
    family_interval = family["wilson_95"]
    if any(ci and ci[0] > CONFIG["upper_type_i_tolerance"] for ci in intervals) or (
        family_interval and family_interval[0] > CONFIG["upper_type_i_tolerance"]
    ):
        return "FAIL"
    if not assumptions_apply:
        return "INCONCLUSIVE_ASSUMPTIONS_VIOLATED"
    if (
        family["refused_families"] or not family["monte_carlo_precision_sufficient"]
        or any(ci is None or ci[1] > CONFIG["upper_type_i_tolerance"] for ci in intervals)
        or not family_interval or family_interval[1] > CONFIG["upper_type_i_tolerance"]
    ):
        return "INCONCLUSIVE"
    return "PASS_SYNTHETIC_ORACLE_ONLY"


def check_deadline(start):
    if time.monotonic() - start >= CONFIG["runtime_budget_seconds"]:
        raise TimeoutError("predeclared runtime budget exceeded")


def save(path, artifact):
    serialized = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    if len(serialized.encode()) > CONFIG["maximum_artifact_bytes"]:
        raise RuntimeError("predeclared serialized byte budget exceeded")
    path.write_text(serialized)


def run():
    start = time.monotonic()
    artifact = {
        "artifact_status": "RUNNING",
        "calibration_gate": "NOT_RUN",
        "scope": "Candidate synthetic known-covariance Gaussian oracle only; no practical market inference authorized.",
        "actual_market_data_used": False,
        "future_data_fetched": False,
        "walkforward_readiness": "NOT_READY",
        "reserved_validation": "NOT_RUN",
        "frozen_future_protocol_amended": False,
        "results": {},
        "protocol_sha256": None,
    }
    active_tally = None
    active_name = None
    old_handler = None
    try:
        protocol = json.loads(PROTOCOL_PATH.read_text())
        if protocol != prospective_protocol():
            raise ValueError("REFUSE: prospective protocol/source hashes differ; do not rewrite after simulation")
        artifact["protocol_sha256"] = hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()
        save(OUTPUT_PATH, artifact)

        def terminate(signum, frame):
            raise TimeoutError(f"interrupted by signal {signum}")

        old_handler = signal.signal(signal.SIGTERM, terminate)
        for scenario in SCENARIOS:
            active_name = scenario
            active_tally = Tally()
            mismatch = Tally() if scenario == "ar1_day_null" else None
            rng = random.Random(protocol["scenario_seeds"][scenario])
            for _ in range(CONFIG["replicates_per_scenario"]):
                check_deadline(start)
                sums, counts = synthetic_panel(rng, scenario)
                active_tally.add(oracle_pvalues(sums, counts, scenario))
                if mismatch is not None:
                    mismatch.add(oracle_pvalues(sums, counts, scenario, false_independent_days=True))
            report = active_tally.report()
            report["status"] = gate(report)
            artifact["results"][scenario] = report
            if mismatch is not None:
                diagnostic = mismatch.report()
                diagnostic["status"] = gate(diagnostic, assumptions_apply=False)
                diagnostic["assumptions_apply"] = False
                diagnostic["interpretation"] = "Deliberately wrong independent-day covariance on AR1; never market-valid or a selectable alternative."
                artifact["ar1_false_independence_diagnostic"] = diagnostic
            save(OUTPUT_PATH, artifact)
        check_deadline(start)
        statuses = [value["status"] for value in artifact["results"].values()]
        artifact["calibration_gate"] = (
            "FAIL" if "FAIL" in statuses
            else "PASS_SYNTHETIC_ORACLE_ONLY" if all(s == "PASS_SYNTHETIC_ORACLE_ONLY" for s in statuses)
            else "INCONCLUSIVE"
        )
        artifact["artifact_status"] = "COMPLETE_SYNTHETIC_ONLY"
        artifact["decision_reason"] = (
            "Fixed 600 independent panels/scenario cannot meet >=2000 family calibration requirement; "
            "missing sparse families are refused. Analytic p-value resolution alone is not sufficient. "
            "Known-covariance oracle assumptions are not established for market data."
        )
        code = 0
    except Exception as exc:
        artifact["artifact_status"] = "RUNTIME_OR_EXECUTION_FAILURE"
        artifact["calibration_gate"] = "INCONCLUSIVE"
        artifact["error"] = f"{type(exc).__name__}: {exc}"
        if active_tally is not None:
            artifact["partial_scenario"] = {"name": active_name, "report": active_tally.report()}
        code = 1
    finally:
        if old_handler is not None:
            signal.signal(signal.SIGTERM, old_handler)
    artifact["runtime_seconds"] = round(time.monotonic() - start, 6)
    try:
        save(OUTPUT_PATH, artifact)
    except Exception as exc:
        OUTPUT_PATH.write_text(json.dumps({
            "artifact_status": "RUNTIME_OR_EXECUTION_FAILURE",
            "calibration_gate": "INCONCLUSIVE",
            "error": str(exc),
            "walkforward_readiness": "NOT_READY", "reserved_validation": "NOT_RUN",
        }, indent=2) + "\n")
        code = 1
    print(json.dumps({
        "output": str(OUTPUT_PATH), "status": artifact["calibration_gate"],
        "artifact_status": artifact["artifact_status"], "runtime_seconds": artifact["runtime_seconds"],
    }))
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-protocol", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.write_protocol:
        if PROTOCOL_PATH.exists():
            raise FileExistsError("REFUSE: never overwrite prospective candidate protocol")
        save(PROTOCOL_PATH, prospective_protocol())
        print(PROTOCOL_PATH)
        return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
