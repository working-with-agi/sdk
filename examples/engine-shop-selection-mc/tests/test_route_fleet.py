"""Route layer with several aircraft types: patterns chain through the hub and open only to types
whose day fits, route seasonality normalises to the market index, the monthly fleet assignment
keeps every type within its aircraft and every route within its slots and the operating load
factor, leases only 737s, and each type's cycles feed its engine windows."""
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
        cls.R = rf.load(); cls.D = demand.load()
        cls.types = rf.types_of(cls.R, "jal"); cls.P = rf.pattern_table(cls.R, cls.types)
        cls.r = ffd.build("jal")
        cls.tr = cls.r["trunk"]

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

    def test_route_seasonality_normalises_to_market(self):
        idx = {c["month"]: c["demand_index"] for c in demand.market_view(self.D)["seasonal"]}
        W = sum(r["pax_month_k"] for r in self.R["routes"]) * 2
        for d, b in zip(self.tr["demand"], self.r["demand_rpk_737"]):
            self.assertAlmostEqual(d["total_p50"] / (W * b["trend"]), idx[int(d["label"][5:])], places=2)

    def test_assignment_respects_aircraft_slots_and_load_factor(self):
        slots = {r["id"]: r["slots_legs_per_day"] for r in self.R["routes"]}
        for row in self.tr["rows"]:
            for t, n in row["used_p50"].items():
                self.assertLessEqual(n, int(row["available"][t] + 1e-9) if row["available"][t] >= 0 else 0)
            for r, n in row["slots_used_p50"].items():
                self.assertLessEqual(n, slots[r])
            for r, lf in row["lf_p50"].items():
                if lf is not None:
                    self.assertLessEqual(lf, rf.LF_MAX + 1e-3)

    def test_quantiles_order_the_shortfall(self):
        for row in self.tr["rows"]:
            # a busier month puts more seats up, so p90 can spill less than p50; the assignment maximises revenue,
            # so it may carry fewer passengers on longer routes, but never fewer passenger-km
            self.assertGreaterEqual(row["carried_p90_rpk_m"], row["carried_p50_rpk_m"] * 0.995)
            self.assertEqual(row["short_p90"], row["lease_p90"] > 0 or row["spill_p90_pax_k"] > 0.5)

    def test_lease_only_when_it_pays(self):
        for m in self.tr["decisions"]["months"]:
            self.assertGreaterEqual(m["lease_aircraft"], 0)
            if m["lease_aircraft"]:
                self.assertGreater(m["revenue_recovered_oku"], 0)
            else:
                self.assertEqual(m["lease_cost_oku"], 0)

    def test_version_uses_widebodies_within_their_allocation(self):
        v = self.tr["version"]["by_type"]
        for t in self.types:
            if t["trunk_aircraft"] is not None:
                self.assertLessEqual(v[t["type"]], t["trunk_aircraft"])
        self.assertGreater(sum(n for k, n in v.items() if k != "737"), 0)
        self.assertGreater(self.tr["version"]["trunk_share_of_737_rpk"], 0)
        self.assertLess(self.tr["version"]["trunk_share_of_737_rpk"], 1)

    def test_reconciliation_with_the_whole(self):
        for row in self.tr["reconciliation"]["rows"]:
            self.assertAlmostEqual(row["sum_p50"], row["trunk_737_p50"] + row["regional_p50"] + row["in_checks"], places=0)
            self.assertLess(abs(row["sum_p50"] - row["whole_by_seat_km_p50"]) / row["whole_by_seat_km_p50"], 0.2)

    def test_engine_flying_per_type(self):
        by = {e["type"]: e for e in self.tr["engine_flying"]}
        self.assertEqual(set(by), {t["type"] for t in self.types})
        for k in ("737", "767", "787"):
            e = by[k]
            if e["trunk_aircraft_used_avg"]:
                self.assertGreaterEqual(e["utilisation_multiplier"], 1.0)
                self.assertIn("windows", e)
        self.assertIn("note", by["A350"])

    def test_month_table_april_is_month_one(self):
        mt = {x["label"]: x for x in self.tr["month_table"]}
        self.assertEqual(mt["2027-04"]["fy_month"], 1); self.assertEqual(mt["2027-04"]["t"], 6); self.assertEqual(mt["2028-03"]["fy_month"], 12)


if __name__ == "__main__":
    unittest.main()
