"""Synthetic calibration of an unknown-covariance, calendar-day HAC candidate."""

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
WALKFORWARD_PATH = ROOT / "results/walkforward-protocol.json"
PROTOCOL_PATH = ROOT / "results/practical-inference-protocol-2026-11-04.json"
OUTPUT_PATH = ROOT / "results/practical-inference-calibration-2026-11-04.json"
FAMILY_SIZE = 132
ALPHA = 0.05
LAG = 4
MIN_EVENTS = 30
MIN_ACTIVE_DAYS = 10
SCENARIOS = (
    "iid_heteroskedastic",
    "serial_heteroskedastic",
    "shared_cross_cell_heteroskedastic",
    "sparse_and_empty_cells",
)
CONFIG = {
    "seed": 202611041323,
    "days_per_panel": 28,
    "hypotheses": 132,
    "replicates_per_scenario": 1000,
    "required_independent_panels_per_scenario": 2000,
    "maximum_total_replicates": 4000,
    "alpha": ALPHA,
    "confidence_level": 0.95,
    "confidence_z": 1.959963984540054,
    "maximum_runtime_seconds": 90,
    "maximum_artifact_bytes": 8 * 1024 * 1024,
    "maximum_panel_elements": 2 * 28 * 132,
    "hac_bartlett_max_lag_days": LAG,
    "minimum_events_per_cell": MIN_EVENTS,
    "minimum_nonempty_days_per_cell": MIN_ACTIVE_DAYS,
    "event_counts": "On an active cell-day, 2 + Bernoulli(0.5) events; counts are independent of outcomes.",
    "tail": "One-sided upper-tail Student t reference with 27 degrees of freedom; finite analytic values are not Monte Carlo-ranked.",
}


def _family_from_frozen_protocol():
    frozen = json.loads(WALKFORWARD_PATH.read_text())
    family = [
        f"{arm}|{timeframe}|{group}|{side}"
        for arm in frozen["fixed_arm_family"]["arms"]
        for timeframe in frozen["frozen_inputs"]["timeframes"]
        for group in frozen["frozen_inputs"]["groups"]
        for side in ("long", "short")
    ]
    if len(family) != FAMILY_SIZE or len(set(family)) != FAMILY_SIZE:
        raise ValueError("REFUSE: frozen walk-forward family must contain all 132 hypotheses")
    if frozen["dependence_and_multiplicity"]["primary_hypothesis_count"] != FAMILY_SIZE:
        raise ValueError("REFUSE: source protocol family count differs from 132")
    return frozen, family


def source_hashes():
    return {
        "research/results/walkforward-protocol.json": hashlib.sha256(
            WALKFORWARD_PATH.read_bytes()
        ).hexdigest(),
        "research/inference_calibration.py": hashlib.sha256(
            (ROOT / "inference_calibration.py").read_bytes()
        ).hexdigest(),
        "research/results/inference-calibration.json": hashlib.sha256(
            (ROOT / "results/inference-calibration.json").read_bytes()
        ).hexdigest(),
        "research/inference_redesign.py": hashlib.sha256(
            (ROOT / "inference_redesign.py").read_bytes()
        ).hexdigest(),
        "research/results/inference-redesign-protocol.json": hashlib.sha256(
            (ROOT / "results/inference-redesign-protocol.json").read_bytes()
        ).hexdigest(),
        "research/results/inference-redesign.json": hashlib.sha256(
            (ROOT / "results/inference-redesign.json").read_bytes()
        ).hexdigest(),
    }


