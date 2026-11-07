import json
import math
import random
import unittest

from research import practical_inference_v2 as v2


def _panel(value=1.0, count=3):
    sums = [[value] * 12 for _ in range(28)]
    counts = [[count] * 12 for _ in range(28)]
    return sums, counts


class PracticalInferenceV2Tests(unittest.TestCase):
    def test_protocol_matches_code_and_family_is_strict_subset(self):
        protocol = json.loads(v2.PROTOCOL_PATH.read_text())
        self.assertEqual(protocol, v2.prospective_protocol())
        frozen, family = v2._frozen()
        self.assertEqual(len(family), 12)
        self.assertEqual(len(set(family)), 12)
        self.assertTrue(all(h.startswith("three_close_momentum|") for h in family))
        self.assertEqual(protocol["config"]["panels_per_scenario"], 2000)

    def test_frozen_inputs_untouched_by_hash(self):
        protocol = json.loads(v2.PROTOCOL_PATH.read_text())
        self.assertEqual(
            protocol["source_hashes"]["research/results/walkforward-protocol.json"],
            v2._sha(v2.WALKFORWARD_PATH),
        )

    def test_sign_vectors_exact_enumeration(self):
        self.assertEqual(len(v2.SIGNS), 128)
        self.assertEqual(len(set(v2.SIGNS)), 128)
        self.assertEqual(v2.SIGNS[0], (1.0,) * 7)

    def test_count_generator_follows_frozen_two_plus_bernoulli(self):
        rng = random.Random(7)
        values = []
        for _ in range(30):
            _, counts = v2.synthetic_panel(rng, "iid_heteroskedastic")
            values.extend(c for row in counts for c in row)
        self.assertEqual(set(values), {2, 3})
        self.assertAlmostEqual(sum(c == 3 for c in values) / len(values), 0.5, delta=0.03)

    def test_sparse_counts_are_zero_or_two_three(self):
        rng = random.Random(8)
        _, counts = v2.synthetic_panel(rng, "sparse_days")
        flat = {c for row in counts for c in row}
        self.assertTrue(flat <= {0, 2, 3})
        self.assertIn(0, flat)

    def test_same_seed_is_deterministic(self):
        a = v2.synthetic_panel(random.Random(3), "skewed_mean_zero")
        b = v2.synthetic_panel(random.Random(3), "skewed_mean_zero")
        self.assertEqual(a, b)

    def test_strong_positive_effect_is_rejected(self):
        rng = random.Random(5)
        sums, counts = _panel(0.0)
        for d in range(28):
            for h in range(12):
                sums[d][h] = 1.0 + 0.05 * rng.gauss(0, 1)
        adjusted, _ = v2.test_panel(sums, counts)
        self.assertTrue(all(p <= v2.ALPHA for p in adjusted))

    def test_negative_effect_not_rejected(self):
        sums, counts = _panel(-1.0)
        adjusted, _ = v2.test_panel(sums, counts)
        self.assertTrue(all(p > v2.ALPHA for p in adjusted))

    def test_refuses_ineligible_and_degenerate_cells(self):
        sums, counts = _panel(1.0, 3)
        for d in range(28):
            counts[d][4] = 0
            sums[d][4] = 0.0
        self.assertEqual(v2.test_panel(sums, counts), (None, "ineligible_cell"))
        sums, counts = _panel(0.0, 3)
        self.assertEqual(v2.test_panel(sums, counts), (None, "degenerate_cell"))

    def test_validation_rejects_malformed(self):
        sums, counts = _panel()
        with self.assertRaises(ValueError):
            v2.validate_panel(sums[:-1], counts[:-1])
        sums[0][0] = math.nan
        with self.assertRaises(ValueError):
            v2.validate_panel(sums, counts)

    def test_wilson_known_value(self):
        low, high = v2.wilson(50, 1000)
        self.assertAlmostEqual(low, 0.0381, places=3)
        self.assertAlmostEqual(high, 0.0653, places=3)

    def _reports(self, null_hits, power_hits, refused=0):
        out = []
        for name in v2.SCENARIOS:
            t = v2.Tally(name)
            hits = power_hits if name == v2.POWER_SCENARIO else null_hits
            for i in range(v2.PANELS):
                if i < refused:
                    t.add(None, "ineligible_cell")
                else:
                    t.add([0.01 if i < hits else 1.0] * 12, None)
            out.append(t.report())
        return out

    def test_gate_pass_fail_inconclusive(self):
        self.assertEqual(v2.decide(self._reports(60, 1500)), "PASS")
        self.assertEqual(v2.decide(self._reports(200, 1500)), "FAIL")
        self.assertEqual(v2.decide(self._reports(60, 100)), "FAIL")
        self.assertEqual(v2.decide(self._reports(60, 600)), "INCONCLUSIVE")
        self.assertEqual(v2.decide(self._reports(140, 1500)), "INCONCLUSIVE")
        self.assertEqual(v2.decide(self._reports(60, 1500, refused=200)), "INCONCLUSIVE")
        self.assertEqual(v2.decide(self._reports(60, 1500), runtime_failed=True), "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
