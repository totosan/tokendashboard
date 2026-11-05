import unittest

from research import rolling_profile_comparison as rpc
from research.g04_matrix_comparison import cell_config, run_cell


class MatrixTests(unittest.TestCase):
    def test_cell_config_hours_and_objects(self):
        config = cell_config("BTCUSDT", 15)
        self.assertEqual([o.split("/")[2] for o in config["objects"]], ["14", "15", "16"])
        self.assertEqual(config["end_ms"] - config["start_ms"], 3600000)
        self.assertEqual(cell_config("AAPLUSDT", 14)["start_ms"], rpc.START_MS)

    def test_globals_restored_after_failure(self):
        before = (rpc.SYMBOL, rpc.TRADE_OBJECTS, rpc.START_MS, rpc.END_MS)
        with self.assertRaises(Exception):
            run_cell(cell_config("BTCUSDT", 14), None, None, None, "x")
        self.assertEqual(before, (rpc.SYMBOL, rpc.TRADE_OBJECTS, rpc.START_MS, rpc.END_MS))


if __name__ == "__main__":
    unittest.main()
