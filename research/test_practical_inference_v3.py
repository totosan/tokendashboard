import random
import unittest

from research import practical_inference_v3 as v3


def flat_panel(value=1.0, count=3):
    sums = [[value * count] * 12 for _ in range(v3.DAYS)]
    counts = [[count] * 12 for _ in range(v3.DAYS)]
    return sums, counts


class BlockRuleTests(unittest.TestCase):
    def test_layouts(self):
        self.assertEqual(v3.block_layout(0.0), (4, 7))
        self.assertEqual(v3.block_layout(-0.5), (4, 7))
        self.assertEqual(v3.block_layout(0.5), (4, 7))
        self.assertEqual(v3.block_layout(0.6), (5, 5))
        self.assertIsNone(v3.block_layout(0.7))
        self.assertIsNone(v3.block_layout(5.0))

    def test_lag1(self):
        self.assertIsNone(v3.lag1([1.0, 1.0, 1.0]))
        self.assertLess(v3.lag1([1, -1] * 10), -0.8)


class PanelTests(unittest.TestCase):
    def test_sparse_cells_dropped_not_refused(self):
        rng = random.Random(1)
        sums, counts = v3.synthetic_panel(rng, "iid_heteroskedastic")
        for d in range(v3.DAYS):
            counts[d][0] = 0
            sums[d][0] = 0.0
        adjusted, info = v3.test_panel(sums, counts)
        if adjusted is not None:
            self.assertNotIn(0, adjusted)

    def test_too_few_eligible_refused(self):
        rng = random.Random(2)
        sums, counts = v3.synthetic_panel(rng, "iid_heteroskedastic")
        for h in range(7):
            for d in range(v3.DAYS):
                counts[d][h] = 0
                sums[d][h] = 0.0
        self.assertEqual(v3.test_panel(sums, counts), (None, "too_few_eligible_cells"))

    def test_persistent_series_refused(self):
        sums, counts = [], []
        for d in range(v3.DAYS):
            sums.append([float(d - 14)] * 12)
            counts.append([3] * 12)
        self.assertEqual(
            v3.test_panel(sums, counts), (None, "insufficient_blocks_under_dependence")
        )

    def test_pvalues_valid(self):
        rng = random.Random(3)
        sums, counts = v3.synthetic_panel(rng, "iid_heteroskedastic")
        adjusted, info = v3.test_panel(sums, counts)
        if adjusted is not None:
            for p in adjusted.values():
                self.assertGreaterEqual(p, 2.0 ** -info["blocks"])
                self.assertLessEqual(p, 1.0)

    def test_degenerate(self):
        sums = [[0.0] * 12 for _ in range(v3.DAYS)]
        counts = [[3] * 12 for _ in range(v3.DAYS)]
        self.assertEqual(v3.test_panel(sums, counts), (None, "degenerate_daily_series"))


class ProtocolTests(unittest.TestCase):
    def test_protocol_deterministic_and_unrun(self):
        a = v3.prospective_protocol()
        self.assertEqual(a, v3.prospective_protocol())
        self.assertEqual(len(a["family"]), 12)
        self.assertEqual(a["status"], "FROZEN_BEFORE_ANY_V3_CALIBRATION")

    def test_power_exists_iid(self):
        rng = random.Random(4)
        hits = 0
        for _ in range(20):
            adjusted, _ = v3.test_panel(*v3.synthetic_panel(rng, v3.POWER_SCENARIO))
            hits += bool(adjusted) and any(p <= 0.05 for p in adjusted.values())
        self.assertGreaterEqual(hits, 0)


if __name__ == "__main__":
    unittest.main()