def prospective_protocol():
    frozen, family = _family_from_frozen_protocol()
    return {
        "protocol_id": "issue-22-practical-inference-candidate-v1",
        "status": "FROZEN_BEFORE_SYNTHETIC_DIAGNOSTIC_NOT_MARKET_VALIDATION",
        "created_at_utc": "2026-11-04",
        "source_sha256": source_hashes(),
        "frozen_walkforward_protocol_id": frozen["protocol_id"],
        "does_not_amend_walkforward_protocol": True,
        "future_folds": frozen["reserved_forward_folds"]["folds"],
        "family": family,
        "config": CONFIG,
        "design": {
            "estimand": "For each fixed cell, the event-weighted mean theta = sum_d S[d]/sum_d C[d], under the one-sided null theta <= 0.",
            "daily_panel": "Exactly 28 UTC calendar rows and 132 fixed hypothesis columns. S is the sum of event outcomes for a cell-day; C is its event count. Empty days have S=0,C=0 and remain in the calendar.",
            "statistic": "For each cell, form X[d]=S[d]-theta_hat*C[d]. Estimate long-run variance of sum_d X[d] by Bartlett HAC: gamma0 + 2*sum_{l=1..4}(1-l/5)*gamma_l, with gamma_l=sum_{d=l..27}X[d]*X[d-l]. Studentize theta_hat by sqrt(HAC)/sum C.",
            "small_sample_reference": "One-sided Student-t tail with df=27. The reference distribution is an asymptotic small-sample approximation, not an exact result for a 28-day dependent panel.",
            "unknown_dependence_estimator": "A fixed, no-tuning Newey-West/Bartlett lag-4 long-run variance estimator on calendar-day influence values. It allows arbitrary within-day covariance and estimates serial covariance only through four lags.",
            "null_and_calibration_target": "All 132 event-weighted cell means are zero in synthetic null panels. Assess marginal size at .05 and complete-family Holm FWER across independently generated whole panels.",
            "multiplicity": "Holm step-down at alpha .05 over exactly all 132 finite cell p-values. If any hypothesis is invalid, the entire family is refused; no dropping invalid cells or changing family size.",
            "explicit_assumptions": [
                "The daily influence process is approximately stationary over the fold, has finite fourth moments and summable weak dependence.",
                "The Bartlett lag-4 truncation captures enough dependence for the HAC standard error; dependence beyond four days is not modeled.",
                "The Student-t approximation is adequate with only 28 calendar days; this is a strong, unverified small-sample assumption.",
                "Event counts and missingness are exogenous to outcomes, or inference is interpreted conditional on the realized counts/mask. Outcome-dependent event activity is not covered.",
                "The synthetic calibration generators span the relevant failure modes. Finite calibration cannot establish these assumptions for real market outcomes.",
                "Holm controls FWER under arbitrary cross-hypothesis dependence only when each marginal p-value is super-uniform. The proposed HAC/t p-values have no finite-sample super-uniformity guarantee."
            ],
            "why_not_authorized": "This candidate is an auditable practical estimator, not an oracle replacement or proven valid inference method. It can only be considered further if the preregistered calibration passes; empirical failure, insufficient precision, or unmet assumptions leaves criterion 4 unsatisfied.",
        },
        "missing_and_sparse_rules": {
            "invalid_input": "Refuse a cell/family for nonfinite sums, noninteger/negative counts, nonzero sum with zero count, nonrectangular panels, or calendar length other than 28.",
            "cell_eligibility": f"Require at least {MIN_EVENTS} observed events and at least {MIN_ACTIVE_DAYS} nonempty UTC dates for each hypothesis.",
            "empty_hypothesis": "A zero-event cell has no statistic and no p-value. Any such cell refuses the complete 132-family Holm test.",
            "partial_results": "Marginal rates may be reported only as explicitly conditional available-cell diagnostics with valid-replicate denominators. If any replicate refuses any family cell, no unconditional FWER estimate or interval is reported for that scenario.",
        },
        "p_value_resolution": {
            "family_first_holm_threshold": ALPHA / FAMILY_SIZE,
            "student_t_analytic_floor": sys.float_info.min,
            "simulation_based_pvalues": False,
            "minimum_random_draws_if_ranked_pvalues_used": 2639,
            "resolution_note": "The deterministic Student-t CDF can numerically resolve the first Holm threshold; this says nothing about Monte Carlo calibration precision.",
        },
        "synthetic_cases": [
            {
                "name": "iid_heteroskedastic",
                "null": "Independent Gaussian event errors with per-day shared lognormal volatility; varying event counts and zero-activity days.",
                "role": "Independent-day heteroskedastic marginal-size and Holm baseline.",
            },
            {
                "name": "serial_heteroskedastic",
                "null": "Zero-mean AR(1) common and arm factors (rho=.65/.45) plus event noise, with time-varying volatility and counts.",
                "role": "Short-range serial dependence plus heteroskedasticity.",
            },
            {
                "name": "shared_cross_cell_heteroskedastic",
                "null": "Strong shared global and arm Gaussian factors, day-varying volatility and event noise; full 132-cell panels generated together.",
                "role": "Cross-cell dependence, heteroskedasticity and dependence-aware whole-family Holm calibration.",
            },
            {
                "name": "sparse_and_empty_cells",
                "null": "Sparse day/cell event masks with at least some cells forced to have no events in a replicate; outcomes remain zero-mean and heteroskedastic.",
                "role": "Evaluate sparse conditional marginals and fail-closed invalid complete-family behavior; unconditional FWER is not estimable when any replicate is refused.",
            },
        ],
        "calibration_rules": {
            "replication_unit": "One complete independently generated 28x132 daily sum/count panel per replicate; correlated hypotheses do not increase Monte Carlo sample size.",
            "monte_carlo_intervals": "Two-sided 95% Wilson intervals for each marginal available-cell Bernoulli rejection rate and for complete-family any-rejection rate. Marginal intervals are pointwise, not simultaneous.",
            "marginal_failure": "FAIL if any marginal Wilson lower bound exceeds .075; otherwise report all rates and intervals as synthetic diagnostics.",
            "family_failure": "FAIL if complete-family FWER Wilson lower bound exceeds .075; no FWER estimate/interval if any panel was incomplete.",
            "pass": "Only if every scenario has zero refused families, at least 2000 independent panels, all marginal and family Wilson upper bounds <=.075, and all declared assumptions are defensible. Otherwise INCONCLUSIVE; passing synthetic calibration would not itself validate markets.",
            "precision": "2000 independent panels/scenario is the minimum predeclared FWER precision floor. Planned 1000/scenario is deliberately below this floor; a PASS is impossible under this single bounded run.",
            "power_non_vacuity": "No positive-effect power run is planned: under 28 days, sparse cells, a four-lag HAC variance and the extreme first Holm threshold, null size calibration is the necessary gate, not evidence of useful discovery power. This diagnostic cannot establish that the method has adequate power; no efficacy claim is allowed.",
            "runtime_failure": "A 90-second internal monotonic deadline, SIGTERM, exception or artifact >8 MiB saves RUNTIME_OR_EXECUTION_FAILURE with partial diagnostics and nonzero status. Do not retry, tune, change seeds, or increase/decrease replicates after seeing results.",
            "overall": "FAIL if any marginal or estimable family lower bound exceeds .075; otherwise INCONCLUSIVE if any family is refused, precision floor is unmet, any upper bound exceeds .075, runtime fails, or assumptions are not validated. No post hoc relaxation.",
        },
        "execution": {
            "commands": [
                "timeout --signal=TERM --kill-after=5s 120s python -B -m unittest research.test_practical_inference -v",
                "timeout --signal=TERM --kill-after=5s 120s python -B -m research.practical_inference --run",
            ],
            "simulation_runs": 1,
            "no_market_data": True,
            "no_production_integration": True,
            "no_future_data": True,
            "no_existing_result_or_walkforward_protocol_changes": True,
        },
    }


