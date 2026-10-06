"""Airport investment against what comes back to one airline: the unit costs follow the public
projects, the destination headroom can be raised per airport, and an option that opens the
destinations flies more of the hub's added slots than one that does not."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import airport_slots as ap  # noqa: E402
import investment_scenarios as inv  # noqa: E402


class InvestmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = inv.build("jal", options=inv.OPTIONS[1:3], log=None)

    def test_unit_costs(self):
        c = inv.cost_per_round_trip(inv.load())
        self.assertAlmostEqual(c["HND_D"], 6700 / (144000 / 730), places=0)
        self.assertAlmostEqual(c["FUK_2"], 1643 / (24000 / 730), places=0)
        self.assertAlmostEqual(inv.annuity(0.04, 30), 17.29, places=2)

    def test_destination_extra(self):
        S = ap.load()
        base = ap.destination_caps(S, "jal")
        more = ap.destination_caps(S, "jal", extra={"CTS": 4})
        self.assertEqual(more["HND-CTS"], base["HND-CTS"] + 4)
        self.assertEqual(more["HND-FUK"], base["HND-FUK"])

    def test_opening_the_destinations_pays(self):
        hnd20, open_ = self.r["rows"]
        self.assertGreater(hnd20["unusable_round_trips"], open_["unusable_round_trips"])
        self.assertGreater(open_["gain_oku_per_year"], hnd20["gain_oku_per_year"])
        self.assertGreater(open_["added_round_trips"]["HND"], hnd20["added_round_trips"]["HND"])
        self.assertEqual(hnd20["beyond_today_headroom"]["CTS"], 0)
        lo, hi = open_["cost_share_oku"]
        self.assertLessEqual(lo, hi)


if __name__ == "__main__":
    unittest.main()
