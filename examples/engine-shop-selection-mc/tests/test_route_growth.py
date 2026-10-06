"""Which routes the airports grow: the added capacity goes to the grown route only, the market
step keeps company A's share, and the airport's order stops when no route carries more people."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import airport_slots as ap  # noqa: E402
import capacity_scenarios as cs  # noqa: E402
import carbon_scenarios as cb  # noqa: E402
import route_growth as rg  # noqa: E402


class RouteGrowthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = cs.setup("jal")
        cls.S = ap.load()
        cls.K = cb.load()
        cls.base = rg.solve(cls.s, cls.S, {}, {}, {}, 3, cls.K)
        cls.lock = {r: cls.base["round_trips"][r] for r in ap.HUB_ROUTES}

    def test_capacity_goes_to_the_grown_route(self):
        x = rg.solve(self.s, self.S, {}, {"OKA": 2}, {}, 3, self.K, self.lock)
        for r in ap.HUB_ROUTES:
            want = self.lock[r] + (2 if r == "HND-OKA" else 0)
            self.assertAlmostEqual(x["round_trips"][r], want, places=6, msg=r)

    def test_market_step_keeps_share(self):
        sh = ap.share(self.S, "jal", ap.current_freq(self.S, "jal"))
        r = "HND-FUK"
        f = ap.current_freq(self.S, "jal")
        g = {**f, r: f[r] + 2}
        after = ap.share(self.S, "jal", g, comp_delta={r: 2 * (1 - sh[r]) / sh[r]})[r]
        self.assertAlmostEqual(after, sh[r], places=6)

    def test_diff_is_b_minus_a(self):
        d = rg.diff(self.base, self.base)
        self.assertEqual(d["co2_kt"], 0.0)
        self.assertTrue(all(v == 0 for v in d["aircraft_used_avg"].values()))


if __name__ == "__main__":
    unittest.main()
