import unittest

from research.scanner_parity import (
    MINUTE,
    fixture_cases,
    pattern_reference,
    research_acceptance_guard,
    run_suite,
    tradfi_reference,
)


class ScannerParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_suite()
        cls.by_name = {item["name"]: item["output"] for item in cls.result["comparison"]}
        cls.cases = {item["name"]: item for item in fixture_cases()}

    def test_finite_original_module_and_reference_fixture_suite(self):
        self.assertEqual(self.result["fixture_count"], 18)
        self.assertTrue(all(item["reference_matched"] for item in self.result["comparison"]))

    def test_pattern_long_short_and_1m_5m_scope(self):
        long_signal = self.by_name["pattern-1m-confirmed"][0]
        self.assertEqual((long_signal["side"], long_signal["status"]), ("long", "confirmed"))
        self.assertEqual(
            (long_signal["start"], long_signal["pullbackStart"], long_signal["pullbackEnd"],
             long_signal["end"], long_signal["trigger"], long_signal["invalidation"],
             long_signal["impulseBars"], long_signal["pullbackBars"], long_signal["setupMinutes"]),
            (600_000, 780_000, 900_000, 960_000, 103.0, 102.5, 3, 2, 6),
        )
        short_signal = self.by_name["pattern-short-confirmed"][0]
        self.assertEqual((short_signal["side"], short_signal["status"]), ("short", "confirmed"))
        five_minute = self.by_name["pattern-5m-confirmed"][0]
        self.assertEqual(five_minute["minutes"], 5)
        self.assertEqual(five_minute["end"], 4_800_000)

    def test_pattern_incomplete_confirmation_boundary_and_future_invariance(self):
        watch = self.by_name["pattern-1m-pullback"]
        self.assertEqual(len(watch), 1)
        self.assertEqual(watch[0]["status"], "pullback")
        self.assertEqual(watch[0]["end"], 900_000)
        base = self.cases["pattern-1m-confirmed"]
        future_case = self.cases["pattern-future-invariance"]
        self.assertEqual(
            pattern_reference(base["candles"], base["end"], base["options"]),
            pattern_reference(future_case["candles"], future_case["end"], future_case["options"]),
        )
        self.assertEqual(
            self.by_name["pattern-1m-confirmed"],
            self.by_name["pattern-future-invariance"],
        )
        self.assertEqual(self.by_name["pattern-unsupported-2m"], [])
        self.assertEqual(self.by_name["pattern-unsupported-pullback"], [])

    def test_research_guard_rejects_gapped_baseline_even_if_candidate_is_supplied(self):
        case = self.cases["pattern-gap"]
        signal = {
            "start": 600_000, "end": 960_000,
        }
        self.assertFalse(research_acceptance_guard(case["candles"], signal, 1))
        self.assertEqual(self.by_name["pattern-gap"], [])

    def test_tradfi_exact_boundary_semantics_and_long_only_1m(self):
        watch = self.by_name["tradfi-watch"]
        self.assertEqual(watch["status"], "watch")
        self.assertEqual(
            (watch["trigger"], watch["low"], watch["retrace"],
             watch["pullbackBars"], watch["closedAt"], watch["closeAbove"]),
            (103.0, 102.0, 0.5, 2, 420_000, False),
        )
        self.assertAlmostEqual(watch["impulse"], 3.5)
        triggered = self.by_name["tradfi-triggered"]
        self.assertEqual(triggered["status"], "triggered")
        self.assertTrue(triggered["closeAbove"])
        touched_not_closed = self.by_name["tradfi-high-with-close-below"]
        self.assertEqual(touched_not_closed["status"], "triggered")
        self.assertFalse(touched_not_closed["closeAbove"])
        self.assertIsNone(self.by_name["tradfi-reject-over-retrace"])
        self.assertIsNone(self.by_name["tradfi-gap"])
        self.assertIsNone(self.by_name["tradfi-5m-unsupported"])
        self.assertIsNone(self.by_name["tradfi-short-unsupported"])
        self.assertAlmostEqual(
            self.by_name["tradfi-exact-min-impulse"]["impulse"], 3.0
        )
        base = self.cases["tradfi-watch"]
        future_case = self.cases["tradfi-future-invariance"]
        self.assertEqual(
            tradfi_reference(base["candles"], base["end"], base["minImpulse"]),
            tradfi_reference(future_case["candles"], future_case["end"],
                             future_case["minImpulse"]),
        )
        self.assertEqual(
            self.by_name["tradfi-watch"], self.by_name["tradfi-future-invariance"]
        )


if __name__ == "__main__":
    unittest.main()
