"""Backtest: the demand-rule backtest never uses data from the year it predicts, its
error columns are consistent, and the engine backtest's coverage is a share."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backtest  # noqa: E402
import demand  # noqa: E402


class BacktestTest(unittest.TestCase):
    def test_demand_rule_uses_only_prior_years(self):
        D = demand.load()
        out = backtest.demand_backtest(D)
        rpk = {f["fy"]: f["rpk"] for f in D["market"]["fiscal_years"]}
        for r in out["rows"]:
            y = int(r["fy"][2:])
            short = (rpk[f"FY{y - 1}"] / rpk[f"FY{y - 3}"]) ** 0.5 - 1
            self.assertAlmostEqual(r["short"], short, places=3)
            self.assertAlmostEqual(r["realised"], rpk[f"FY{y}"] / rpk[f"FY{y - 1}"] - 1, places=3)
            self.assertAlmostEqual(r["err_short"], r["realised"] - r["short"], places=3)

    def test_engine_backtest_shape(self):
        e = backtest.engine_backtest("jal", years=2, scenarios=10)
        self.assertGreaterEqual(e["n_versions"], 1)
        self.assertTrue(0.0 <= e["coverage"] <= 1.0)
        self.assertEqual(len(e["timing"]["hist"]), len(e["timing"]["hist_bins"]) - 1)


if __name__ == "__main__":
    unittest.main()
