"""Demand -> plan assumptions: the derived index is the market's seasonal shape, the
utilisation multiplier stays within its cap, the past is not rewritten (the same engines
carry over) and higher utilisation never moves a limit later."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import demand  # noqa: E402
import plan_from_demand as pfd  # noqa: E402


class PlanFromDemandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.D = demand.load()
        cls.ov = pfd.derive(cls.D, "jal")
        cls.new, cls.n = pfd.build_fleet("jal", cls.ov)
        cls.cur = json.loads((ROOT / "data" / "jal" / "fleet.json").read_text(encoding="utf-8"))

    def test_derived_index_is_market_seasonality(self):
        seas = {c["month"]: c["demand_index"] for c in demand.market_view(self.D)["seasonal"]}
        self.assertEqual(self.ov["flight_index"], seas)

    def test_utilisation_within_cap(self):
        self.assertGreaterEqual(self.ov["utilisation_multiplier"], 1.0)
        self.assertLessEqual(self.ov["utilisation_multiplier"], pfd.UTIL_CAP)

    def test_past_not_rewritten(self):
        a = {e["esn"]: e for e in self.cur["engines"]}
        b = {e["esn"]: e for e in self.new["engines"]}
        common = set(a) & set(b)
        self.assertGreaterEqual(len(common), 0.8 * len(a))
        for esn in common:
            self.assertEqual(a[esn]["llp_remaining"], b[esn]["llp_remaining"])   # today's state is the same
            if self.ov["utilisation_multiplier"] > 1:
                self.assertLessEqual(b[esn]["window"][1], a[esn]["window"][1])    # flying more never delays a limit

    def test_required_positions_grow_with_demand(self):
        self.assertGreaterEqual(sum(self.new["required_positions"]), sum(self.cur["required_positions"]))


if __name__ == "__main__":
    unittest.main()