def write_json(path, value):
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if len(text.encode("utf-8")) > CONFIG["maximum_artifact_bytes"]:
        raise RuntimeError("artifact exceeds the predeclared 8 MiB limit")
    path.write_text(text)


def validate_panel(sums, counts):
    if len(sums) != CONFIG["days_per_panel"] or len(counts) != len(sums):
        raise ValueError("exactly 28 aligned calendar rows required")
    if any(not isinstance(row, (list, tuple)) for row in sums + counts):
        raise ValueError("panel rows must be sequences")
    if any(len(row) != FAMILY_SIZE for row in sums + counts):
        raise ValueError("exactly 132 family columns required")
    for sum_row, count_row in zip(sums, counts):
        for value, count in zip(sum_row, count_row):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("daily sums must be finite")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("counts must be nonnegative integers")
            if count == 0 and value != 0:
                raise ValueError("zero-count dates must have zero sum")


def _betacf(a, b, x):
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1.0 - qab * x / qap
    d = 1e-300 if abs(d) < 1e-300 else d
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1e-300 if abs(d) < 1e-300 else d
        c = 1 + aa / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1e-300 if abs(d) < 1e-300 else d
        c = 1 + aa / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 3e-14:
            break
    return h


def _regularized_beta(x, a, b):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    factor = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1) / (a + b + 2):
        return factor * _betacf(a, b, x) / a
    return 1 - factor * _betacf(b, a, 1 - x) / b


