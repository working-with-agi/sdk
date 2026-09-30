"""Route layer: patterns chain through the hub, the seasonal deviations normalise to the market
index, the integer programme covers every route at the target L/F, the 737 carries its share plus
the widebody overflow, the yearly version's spill matches the L/F above target, and the whole reconciles with the trunk plus the others."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import demand  # noqa: E402
import fleet_from_demand as ffd  # noqa: E402
import route_fleet as rf  # noqa: E402


class RouteFleetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = rf.load(); cls.P = rf.pattern_table(cls.R); cls.D = demand.load()
        cls.r = ffd.build("jal")

    def test_patterns_chain_from_hub_back_to_hub(self):
        hub = self.R["hub"]
        for p in self.R["patterns"]:
            legs = p["legs"]
            self.assertTrue(legs[0].startswith(hub) and legs[-1].endswith(hub))
            for a, b in zip(legs, legs[1:]):
                self.assertEqual(a.split("-")[1], b.split("-")[0])
        self.assertTrue(all(p["fits_day"] for p in self.P))

    def test_route_seasonality_normalises_to_market(self):
        idx = {c["month"]: c["demand_index"] for c in demand.market_view(self.D)["seasonal"]}
        band = self.r["demand_rpk_737"]
        dem = rf.route_demand(self.R, self.D, "jal", band)
        W = sum(r["pax_month_k"] for r in self.R["routes"]) * 2
        for d, b in zip(dem, band):
            m = int(d["label"][5:])
            self.assertAlmostEqual(d["all_types_total_p50"] / (W * b["trend"]), idx[m], places=2)

    def test_min_aircraft_covers_every_route(self):
        lf_t = self.D["assumptions"]["lf_capacity_threshold"]; seats = self.D["companies"]["jal"]["seats_737_800"]
        d = self.r["trunk"]["demand"][10]
        need = {k: v["p50"] for k, v in d["routes"].items()}
        sol = rf.min_aircraft(self.P, need, seats, lf_t)
        sc = rf.score_assignment(self.P, sol["by_pattern"], need, seats, lf_t)
        for r, v in sc.items():
            self.assertLessEqual(v["lf"], lf_t + 1e-6); self.assertEqual(v["spill_pax_k"], 0)
        self.assertEqual(sol["aircraft"], self.r["trunk"]["rows"][10]["need_p50"])
        self.assertLessEqual(sol["aircraft"], rf.min_aircraft(self.P, need, seats, lf_t, stretch=1.0)["aircraft"])
        self.assertLessEqual(rf.min_aircraft(self.P, need, seats, lf_t, stretch=rf.DAY_STRETCH)["aircraft"], sol["aircraft"])

    def test_need_ordered_and_short_flag(self):
        for r in self.r["trunk"]["rows"]:
            self.assertLessEqual(r["need_p10"], r["need_p50"]); self.assertLessEqual(r["need_p50"], r["need_p90"])
            self.assertEqual(r["short_p90"], r["need_p90"] > r["usable"])
            # the re-mix is the best integer mix at the usable count; the version scaled to the same count
            # is a fractional mix, so it can be slightly better, never much better
            self.assertLessEqual(r["remix"]["spill_pax_k"], r["spill_fixed_pax_k"] + 0.1 * r["pax_k_p50"])

    def test_reconciliation_and_others(self):
        tr = self.r["trunk"]
        for row, o in zip(tr["reconciliation"]["rows"], tr["others"]):
            self.assertAlmostEqual(row["sum_p50"], row["trunk_need_p50"] + o["need_p50"], places=1)
            self.assertEqual(o["fleet"] + tr["trunk_aircraft"], row["fleet"])

    def test_decisions_borrow_only_after_others(self):
        d = self.r["trunk"]["decisions"]
        for m in d["with_others_first"]["months"]:
            self.assertEqual(m["short_aircraft"], m["from_others"] + m["borrow"] + m["spill_aircraft"])
        for m in d["mixed_rule"]["months"]:
            self.assertAlmostEqual(m["net_oku"], m["revenue_recovered_oku"] - m["lease_cost_oku"], delta=0.02)
            self.assertEqual(m["decision"] == "借りる", m["net_oku"] > 0)

    def test_month_table_april_is_month_one(self):
        mt = {x["label"]: x for x in self.r["trunk"]["month_table"]}
        self.assertEqual(mt["2027-04"]["fy_month"], 1); self.assertEqual(mt["2027-04"]["t"], 6); self.assertEqual(mt["2028-03"]["fy_month"], 12)

    def test_737_carries_its_share_plus_widebody_overflow(self):
        R = self.R; cap = R["wide_lf_cap"]
        share = {r["id"]: r["share_737"] for r in R["routes"]}
        for d in self.r["trunk"]["demand"]:
            for rid, v in d["routes"].items():
                allp = d["all_types_p50"][rid]; w = d["wide"][rid]
                self.assertLessEqual(v["p50"], allp + 1e-6)
                self.assertGreaterEqual(v["p50"], share[rid] * allp - 0.2)
                self.assertLessEqual(w["lf_p50"], cap + 1e-6)
                self.assertAlmostEqual(v["p50"] + w["carried_p50_k"], allp, delta=0.2)

    def test_trunk_plus_regional_matches_the_whole(self):
        for row in self.r["trunk"]["reconciliation"]["rows"]:
            self.assertLess(abs(row["sum_p50"] - row["whole_by_seat_km_p50"]) / row["whole_by_seat_km_p50"], 0.06)

    def test_version_assignment_is_smaller_than_all_on_737(self):
        tr = self.r["trunk"]
        self.assertLess(tr["trunk_aircraft"], tr["assignment_demo"]["aircraft"])

    def test_trunk_cycles_exceed_company_average(self):
        ef = self.r["trunk"]["engine_flying"]
        self.assertGreater(ef["cycles_per_aircraft_day_trunk"], ef["cycles_per_aircraft_day_company_now"])
        self.assertGreaterEqual(ef["utilisation_multiplier_from_routes"], 1.0)


if __name__ == "__main__":
    unittest.main()
