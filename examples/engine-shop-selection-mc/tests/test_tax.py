"""Checks for tax.py: the depreciation schedule, the shield PV arithmetic, the repair /
capital shares, and the shape of build() on the frozen JAL baseline.

Run: python3 -m unittest tests.test_tax
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tax  # noqa: E402


class Schedule(unittest.TestCase):
    def test_declining_balance_sums_to_cost(self):
        s = tax.declining_balance(5500.0, 10, 0.2, 0.06552, 0.25)
        self.assertEqual(len(s), 10)
        self.assertAlmostEqual(sum(s), 5500.0, places=6)
        self.assertAlmostEqual(s[0], 1100.0)
        self.assertAlmostEqual(s[1], 880.0)
        # after the switch to the revised rate the charge is flat
        self.assertAlmostEqual(s[6], s[7])
        self.assertTrue(all(a >= b - 1e-9 for a, b in zip(s, s[1:])))

    def test_straight_line(self):
        s = tax.straight_line(380.0, 38)
        self.assertEqual(len(s), 38)
        self.assertAlmostEqual(sum(s), 380.0)


class ShieldPV(unittest.TestCase):
    def test_pv_of_shield_matches_hand_sum(self):
        P = tax.load_params()
        r = P["discount_rate"]
        d = P["depreciation"]["engine"]
        sched = tax.declining_balance(1000.0, d["years"], d["rate"], d["guarantee_rate"], d["revised_rate"])
        rate = tax.rate_for(P, "FY2027")
        by_hand = sum(a * rate / (1 + r) ** i for i, a in enumerate(sched))
        self.assertAlmostEqual(tax.pv([a * rate for a in sched], r), by_hand, places=9)
        # the shield factor is between the value of an immediate deduction (1) and nothing (0)
        f = tax.shield_pv_factor(P, r)
        self.assertLess(f, 1.0)
        self.assertGreater(f, 0.5)
        self.assertAlmostEqual(f * 1000.0 * rate, by_hand, places=6)

    def test_timing_value_formula(self):
        P = tax.load_params()
        r = P["discount_rate"]
        deltas = {"answers": [{"feasible": True, "case": "backlog", "question": "外部工場の TAT が 1 か月延びたら（再計画）",
                               "delta": {"by_fiscal_year": {"FY2026": {"visits": -1, "spend": -1000.0}, "FY2027": {"visits": 1, "spend": 1000.0}}}}]}
        s = tax.shift_of(deltas, P, r)
        rate = tax.rate_for(P, "FY2026")
        self.assertAlmostEqual(s["moved_k"], 1000.0)
        self.assertAlmostEqual(s["timing_value_k"], rate * 1000.0 * (1 - 1 / (1 + r)))
        self.assertAlmostEqual(s["pre_tax_delta_k"], 0.0)
        self.assertAlmostEqual(s["after_tax_delta_k"], 0.0)


class Shares(unittest.TestCase):
    def test_shares_sum_to_one(self):
        P = tax.load_params()
        for ws, s in P["repair_vs_capital"].items():
            if isinstance(s, dict) and "repair" in s:
                self.assertAlmostEqual(s["repair"] + s["capital"], 1.0, msg=ws)
        self.assertAlmostEqual(P["repair_vs_capital"]["PR"]["repair"], 1.0)

    def test_every_parameter_has_source_and_confidence(self):
        P = tax.load_params()
        for fy, v in P["by_country"]["JP"].items():
            self.assertIn(v["corporate_effective_rate_source"]["confidence"], ("A", "B", "C", "no_source"), fy)
            self.assertIn(v["defense_surtax"]["confidence"], ("A", "B", "C", "no_source"), fy)
        for k, d in P["depreciation"].items():
            if isinstance(d, dict):
                self.assertIn("source", d, k)
                self.assertIn(d["confidence"], ("A", "B", "C", "no_source"), k)


class Build(unittest.TestCase):
    def test_build_on_jal_baseline(self):
        b = json.loads((ROOT / "baselines" / "jal-2026-10.json").read_text(encoding="utf-8"))
        fleet = json.loads((ROOT / b["paths"]["fleet"]).read_text(encoding="utf-8"))
        T = tax.build(b, fleet, None, None)
        S = T["split"]
        self.assertAlmostEqual(S["total_repair_k"] + S["total_capital_k"], S["total_spend_k"], places=6)
        self.assertAlmostEqual(sum(r["spend"] for r in S["window"]), sum(float(x["exp_cost"]) for x in b["plan"]), places=6)
        # all capital spend is depreciated eventually, so the total shield is rate × spend
        rate = tax.rate_for(P := tax.load_params(), "FY2027")
        self.assertAlmostEqual(S["shield_total_k"], S["total_spend_k"] * rate, delta=S["total_spend_k"] * 0.005)
        self.assertLess(S["shield_pv_k"], S["shield_total_k"])
        self.assertGreater(S["shield_pv_k"], S["shield_in_window_k"] * 0.9)
        self.assertEqual(len(T["shops"]["rows"]), 4)
        self.assertEqual([r["rank"] for r in T["shops"]["rows"]], [1, 2, 3, 4])
        self.assertIn(T["spares"]["rows"][0]["best"], ("buy", "long", "short"))
        self.assertTrue(T["invest"]["rows"])
        self.assertTrue(all(r["compression_gain_k"] > 0 for r in T["invest"]["rows"]))
        self.assertTrue(T["observe"])


if __name__ == "__main__":
    unittest.main()