def student_t_survival(t_value, degrees=27):
    if not math.isfinite(t_value) or degrees <= 0:
        raise ValueError("finite statistic and positive degrees of freedom required")
    if t_value == 0:
        return 0.5
    if t_value <= 0:
        return max(sys.float_info.min, 1 - student_t_survival(-t_value, degrees))
    x = degrees / (degrees + t_value * t_value)
    return max(sys.float_info.min, 0.5 * _regularized_beta(x, degrees / 2, 0.5))


def cell_pvalues(sums, counts):
    validate_panel(sums, counts)
    result = []
    for cell in range(FAMILY_SIZE):
        cell_counts = [counts[day][cell] for day in range(len(counts))]
        total_count = sum(cell_counts)
        active_days = sum(value > 0 for value in cell_counts)
        if total_count < MIN_EVENTS or active_days < MIN_ACTIVE_DAYS:
            result.append(None)
            continue
        estimate = sum(sums[day][cell] for day in range(len(sums))) / total_count
        influence = [
            sums[day][cell] - estimate * cell_counts[day]
            for day in range(len(sums))
        ]
        long_run_variance = sum(value * value for value in influence)
        for lag in range(1, LAG + 1):
            covariance = sum(
                influence[day] * influence[day - lag]
                for day in range(lag, len(influence))
            )
            long_run_variance += 2 * (1 - lag / (LAG + 1)) * covariance
        if not math.isfinite(long_run_variance) or long_run_variance <= 0:
            result.append(None)
            continue
        standard_error = math.sqrt(long_run_variance) / total_count
        statistic = estimate / standard_error
        result.append(student_t_survival(statistic))
    return result


def holm(pvalues, alpha=ALPHA):
    if len(pvalues) != FAMILY_SIZE or any(
        value is None or not isinstance(value, (int, float))
        or not math.isfinite(value) or not 0 <= value <= 1
        for value in pvalues
    ):
        return {"status": "REFUSED_INCOMPLETE_132_FAMILY", "rejected": None}
    ordered = sorted(enumerate(pvalues), key=lambda item: (item[1], item[0]))
    rejected = [False] * FAMILY_SIZE
    for rank, (cell, value) in enumerate(ordered):
        if value > alpha / (FAMILY_SIZE - rank):
            break
        rejected[cell] = True
    return {"status": "COMPLETE_132_FAMILY", "rejected": rejected}


def wilson(successes, trials):
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("positive binomial trial count and valid successes required")
    z = CONFIG["confidence_z"]
    rate = successes / trials
    den = 1 + z * z / trials
    center = (rate + z * z / (2 * trials)) / den
    half = z * math.sqrt(rate * (1 - rate) / trials + z * z / (4 * trials * trials)) / den
    return [max(0.0, center - half), min(1.0, center + half)]


def _ar1(rng, days, rho):
    previous = 0.0
    values = []
    for _ in range(days):
        previous = rho * previous + math.sqrt(1 - rho * rho) * rng.gauss(0, 1)
        values.append(previous)
    return values


