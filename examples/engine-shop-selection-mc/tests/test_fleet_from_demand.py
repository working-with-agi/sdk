"""Demand -> aircraft -> engines: the need follows the demand band (p10 <= p50 <= p90), the
short flag is the p90 rule, engines are two per flying aircraft plus the spares buffer, the
levers cover the shortage they claim, and the 737-share consistency check reports the share
that would fit the fleet."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fleet_from_demand as ffd  # noqa: E402


class FleetFromDemandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = {c: ffd.build(c) for c in ("jal", "ana")}

    def test_labels_and_fiscal_years(self):
        self.assertEqual(ffd._label("2026-10", 0), "2026-10")
        self.assertEqual(ffd._label("2026-10", 6), "2027-04")
        self.assertEqual(ffd._fy("2027-03"), "FY2026")
        self.assertEqual(ffd._fy("2027-04"), "FY2027")

    def test_demand_band_is_ordered_and_widens(self):
        for r in self.r.values():
            rpk = r["demand_rpk_737"]
            self.assertEqual(len(rpk), r["horizon_months"])
            for m in rpk:
                self.assertLessEqual(m["p10"], m["p50"]); self.assertLessEqual(m["p50"], m["p90"])
            self.assertGreater(rpk[-1]["p90"] - rpk[-1]["p10"], rpk[0]["p90"] - rpk[0]["p10"])

    def test_need_follows_band_and_short_is_p90_rule(self):
        for r in self.r.values():
            for a in r["aircraft"]["rows"]:
                self.assertLessEqual(a["need_p10"], a["need_p50"]); self.assertLessEqual(a["need_p50"], a["need_p90"])
                self.assertEqual(a["short_p90"], a["need_p90"] > a["owned"])
                self.assertAlmostEqual(a["gap_p90"], a["owned"] - a["need_p90"], places=1)

    def test_engines_two_per_flying_aircraft_plus_buffer(self):
        for r in self.r.values():
            eng = r["engines"]
            for e in eng["rows"]:
                self.assertEqual(e["installed_p50"] % 2, 0)
                self.assertEqual(e["need_total_p50"], e["installed_p50"] + e["spares_buffer"] + e["spares_short_lease"])
                self.assertEqual(e["headroom_p50"], e["owned"] - e["need_total_p50"])

    def test_levers_cover_the_shortage(self):
        for r in self.r.values():
            for m in r["levers"]["short_months"]:
                by = {x["lever"]: x for x in m["levers"]}
                util, wet = by["1 機あたりの飛び方を増やす"], by["機体を短期で借りる（ウェットリース）"]
                self.assertAlmostEqual(util["aircraft"] + wet["aircraft"], m["short_aircraft_p90"], places=1)
                self.assertLessEqual(by["退役を遅らせる"]["aircraft"], m["short_aircraft_p90"] + 1e-9)
                self.assertGreater(by["見送る（乗せられない需要）"]["cost_k"], 0)

    def test_consistency_reports_fitting_share(self):
        for r in self.r.values():
            c = r["consistency"]
            self.assertLessEqual(c["share_that_fits"], c["share_737_800"] + 1e-9 if not c["fits_fleet"] else 1.0)
            if not c["fits_fleet"]:
                self.assertIn("不整合", c["verdict"])
        self.assertTrue(self.r["jal"]["consistency"]["fits_fleet"])

    def test_planning_season_has_the_series_numbers(self):
        s = self.r["jal"]["planning_season"]
        self.assertIn("FY2027", s["fiscal_years"])
        self.assertGreater(s["maintenance"]["spend_per_year_oku_yen"], 0)
        self.assertGreater(s["maintenance"]["added_by_growth_oku_yen"], 0)
        p = s["peak_month"]
        self.assertIn("lf_if_all_fly", p); self.assertIn("engines_headroom_p90", p)

    def test_assumptions_are_flagged(self):
        a = self.r["jal"]["assumptions"]
        self.assertIn("no_source", a["band"]); self.assertIn("no_source", a["wet_lease"])


if __name__ == "__main__":
    unittest.main()
