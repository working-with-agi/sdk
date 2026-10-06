"""Fares under the cap: the demand curve is linear through today's fare (the elasticity holds there),
a month's fare search never earns less than today's fares and stays on its grid, and an inelastic
market raises fares more than an elastic one."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capacity_scenarios as cs  # noqa: E402
import fleet_from_demand as ffd  # noqa: E402
import route_fleet as rf  # noqa: E402


class FareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = cs.setup("jal")
        ctx, _ = ffd.trunk_context(s["cid"], s["cfg"], s["rpk"], s["ac"], s["eng"], s["derived"])
        cls.R = rf.load()
        tr = rf.build("jal", s["D"], s["rpk"], ctx, quantiles=("p50",), detail=False, fiscal_years={s["fy"]})
        cls.types, cls.P, cls.slots = tr["types"], tr["patterns"], {"bounds": tr["airport"]["bounds"], "budget": tr["airport"]["budget"], "use_min": tr["airport"]["use_min"]}
        d = next(x for x in tr["demand"] if x["label"] == tr["rows"][4]["label"])            # the summer peak
        cls.pax = {r: v["p50"] for r, v in d["routes"].items()}
        cls.av = tr["rows"][4]["available"]
        cls.mu = rf.band_means(cls.R, cls.pax, tr["version"]["legs_band"])
        cls.yld = s["D"]["companies"]["jal"]["yield_yen_per_rpk"]
        cls.today = rf.assign(cls.R, cls.P, cls.types, cls.pax, cls.av, cls.mu, cls.yld, cls.slots)
        cls.inelastic = rf.price(cls.R, cls.P, cls.types, cls.pax, cls.av, cls.mu, cls.yld, cls.slots, elasticity=-0.8)
        cls.elastic = rf.price(cls.R, cls.P, cls.types, cls.pax, cls.av, cls.mu, cls.yld, cls.slots, elasticity=-1.4)

    def test_linear_demand_through_today(self):
        one = rf.assign(self.R, self.P, self.types, self.pax, self.av, self.mu, self.yld, self.slots, fare_mult={r: 1.2 for r in self.pax}, elasticity=-1.0)
        for r, v in self.pax.items():
            self.assertAlmostEqual(one["pax_after_fare_k"][r], round(v * 0.8, 1), places=0)

    def test_search_earns_at_least_today(self):
        for sol in (self.inelastic, self.elastic):
            self.assertGreaterEqual(rf.margin_k(sol), rf.margin_k(self.today) - 1e-6)
            for m in sol["fare_mult"].values():
                self.assertTrue(0.8 - 1e-9 <= m <= 1.5 + 1e-9)
                self.assertAlmostEqual(m * 20, round(m * 20), places=6)

    def test_inelastic_market_raises_more(self):
        w = self.pax
        avg = lambda sol: sum(sol["fare_mult"][r] * w[r] for r in w) / sum(w.values())
        self.assertGreater(avg(self.inelastic), avg(self.elastic))
        self.assertGreater(avg(self.inelastic), 1.0)


if __name__ == "__main__":
    unittest.main()
