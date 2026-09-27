"""The growth plan: adds never exceed either headroom, revenue follows the added ASK, and
the engine side's extra visits follow the extra cycles."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import growth_plan  # noqa: E402


class GrowthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = growth_plan.build("jal", ROOT / "demand" / "jal.json", ROOT / "runout" / "jal.json")

    def test_adds_bounded_by_both_headrooms(self):
        for r in self.out["months"]:
            self.assertLessEqual(r["add_aircraft"], r["engine_headroom_ac"])
            self.assertLessEqual(r["add_aircraft"], r["demand_headroom_ac"] + 1e-9)

    def test_revenue_and_cycles_consistent(self):
        P = self.out["params"]; T = self.out["totals"]
        ask_ac = P["cycles_per_aircraft_month"] * P["seats"] * P["stage_km"] / 1e6
        self.assertAlmostEqual(T["add_ask"], T["aircraft_months"] * ask_ac, delta=0.2)
        self.assertAlmostEqual(T["extra_cycles"], T["aircraft_months"] * P["cycles_per_aircraft_month"] * 2, delta=1)
        self.assertAlmostEqual(T["extra_visits"], T["extra_cycles"] / P["run_cycles"], delta=0.05)


if __name__ == "__main__":
    unittest.main()
