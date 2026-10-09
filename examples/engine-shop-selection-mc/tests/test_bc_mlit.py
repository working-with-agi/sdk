"""The MLIT-style score: the frequency benefit follows the manual's 式 5.8 with the rule of a half,
airport fees count both ends, airline profit stays out unless asked, and B/C is PV over capital."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bc_mlit as bc  # noqa: E402


class BcMlitTest(unittest.TestCase):
    def setUp(self):
        self.m = {"f0_round_trips": {"HND-FUK": 50.0, "HND-CTS": 50.0, "HND-OKA": 30.0}, "q0_pax_k": {"HND-FUK": 10000.0, "HND-CTS": 10000.0, "HND-OKA": 8000.0}}
        self.row = {"market_round_trips": {"CTS": 0.0, "FUK": 5.0, "OKA": 0.0}, "new_pax_by_route_k": {"HND-FUK": 200.0, "HND-CTS": 0.0, "HND-OKA": 0.0},
                    "margin_change_oku": {"jal": -10.0, "ana": -5.0}, "capital_oku": 420.0}
        self.fare = {"HND-FUK": 15000.0, "HND-CTS": 15000.0, "HND-OKA": 20000.0}

    def test_frequency(self):
        s = bc.score(self.row, self.m, self.fare, 0.0)
        want = 0.5 * (10000e3 + 10200e3) * 3461 * math.log(55 / 50) / 1e8
        self.assertAlmostEqual(s["annual_oku"]["frequency"], round(want, 1), places=1)
        self.assertAlmostEqual(s["annual_oku"]["airport_fees"], round(5 * 4 * 365 * 50000 / 1e8, 1), places=1)
        self.assertEqual(s["annual_oku"]["airline"], 0.0)

    def test_airline_variant_and_bc(self):
        s = bc.score(self.row, self.m, self.fare, 0.45, airline=True)
        self.assertEqual(s["annual_oku"]["airline"], -15.0)
        self.assertAlmostEqual(s["bc"], s["pv_benefit_oku"] / 420.0, places=1)
        self.assertAlmostEqual(bc.annuity(), 21.48, places=2)


if __name__ == "__main__":
    unittest.main()
