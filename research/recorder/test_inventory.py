import json
import tempfile
import unittest
from pathlib import Path

from research.recorder import inventory_diff, recorder

DAY1 = 1_700_000_000_000_000_000  # 2023-11-14T22:13:20Z
DAY2 = DAY1 + 86_400 * 10**9
DAY2_SAME = DAY2 + 60 * 10**9


def rows(*items):
    return [{"symbol": s, "symbolStatus": st, "offTime": "-1", "limitOpenTime": "-1",
             "launchTime": "1"} for s, st in items]


def fetcher(data, calls):
    def fetch(url, timeout):
        calls.append(url)
        return json.dumps({"code": "00000", "requestTime": 1, "data": data}).encode()
    return fetch


def run(root, data, now, calls):
    return recorder.run(root, ["BTCUSDT"], 2, 0, 60, wait=lambda s: None, now_ns=lambda: now,
                        min_gap=0, fetcher=fetcher(data, calls),
                        clock_status=lambda: {"ntp_synchronized": True, "source": "test"})


class InventoryTests(unittest.TestCase):
    def setUp(self):
        recorder.STOP.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def inv_calls(self, calls):
        return [c for c in calls if "symbol=" not in c and "contracts" in c]

    def test_once_per_utc_day_and_hashed(self):
        calls = []
        data = rows(("BTCUSDT", "normal"))
        s = run(self.root, data, DAY1, calls)
        self.assertEqual(len(self.inv_calls(calls)), 1)  # 2 cycles, one snapshot
        self.assertEqual(s["inventory_recorded"], 1)
        run(self.root, data, DAY1 + 10**9, calls)
        self.assertEqual(len(self.inv_calls(calls)), 1)  # same day: no new snapshot
        run(self.root, data, DAY2, calls)
        self.assertEqual(len(self.inv_calls(calls)), 2)
        recs = inventory_diff.load_inventories(self.root)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["kind"], "inventory")
        self.assertEqual(recs[0]["record_sha256"], recorder.record_hash(recs[0]))
        self.assertEqual(recs[0]["fields"]["symbol_count"], 1)

    def test_failure_is_retried_next_run_without_state(self):
        calls = []
        s = run(self.root, [], DAY1, calls)  # empty inventory is invalid
        self.assertEqual([f["kind"] for f in s["failures"] if f["kind"] == "inventory"],
                         ["inventory"])
        self.assertTrue(recorder.inventory_due(self.root, DAY1 // 10**6))

    def test_diff_added_removed_status_changed(self):
        run(self.root, rows(("BTCUSDT", "normal"), ("OLDUSDT", "normal"), ("KEEPUSDT", "normal")),
            DAY1, [])
        run(self.root, rows(("BTCUSDT", "limit_open"), ("NEWUSDT", "normal"),
                            ("KEEPUSDT", "normal")), DAY2, [])
        (d,) = inventory_diff.diff_all(self.root)
        self.assertEqual(d["added"], ["NEWUSDT"])
        self.assertEqual(d["removed"], ["OLDUSDT"])
        self.assertEqual(d["changed"], {"BTCUSDT": {"symbolStatus": ["normal", "limit_open"]}})


if __name__ == "__main__":
    unittest.main()
