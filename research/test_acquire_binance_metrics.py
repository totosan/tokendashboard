import tempfile
import unittest
from datetime import date
from pathlib import Path

from research import acquire_binance_metrics as ab


class Fake:
    def __init__(self, missing=(), big=False):
        self.calls, self.missing, self.big = [], set(missing), big

    def __call__(self, url, timeout, max_bytes):
        self.calls.append(url)
        if any(m in url for m in self.missing):
            return 404, None
        data = b"Z" * (max_bytes + 1 if self.big else 1000)
        return ("too_large", None) if len(data) > max_bytes else (200, data)


def go(fake, d, **kw):
    args = dict(dataset="metrics", symbols=["BTCUSDT"], start=date(2022, 1, 1), end=date(2022, 1, 10),
                directory=d, execute=True, interval=0, sleep=lambda s: None, fetcher=fake)
    args.update(kw)
    return ab.run(**args)


class Acquire(unittest.TestCase):
    def test_dry_run_no_network(self):
        with tempfile.TemporaryDirectory(dir=".") as d:
            man = ab.run("metrics", ["BTCUSDT", "ETHUSDT"], date(2022, 1, 1), date(2022, 1, 10), d, False,
                         fetcher=lambda *a: self.fail("network"))
            self.assertEqual(man["planned_files"], 20)
            self.assertEqual(man["mode"], "dry_run")
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_urls_allowlisted(self):
        items = ab.plan("klines5m", ["BTCUSDT"], date(2021, 11, 15), date(2022, 2, 1))
        self.assertEqual([i[1] for i in items], ["2021-11", "2021-12", "2022-01", "2022-02"])
        self.assertTrue(all(i[2].startswith("https://data.binance.vision/") for i in items))
        with self.assertRaises(ValueError):
            ab.fetch("https://evil.example/x.zip", 1, 10)
        with self.assertRaises(ValueError):
            ab.fetch("http://data.binance.vision/x.zip", 1, 10)

    def test_max_files_and_hash(self):
        with tempfile.TemporaryDirectory(dir=".") as d:
            man = go(Fake(), d, max_files=3)
            self.assertEqual(man["downloaded_files"], 3)
            self.assertEqual(man["stopped_by"], "max_files")
            self.assertEqual(len(man["files"][0]["sha256"]), 64)

    def test_resume_skips_existing_and_records_missing(self):
        with tempfile.TemporaryDirectory(dir=".") as d:
            go(Fake(), d, max_files=2)
            fake = Fake(missing=["2022-01-04"])
            man = go(fake, d, max_files=50)
            self.assertEqual(len(fake.calls), 8)
            self.assertEqual([m["label"] for m in man["missing"]], ["2022-01-04"])
            self.assertEqual(sum(f["source"] == "resume" for f in man["files"]), 2)

    def test_max_mib_cap(self):
        with tempfile.TemporaryDirectory(dir=".") as d:
            man = go(Fake(big=True), d)
            self.assertEqual(man["stopped_by"], "max_mib")
            self.assertEqual(man["files"], [])

    def test_estimate(self):
        man = ab.run("metrics", ["BTCUSDT"], date(2022, 1, 1), date(2022, 1, 10), ".", False)
        self.assertAlmostEqual(man["estimated_total_mib"], 10 * 11000 / 1048576, places=2)


if __name__ == "__main__":
    unittest.main()
