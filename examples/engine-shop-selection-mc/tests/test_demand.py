"""The demand layer: sourced market series, spill only above the threshold, the engine
link's unit conversion, and no shortage months without negative engine margin."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import demand  # noqa: E402


class DemandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = demand.build("jal", ROOT / "runout" / "jal.json")

    def test_market_lf_is_rpk_over_ask(self):
        for x in self.out["market"]["months"]:
            self.assertAlmostEqual(x["rpk"] / x["ask"] * 100, x["lf"], delta=0.15)

    def test_spill_only_when_tight(self):
        th = self.out["carrier"]["threshold"]
        for r in self.out["carrier"]["months"]:
            if r["spilled_rpk"]:
                self.assertGreaterEqual(r["lf"] / 100, th)
            if r["lf"] is not None and r["lf"] / 100 < th and r["ask"]:
                self.assertEqual(r["spilled_rpk"], 0.0)

    def test_engine_link_units(self):
        e = self.out["engines"]
        P = e["params"]
        self.assertAlmostEqual(P["ask_per_aircraft_month"], P["cycles_per_aircraft_month"] * P["seats"] * P["stage_km"] / 1e6, places=1)
        for m in e["months"]:
            self.assertEqual(m["extra_aircraft"], max(0, m["margin"]) // 2)
            self.assertEqual(m["short_aircraft"] > 0, m["margin"] < 0)

    def test_seasonal_index_averages_to_one(self):
        S = self.out["market"]["seasonal"]
        self.assertAlmostEqual(sum(c["demand_index"] for c in S) / len(S), 1.0, delta=0.03)


if __name__ == "__main__":
    unittest.main()
