import unittest
from unittest import mock

import acquire_universe_approx as m

S = [
    {"id": "AUSDT", "type": "perpetual", "availableSince": "2025-01-01T00:00:00.000Z"},
    {"id": "BTCUSDT", "type": "perpetual", "availableSince": "2024-11-08T00:00:00.000Z"},
    {"id": "OLDUSDT", "type": "perpetual", "availableSince": "2025-01-01T00:00:00.000Z",
     "availableTo": "2026-09-01T00:00:00.000Z"},
    {"id": "ENDUSDT", "type": "perpetual", "availableSince": "2025-01-01T00:00:00.000Z",
     "availableTo": "2026-10-10T00:00:00.000Z"},
    {"id": "NEWUSDT", "type": "perpetual", "availableSince": "2026-10-01T00:00:00.000Z"},
    {"id": "LATEUSDT", "type": "perpetual", "availableSince": "2026-11-01T00:00:00.000Z"},
    {"id": "BTCPERP", "type": "perpetual", "availableSince": "2025-01-01T00:00:00.000Z"},
    {"id": "BTCUSDT_241227", "type": "future", "availableSince": "2025-01-01T00:00:00.000Z"},
]


class Derive(unittest.TestCase):
    def test_filters_and_classes(self):
        d = m.derive(S, panel=["BTCUSDT"], inventory=["AUSDT", "BTCUSDT", "NEWUSDT", "BTCPERP"])
        ids = {r["symbol"] for c in d["active"].values() for r in c}
        self.assertEqual(ids, {"AUSDT", "BTCUSDT", "ENDUSDT", "NEWUSDT", "BTCPERP", "BTCUSDT_241227"})
        self.assertEqual(d["counts_by_class"], {"usdt_perpetual": 4, "other_perpetual": 1, "future": 1})
        self.assertEqual([r["symbol"] for r in d["ended_in_window"]], ["ENDUSDT"])
        self.assertEqual([r["symbol"] for r in d["started_in_window"]], ["NEWUSDT"])

    def test_survivor_bias(self):
        d = m.derive(S, panel=["BTCUSDT"], inventory=["AUSDT", "BTCUSDT", "NEWUSDT"])
        b = d["survivor_bias_exposure"]
        self.assertEqual(b["ended_usdt_perpetual_not_in_panel"], ["ENDUSDT"])
        self.assertEqual(b["ended_usdt_perpetual_absent_from_current_contracts"], ["ENDUSDT"])
        self.assertEqual(b["panel_symbols_ended_in_window"], [])
        self.assertEqual(d["panel_overlap"]["usdt_perpetual_active_not_in_panel"], 3)


class Fetch(unittest.TestCase):
    def test_host_allowlist(self):
        with self.assertRaises(m.FetchError):
            m.fetch("https://evil.example/x")
        with self.assertRaises(m.FetchError):
            m.fetch("http://api.tardis.dev/x")

    def test_size_cap(self):
        resp = mock.MagicMock(status=200)
        resp.read.return_value = b"x" * (m.MAX_BYTES + 1)
        resp.__enter__.return_value = resp
        op = mock.Mock(); op.open.return_value = resp
        with self.assertRaises(m.FetchError):
            m.fetch(m.TARDIS_URL, op)

    def test_ok(self):
        resp = mock.MagicMock(status=200)
        resp.read.return_value = b"{}"
        resp.__enter__.return_value = resp
        op = mock.Mock(); op.open.return_value = resp
        self.assertEqual(m.fetch(m.TARDIS_URL, op), b"{}")


if __name__ == "__main__":
    unittest.main()