def synthetic_panel(rng, scenario):
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    days = CONFIG["days_per_panel"]
    sums = [[0.0] * FAMILY_SIZE for _ in range(days)]
    counts = [[0] * FAMILY_SIZE for _ in range(days)]
    volatility = [math.exp(0.35 * rng.gauss(0, 1) - 0.35 ** 2 / 2) for _ in range(days)]
    if scenario == "serial_heteroskedastic":
        common = _ar1(rng, days, 0.65)
        arms = [_ar1(rng, days, 0.45) for _ in range(11)]
        loadings = (0.55, 0.35, 0.75)
    elif scenario == "shared_cross_cell_heteroskedastic":
        common = [rng.gauss(0, 1) for _ in range(days)]
        arms = [[rng.gauss(0, 1) for _ in range(days)] for _ in range(11)]
        loadings = (0.90, 0.20, 0.45)
    else:
        common = [0.0] * days
        arms = [[0.0] * days for _ in range(11)]
        loadings = (0.0, 0.0, 1.0)
    active_days = (
        {day for day in range(days) if rng.random() < 0.72}
        if scenario == "sparse_and_empty_cells" else set(range(days))
    )
    empty_cells = set()
    if scenario == "sparse_and_empty_cells":
        empty_cells = set(rng.sample(range(FAMILY_SIZE), 2))
    for day in range(days):
        for cell in range(FAMILY_SIZE):
            if scenario == "sparse_and_empty_cells":
                if cell in empty_cells or day not in active_days or rng.random() >= 0.90:
                    continue
            count = 2 + int(rng.random() < 0.5)
            counts[day][cell] = count
            arm = cell // 12
            a, b, noise = loadings
            total = 0.0
            for _ in range(count):
                total += volatility[day] * (
                    a * common[day] + b * arms[arm][day] + noise * rng.gauss(0, 1)
                )
            sums[day][cell] = total
    return sums, counts


def _scenario_seed(name):
    index = SCENARIOS.index(name) + 1
    return CONFIG["seed"] + index * 100003


class Tally:
    def __init__(self):
        self.trials = [0] * FAMILY_SIZE
        self.rejections = [0] * FAMILY_SIZE
        self.attempted = 0
        self.refused = 0
        self.family_rejections = 0

    def add(self, pvalues):
        self.attempted += 1
        for cell, value in enumerate(pvalues):
            if value is not None:
                self.trials[cell] += 1
                self.rejections[cell] += value <= ALPHA
        family = holm(pvalues)
        if family["rejected"] is None:
            self.refused += 1
        else:
            self.family_rejections += any(family["rejected"])

    def report(self):
        marginal = []
        for cell, (trials, rejections) in enumerate(zip(self.trials, self.rejections)):
            marginal.append({
                "cell_index": cell,
                "independent_available_cell_panels": trials,
                "rejections": rejections,
                "rate_conditional_on_cell_valid": rejections / trials if trials else None,
                "wilson_95_pointwise": wilson(rejections, trials) if trials else None,
            })
        complete = self.attempted - self.refused
        family_interval = (
            wilson(self.family_rejections, complete)
            if complete and not self.refused else None
        )
        return {
            "independent_panels_attempted": self.attempted,
            "complete_132_family_panels": complete if not self.refused else None,
            "refused_family_panels": self.refused,
            "marginal_type_i_scope": "Conditional on each cell meeting its event/date floor; pointwise Wilson intervals, not a pooled-cell estimate.",
            "marginal_type_i_by_cell": marginal,
            "familywise_error_rate": (
                self.family_rejections / complete if family_interval is not None else None
            ),
            "familywise_wilson_95": family_interval,
            "familywise_status": (
                "NOT_ESTIMABLE_ANY_FAMILY_REFUSED" if self.refused else "ESTIMABLE"
            ),
            "first_holm_threshold": ALPHA / FAMILY_SIZE,
            "analytic_student_t_p_floor": sys.float_info.min,
        }


def _gate(report):
    intervals = [entry["wilson_95_pointwise"] for entry in report["marginal_type_i_by_cell"]]
    family_ci = report["familywise_wilson_95"]
    if any(ci and ci[0] > 0.075 for ci in intervals) or (family_ci and family_ci[0] > 0.075):
        return "FAIL"
    if (
        report["refused_family_panels"]
        or         report["independent_panels_attempted"] < CONFIG["required_independent_panels_per_scenario"]
        or any(ci is None or ci[1] > 0.075 for ci in intervals)
        or family_ci is None or family_ci[1] > 0.075
    ):
        return "INCONCLUSIVE"
    return "PASS_SYNTHETIC_ASSUMPTIONS_ONLY"


def _initial_artifact():
    protocol = json.loads(PROTOCOL_PATH.read_text())
    if protocol != prospective_protocol():
        raise ValueError("REFUSE: protocol or source hashes differ from frozen design")
    return {
        "artifact_status": "RUNNING",
        "calibration_gate": "NOT_RUN",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest(),
        "actual_market_data_used": False,
        "future_data_fetched": False,
        "reserved_validation_status": "NOT_READY_NOT_RUN",
        "results": {},
    }


