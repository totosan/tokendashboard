import io
import tempfile
import zipfile
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
        self.assertLessEqual(len(sr.RULES), 8)
        self.assertEqual(sr.GRID_TOTAL, 36)
        self.assertEqual(sum(1 for r in sr.RULES.values() if 'source' in r), 3)
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


def zipped(text):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", text)
    return b.getvalue()


METRICS = ("create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
           "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
           "2022-01-05 00:05:00,BTCUSDT,100.5,1,1,1,3.0,1.0\n"
           "1641341400000,BTCUSDT,101,1,1,1,1.0,3.0\n"
           "2022-01-05 00:15:00,BTCUSDT,,1,1,1,bad,1.0\n")


class BinanceLoader(unittest.TestCase):
    def test_metrics_zip_and_csv(self):
        for data in (zipped(METRICS), METRICS.encode()):
            rows = {}
            self.assertEqual(sr.parse_metrics_csv(data, rows), 3)
            b0 = sr._ts_ms("2022-01-05 00:05:00") // sr.BAR_MS
            self.assertEqual(rows[b0], {"oi": 100.5, "long_ratio": 0.75, "top_long_ratio": 0.5, "taker_buy_share": 0.5})
            self.assertEqual(rows[b0 + 1]["taker_buy_share"], 0.75)
            self.assertEqual(rows[b0 + 2], {"top_long_ratio": 0.5, "taker_buy_share": 0.5})  # bad fields skipped, not filled

    def test_klines_close_bucket_no_lookahead(self):
        t = sr._ts_ms("2022-01-05 00:00:00")
        rows = {}
        text = "open_time,open,high,low,close,volume\n%d,1,2,0.5,1.5,9,%d,0,0,0,0,0\n" % (t, t + 299999)
        self.assertEqual(sr.parse_klines_csv(zipped(text), rows), 1)
        self.assertEqual(rows[t // sr.BAR_MS + 1]["close"], 1.5)
        self.assertNotIn(t // sr.BAR_MS, rows)

    def test_split_frozen(self):
        disc, conf = sr.binance_segments()
        self.assertEqual((sr.BINANCE_END - sr.BINANCE_START).days + 1, 1614)
        self.assertEqual((disc[1] - disc[0]) // PER_DAY, 908)
        self.assertEqual(conf[0] - disc[1], PER_DAY)
        self.assertEqual((conf[1] - conf[0]) // PER_DAY, 705)

    def test_gate_and_not_ready(self):
        failed, pct = sr.binance_gate({})
        self.assertTrue(failed)
        self.assertEqual(pct, 0.0)
        with tempfile.TemporaryDirectory(dir=".") as d:
            result, code = sr.run_binance(d, d)
        self.assertEqual((code, result["verdict"], result["claim"]), (2, "NOT_READY", "none"))

    def test_full_synthetic_coverage_passes_gate(self):
        b0 = sr._day_bar(sr.BINANCE_START)
        n = ((sr.BINANCE_END - sr.BINANCE_START).days + 1) * PER_DAY
        rows = {b0 + i: {"oi": 1.0, "long_ratio": .5, "taker_buy_share": .5, "close": 1.0}
                for i in range(n)}
        self.assertEqual(sr.binance_gate(rows), ([], 100.0))
        for b in list(rows)[:: 2]:
            del rows[b]
        self.assertTrue(sr.binance_gate(rows)[0])

    def test_block_days(self):
        days = 100
        disc, conf = sr.segment_bounds(0, days * PER_DAY - 1)
        table, closes = prep(synth(days, spike_every(40, 0.82), lambda i: 0.0))
        frozen = sr.select_level("R1_crowded_long_squeeze", table, closes, disc)
        r1 = sr.confirm_once(frozen, table, closes, conf, {}, 1)
        r5 = sr.confirm_once(frozen, table, closes, conf, {}, 5)
        self.assertEqual(r5["block_days"], 5)
        self.assertLess(r5["day_blocks"], r1["day_blocks"])


if __name__ == "__main__":
    unittest.main()


class CommunityPriors(unittest.TestCase):
    def test_funding_contrarian_sides(self):
        r = "R6_funding_extreme_contrarian"
        self.assertTrue(sr.signal_fires(r, 0.0005, {"funding": 0.0006}))
        self.assertTrue(sr.signal_fires(r, 0.0005, {"funding": -0.0006}))
        self.assertFalse(sr.signal_fires(r, 0.0005, {"funding": 0.0001}))
        self.assertFalse(sr.signal_fires(r, 0.0005, {}))
        self.assertEqual(sr.side_for(r, {"funding": 0.001}), -1)
        self.assertEqual(sr.side_for(r, {"funding": -0.001}), 1)

    def test_top_vs_crowd_follows_top(self):
        r = "R7_top_vs_crowd_divergence"
        f = {"top_long_ratio": 0.60, "long_ratio": 0.45}
        self.assertTrue(sr.signal_fires(r, 0.10, f))
        self.assertEqual(sr.side_for(r, f), 1)
        g = {"top_long_ratio": 0.40, "long_ratio": 0.55}
        self.assertEqual(sr.side_for(r, g), -1)
        self.assertFalse(sr.signal_fires(r, 0.10, {"top_long_ratio": 0.5, "long_ratio": 0.45}))
        self.assertFalse(sr.signal_fires(r, 0.10, {"long_ratio": 0.9}))

    def test_oi_price_divergence(self):
        r = "R8_oi_price_divergence"
        self.assertTrue(sr.signal_fires(r, 0.02, {"oi_chg": 0.03, "ret": -0.001}))
        self.assertFalse(sr.signal_fires(r, 0.02, {"oi_chg": 0.03, "ret": 0.01}))
        self.assertFalse(sr.signal_fires(r, 0.02, {"oi_chg": 0.01, "ret": -0.01}))

    def test_funding_no_lookahead_and_expiry(self):
        rows = {i: {"close": 100.0} for i in range(300)}
        rows[100]["funding"] = 0.001
        t = {f["bar"]: f for f in sr.build_table(rows)}
        self.assertNotIn("funding", t[99])
        self.assertEqual(t[100]["funding"], 0.001)
        self.assertEqual(t[195]["funding"], 0.001)
        self.assertNotIn("funding", t[196])

    def test_funding_contrarian_event_sign(self):
        rows = {i: {"close": 100.0 * (0.9995 ** i)} for i in range(200)}
        rows[10]["funding"] = 0.002
        table, closes = prep(rows)
        evs = sr.events("R6_funding_extreme_contrarian", 0.001, table, closes, 0, 100)
        self.assertTrue(evs and all(g > 0 for _, g in evs))  # short a falling price

    def test_parse_funding_and_top_ratio(self):
        rows = {}
        n = sr.parse_funding_csv(b"calc_time,funding_interval_hours,last_funding_rate\n"
                                 b"1640995200000,8,0.00010000\n", rows)
        self.assertEqual(n, 1)
        self.assertEqual(rows[1640995200000 // sr.BAR_MS]["funding"], 0.0001)
        m = {}
        sr.parse_metrics_csv(b"create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
                             b"sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
                             b"2022-01-01 00:05:00,BTCUSDT,10,1,1,3.0,1.0,1.0\n", m)
        self.assertAlmostEqual(list(m.values())[0]["top_long_ratio"], 0.75)

    def test_rule_data_gate(self):
        from datetime import date
        self.assertTrue(sr.rule_data_ok("R8_oi_price_divergence", {}))
        self.assertFalse(sr.rule_data_ok("R6_funding_extreme_contrarian", {}, date(2022, 1, 1), date(2022, 1, 3)))
        rows = {}
        b0 = sr._day_bar(date(2022, 1, 1))
        for d in range(3):
            for k in (0, 96):
                rows[b0 + d * PER_DAY + k] = {"funding": 0.0001}
        self.assertTrue(sr.rule_data_ok("R6_funding_extreme_contrarian", rows, date(2022, 1, 1), date(2022, 1, 3)))
