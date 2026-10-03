"""Airport layer + airline layer on the trunk: patterns chain through the hub and open only to types
whose day fits; the market's passengers split by frequency share and follow the market's seasonal
index; the monthly fleet assignment keeps every type within its aircraft, every route within its
frequency bounds, the hub routes within (and using) their slots, and the operating load factor;
leases only when it pays; a slot re-allocation moves frequencies, share and revenue the right way."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import airport_slots as ap  # noqa: E402
import demand  # noqa: E402
import fleet_from_demand as ffd  # noqa: E402
import route_fleet as rf  # noqa: E402


class RouteFleetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = rf.load(); cls.D = demand.load(); cls.S = ap.load()
        cls.types = rf.types_of(cls.R, "jal"); cls.P = rf.pattern_table(cls.R, cls.types)
        cls.r = ffd.build("jal", scenarios=(-5, 0, 5))
        cls.tr = cls.r["trunk"]

    def test_slot_data_matches_the_public_table(self):
        self.assertEqual(self.S["domestic_slots_total"], 465)
        self.assertAlmostEqual(sum(self.S["allocation"].values()), 465)
        self.assertEqual(ap.trunk_budget(self.S, "jal"), 61)

    def test_patterns_chain_and_fit_the_day(self):
        hub = self.R["hub"]
        for p in self.R["patterns"]:
            legs = p["legs"]
            self.assertTrue(legs[0].startswith(hub) and legs[-1].endswith(hub))
            for a, b in zip(legs, legs[1:]):
                self.assertEqual(a.split("-")[1], b.split("-")[0])
        for p in self.P:
            for t in p["types"]:
                self.assertLessEqual(p["day_h"][t], self.R["day_block_cap_h"])
            self.assertIn("737", p["types"])

    def test_share_follows_frequency(self):
        cur = ap.current_freq(self.S, "jal")
        sh = ap.share(self.S, "jal", cur)
        more = ap.share(self.S, "jal", {**cur, "HND-CTS": cur["HND-CTS"] + 2})
        self.assertGreater(more["HND-CTS"], sh["HND-CTS"])
        self.assertAlmostEqual(sh["HND-ITM"], 0.5)

    def test_market_follows_seasonal_index(self):
        idx = {c["month"]: c["demand_index"] for c in demand.market_view(self.D)["seasonal"]}
        to_start = (1 + self.r["derived"]["demand_growth_per_year"]) ** 2.25
        W = sum(r["market_pax_2024"] for r in self.R["routes"]) / 12 / 1e3
        for d, b in zip(self.tr["demand"], self.r["demand_rpk_737"]):
            self.assertAlmostEqual(sum(d["market_p50"].values()) / (W * to_start * b["trend"]), idx[int(d["label"][5:])], places=2)

    def test_assignment_respects_aircraft_slots_and_load_factor(self):
        a = self.tr["airport"]
        for row in self.tr["rows"]:
            for t, n in row["used_p50"].items():
                self.assertLessEqual(n, max(0, int(row["available"][t] + 1e-9)))
            hub = sum(row["round_trips_p50"][r] for r in ap.HUB_ROUTES)
            self.assertLessEqual(hub, a["budget"] + 1e-9)
            self.assertGreaterEqual(hub, int(a["budget"] * a["use_min"]))
            for r, n in row["round_trips_p50"].items():
                lo, hi = a["bounds"][r]
                self.assertLessEqual(n, hi + 1e-9); self.assertGreaterEqual(n, int(lo - 1e-9) if lo == int(lo) else int(lo) + 1)
            for r, lf in row["lf_p50"].items():
                if lf is not None:
                    self.assertLessEqual(lf, self.R["lf_ops"] + 1e-3)

    def test_quantiles_carry_more_in_a_busier_month(self):
        for row in self.tr["rows"]:
            self.assertGreaterEqual(row["carried_p90_rpk_m"], row["carried_p50_rpk_m"] * 0.995)

    def test_lease_only_when_it_pays(self):
        for m in self.tr["decisions"]["months"]:
            if m["lease_aircraft"]:
                self.assertGreater(m["revenue_recovered_oku"], 0)
            else:
                self.assertEqual(m["lease_cost_oku"], 0)

    def test_version_within_allocation_and_share_converges(self):
        v = self.tr["version"]
        for t in self.types:
            if t["trunk_aircraft"] is not None:
                self.assertLessEqual(v["by_type"][t["type"]], max(t["trunk_aircraft"], t.get("trunk_aircraft_peak", 0)))
        self.assertGreater(v["trunk_share_of_737_rpk"], 0); self.assertLess(v["trunk_share_of_737_rpk"], 1)
        last = v["share_rounds"][-1]["share"]
        self.assertEqual(last, v["share"])

    def test_slot_scenarios_move_the_right_way(self):
        rows = {x["delta_round_trips"]: x for x in self.tr["slot_scenarios"]["rows"]}
        self.assertEqual(rows[5]["budget"] - rows[0]["budget"], 5)
        self.assertLess(rows[-5]["revenue_oku"], rows[0]["revenue_oku"])
        self.assertGreater(rows[5]["revenue_oku"], rows[0]["revenue_oku"])
        self.assertLess(rows[-5]["pax_k"], rows[0]["pax_k"])

    def test_engine_flying_per_type(self):
        by = {e["type"]: e for e in self.tr["engine_flying"]}
        self.assertEqual(set(by), {t["type"] for t in self.types})
        self.assertIn("windows", by["737"])
        self.assertIn("note", by["A350"])

    def test_month_table_april_is_month_one(self):
        mt = {x["label"]: x for x in self.tr["month_table"]}
        self.assertEqual(mt["2027-04"]["fy_month"], 1); self.assertEqual(mt["2027-04"]["t"], 6); self.assertEqual(mt["2028-03"]["fy_month"], 12)


if __name__ == "__main__":
    unittest.main()
