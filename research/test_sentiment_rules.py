import tempfile
import unittest

from research import sentiment_rules as sr

PER_DAY = sr.DAY_MS // sr.BAR_MS


def synth(days, lr_fn, drift_fn):
    rows, price = {}, 100.0
    for i in range(days * PER_DAY):
        price *= 1 + drift_fn(i)
        rows[i] = {"close": price, "oi": 1000.0, "long_ratio": lr_fn(i), "taker_buy_share": 0.5}
    return rows


def prep(rows):
    table = sr.build_table(rows)
    closes = {b: r["close"] for b, r in rows.items()}
    return table, closes


def spike_every(period, level):
    return lambda i: level if i % period == 0 else 0.5


class Rules(unittest.TestCase):
    def test_limits(self):
        self.assertLessEqual(len(sr.RULES), 6)
        self.assertEqual(sr.GRID_TOTAL, 24)
        for r in sr.RULES.values():
            self.assertIn(r["default"], r["grid"])

    def test_signals(self):
        self.assertTrue(sr.signal_fires("R1_crowded_long_squeeze", 0.7, {"long_ratio": 0.71}))
        self.assertFalse(sr.signal_fires("R1_crowded_long_squeeze", 0.7, {"long_ratio": 0.69}))
        self.assertTrue(sr.signal_fires("R2_crowded_short_squeeze", 0.7, {"long_ratio": 0.29}))
        self.assertFalse(sr.signal_fires("R1_crowded_long_squeeze", 0.7, {}))

    def test_events_non_overlapping(self):
        rows = synth(2, lambda i: 0.9, lambda i: 0)
        table, closes = prep(rows)
        evs = sr.events("R1_crowded_long_squeeze", 0.7, table, closes, 0, 2 * PER_DAY)
        bars = [b for b, _ in evs]
        self.assertTrue(all(b2 - b1 >= sr.H + 1 for b1, b2 in zip(bars, bars[1:])))

    def test_embargo_split(self):
        disc, conf = sr.segment_bounds(0, 100 * PER_DAY - 1)
        self.assertEqual(disc[1], 60 * PER_DAY)
        self.assertEqual(conf[0], 61 * PER_DAY)

    def test_selection_not_retuned_on_confirmation(self):
        days = 100
        disc, conf = sr.segment_bounds(0, days * PER_DAY - 1)
        # long ratio 0.80 on bars where price then falls: discovery rewards 0.60..0.80 equally
        # (plateau); in confirmation only >=0.85 would pay off.
        def lr(i):
            return 0.82 if i % 40 == 0 else 0.5
        def drift(i):
            phase = i % 40
            in_disc = i < disc[1]
            if in_disc and 1 <= phase <= 13:
                return -0.004
            if not in_disc and 1 <= phase <= 13:
                return 0.004
            return 0.0
        table, closes = prep(synth(days, lr, drift))
        frozen = sr.select_level("R1_crowded_long_squeeze", table, closes, disc)
        self.assertEqual(frozen["status"], "candidate")
        chosen = frozen["selected_level"]
        ledger = {}
        res = sr.confirm_once(frozen, table, closes, conf, ledger)
        self.assertEqual(res["level"], chosen)  # not re-tuned
        self.assertLess(res["scenarios"]["22"]["net_mean_bp"], 0)
        self.assertEqual(sr.verdict(frozen, res, 0.001)[0], "not_proven")
        with self.assertRaises(RuntimeError):
            sr.confirm_once(frozen, table, closes, conf, ledger)
        tampered = dict(frozen, selected_level=0.85)
        with self.assertRaises(ValueError):
            sr.confirm_once(tampered, table, closes, conf, {})

    def test_spiky_threshold_fails_plateau(self):
        grid = sr.RULES["R1_crowded_long_squeeze"]["grid"]
        per = [{"level": l, "n": 40, "gross_mean_bp": 5.0} for l in grid]
        per[3]["gross_mean_bp"] = 80.0
        self.assertFalse(sr.plateau_ok(per, grid[3], grid))
        per[3]["gross_mean_bp"] = 6.0
        self.assertTrue(sr.plateau_ok(per, grid[3], grid))

    def test_spike_blocks_candidate(self):
        # only level 0.60 fires (ratio 0.62); its neighbour 0.65 has no events: a spike
        days = 100
        disc, _ = sr.segment_bounds(0, days * PER_DAY - 1)
        def lr(i):
            return 0.62 if i % 40 == 0 else 0.5
        def drift(i):
            return -0.004 if 1 <= i % 40 <= 13 else 0.0
        table, closes = prep(synth(days, lr, drift))
        sel = sr.select_level("R1_crowded_long_squeeze", table, closes, disc)
        self.assertIn(sel["status"], ("narrative_default",))
        self.assertEqual(sel["selected_level"], 0.70)

    def test_holm_and_refusal(self):
        self.assertIsNone(sr.sign_flip_p([1.0] * 5))
        adj = sr.holm([0.001, 0.5], 24)
        self.assertAlmostEqual(adj[0], 0.024)
        self.assertEqual(adj[1], 1.0)
        self.assertLess(sr.sign_flip_p([10.0] * 30), 0.01)

    def test_gates(self):
        ok = {"ok": True, "coverage_ok": True}
        self.assertEqual(sr.gate_report(70, ok), [])
        self.assertTrue(sr.gate_report(10, ok))
        self.assertTrue(sr.gate_report(70, {"ok": True, "coverage_ok": False}))

    def test_runner_not_ready_exit_2(self):
        with tempfile.TemporaryDirectory(dir=".") as d:
            result, code = sr.run(d)
        self.assertEqual(code, 2)
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertEqual(result["claim"], "none")


if __name__ == "__main__":
    unittest.main()