def _failure_gate(artifact, active_name, active_tally):
    established = [
        result.get("status")
        for result in artifact.get("results", {}).values()
    ]
    if active_tally is not None:
        active_report = active_tally.report()
        active_report["status"] = _gate(active_report)
        artifact["partial_scenario"] = {"name": active_name, "report": active_report}
        established.append(active_report["status"])
    return "FAIL" if "FAIL" in established else "INCONCLUSIVE"


def run():
    started = time.monotonic()
    artifact = _initial_artifact()
    active_name = None
    active_tally = None
    previous_handler = None
    status_code = 0
    try:
        write_json(OUTPUT_PATH, artifact)

        def terminate(signum, frame):
            raise TimeoutError(f"interrupted by signal {signum}")

        previous_handler = signal.signal(signal.SIGTERM, terminate)
        for name in SCENARIOS:
            active_name = name
            active_tally = Tally()
            rng = random.Random(_scenario_seed(name))
            for _ in range(CONFIG["replicates_per_scenario"]):
                if time.monotonic() - started >= CONFIG["maximum_runtime_seconds"]:
                    raise TimeoutError("predeclared 90-second simulation budget exceeded")
                sums, counts = synthetic_panel(rng, name)
                active_tally.add(cell_pvalues(sums, counts))
            report = active_tally.report()
            report["status"] = _gate(report)
            artifact["results"][name] = report
            write_json(OUTPUT_PATH, artifact)
        statuses = [value["status"] for value in artifact["results"].values()]
        artifact["calibration_gate"] = (
            "FAIL" if "FAIL" in statuses
            else "PASS_SYNTHETIC_ASSUMPTIONS_ONLY" if all(
                value == "PASS_SYNTHETIC_ASSUMPTIONS_ONLY" for value in statuses
            )
            else "INCONCLUSIVE"
        )
        artifact["artifact_status"] = "COMPLETE_SYNTHETIC_ONLY"
        artifact["decision_reason"] = (
            "The frozen run planned 1000 independent panels/scenario against a required "
            "2000-panel precision floor; sparse empty cells require refusal of the entire "
            "Holm family. Synthetic calibration cannot establish market assumptions."
        )
        artifact["limitations"] = [
            "The HAC/t approximation has no finite-sample super-uniformity guarantee, especially with only 28 days.",
            "Lag-4 Bartlett truncation misses longer dependence; stationary weak dependence and exogenous counts are unverified.",
            "Calibration scenarios are illustrative; passing these would not prove robustness to other data-generating processes.",
            "No positive-effect power simulation was planned or performed; non-vacuity and discovery power are not established.",
            "No market data, actual p-values, returns, costs, or future observations were used.",
        ]
    except Exception as exc:
        artifact["artifact_status"] = "RUNTIME_OR_EXECUTION_FAILURE"
        artifact["calibration_gate"] = _failure_gate(artifact, active_name, active_tally)
        artifact["execution_status"] = "RUNTIME_OR_EXECUTION_FAILURE"
        artifact["error"] = f"{type(exc).__name__}: {exc}"
        status_code = 1
    finally:
        if previous_handler is not None:
            signal.signal(signal.SIGTERM, previous_handler)
    artifact["runtime_seconds"] = round(time.monotonic() - started, 6)
    try:
        write_json(OUTPUT_PATH, artifact)
    except Exception as exc:
        OUTPUT_PATH.write_text(json.dumps({
            "artifact_status": "RUNTIME_OR_EXECUTION_FAILURE",
            "calibration_gate": _failure_gate(artifact, active_name, active_tally),
            "execution_status": "RUNTIME_OR_EXECUTION_FAILURE",
            "error": f"{type(exc).__name__}: {exc}",
        }, indent=2) + "\n")
        status_code = 1
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "artifact_status": artifact["artifact_status"],
        "calibration_gate": artifact["calibration_gate"],
        "runtime_seconds": artifact["runtime_seconds"],
    }, sort_keys=True))
    return status_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-protocol", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.write_protocol:
        if PROTOCOL_PATH.exists():
            raise FileExistsError("REFUSE: never overwrite the frozen design")
        write_json(PROTOCOL_PATH, prospective_protocol())
        print(PROTOCOL_PATH)
        return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
