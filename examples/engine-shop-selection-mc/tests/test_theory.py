"""Theory checks for the tracking / CPD / OODA / roll layer.

Run: python -m unittest discover -s tests -v

These tests exercise the pieces that handover/04_docs/theory_check.md relies on:
the switch rule (ΔV minus the late-kit premium, hysteresis over two months), the safety
switch (a change point without any world moving suspends every implicit rule), the
credibility weight, and the bridge identity in the produced roll JSONs.
"""

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cpd  # noqa: E402
import ooda  # noqa: E402
import roll  # noqa: E402
import track  # noqa: E402

RESULTS = ROOT / "handover" / "02_results"


# ---------------------------------------------------------------- 3. switch rule

def switch_saving(keep_mean, hybrid_mean, late_kits, premium):
    """Mirror of track.py status(): by_w[w]["saving"] = keep - hybrid - late * premium."""
    return keep_mean - hybrid_mean - late_kits * premium


def hysteresis_ok(best_now, best_prev, material=track.MATERIAL_K):
    """Mirror of track.py status(): 'hysteresis_ok': best_now > MATERIAL_K and best_prev > MATERIAL_K."""
    return best_now > material and best_prev > material


class SwitchRuleTest(unittest.TestCase):
    def test_late_kit_premium_is_subtracted_from_delta_v(self):
        premium = 1500.0
        self.assertEqual(switch_saving(10_000, 9_000, 0, premium), 1_000)
        self.assertEqual(switch_saving(10_000, 9_000, 1, premium), -500)   # one emergency kit flips the sign

    def test_hysteresis_needs_two_consecutive_months_above_material(self):
        seq = [500, 500, -100, 400, 350, 250, 400]
        got = [hysteresis_ok(seq[i], seq[i - 1] if i else 0.0) for i in range(len(seq))]
        self.assertEqual(got, [False, True, False, False, True, False, False])
        # exactly MATERIAL_K does not count (strict >)
        self.assertFalse(hysteresis_ok(track.MATERIAL_K, track.MATERIAL_K))

    def test_track_exposes_no_switch_rule_function(self):
        # documents the PARTIAL in theory_check.md: the rule lives inline in track.status()
        self.assertFalse(hasattr(track, "hysteresis_ok"))
        self.assertFalse(hasattr(track, "switch_value"))


# ---------------------------------------------------------------- 9. safety switch

class _P0:
    owned_engines = 30
    buffer = (2, 2)
    short_lease_max = 2
    llp_kit_lead_months = 8
    shops = []

    @staticmethod
    def month_label(t):
        return f"M{t:02d}"


def _shock_streams(months=12, rng=None):
    """Weekly quotes: quoted TAT jumps +12 weeks at week 8; nothing else moves."""
    rng = rng or np.random.default_rng(11)
    n = months * cpd.WEEKS_PER_MONTH
    lvl = np.where(np.arange(n) < 8, 10.0, 22.0)
    return {"weeks_per_month": cpd.WEEKS_PER_MONTH, "change_week": 8,
            "quoted_tat_weeks": (lvl + rng.normal(0, 0.5, n)).round(1).tolist(),
            "slot_lead_weeks": (8.0 + rng.normal(0, 0.5, n)).round(1).tolist(),
            "kit_lead_weeks": (35.0 + rng.normal(0, 0.5, n)).round(1).tolist()}


class SafetySwitchTest(unittest.TestCase):
    def setUp(self):
        self.prior = {"base": 0.5, "backlog": 0.25, "crunch": 0.15, "stress": 0.1}
        K = 12
        self.act = {"months": K, "streams": _shock_streams(K), "unscheduled_in_shop": [1] * K,
                    "inductions": [{"esn": "E1", "t": 0, "reason": "planned"}],
                    "returns": [{"esn": "E1", "t": 5, "cost_k": 9_000}]}   # invoiced above expected -> teardown_extra
        # a posterior that never moves (the shock is not one of the four worlds)
        self.timeline = [{"k": k, "as_of": f"M{k - 1:02d}", "posterior": dict(self.prior), "exceptions": [],
                          "switch": {"backlog": {"saving": -100.0, "decide_by": None}}} for k in range(1, K + 1)]
        self.b = {"norms": {"spend_per_year_k": 120_000}, "plan": [{"esn": "E1", "exp_cost": 6_000, "t": 0}],
                  "monthly": {"peak": [False] * K, "labels": [f"M{t:02d}" for t in range(K)],
                              "serviceable": [5] * K, "required": [3] * K, "buffer": [1] * K}}

    def test_cpd_fires_while_posterior_does_not_move(self):
        det = cpd.detect_streams(self.act["streams"])
        self.assertIsNotNone(det["quoted_tat_weeks"]["week"])
        self.assertEqual(det["quoted_tat_weeks"]["month"], 3)   # week 8 -> month index 3
        self.assertIsNone(det["kit_lead_weeks"]["week"])
        c = track.change_points(self.act, self.timeline, self.prior, _P0)
        self.assertEqual(c["cpd_month"], 3)
        self.assertIsNone(c["bayes_month"])
        self.assertEqual(c["state"], "cpd_only")
        self.assertTrue(all(a["state"] == "cpd_only" for a in c["agreement"][2:]))
        self.assertTrue(all(a["state"] == "none" for a in c["agreement"][:2]))
        self.cpd_block = c

    def test_safety_switch_routes_every_case_to_the_meeting(self):
        c = track.change_points(self.act, self.timeline, self.prior, _P0)
        o = ooda.replay(self.b, self.act, self.timeline, c, ooda.DEFAULT_RULES, _P0)
        self.assertGreater(len(o["cases"]), 0)
        rules_fired = {x["rule"] for x in o["cases"]}
        self.assertIn("teardown_extra", rules_fired)            # month 7 return (t=5 -> k=6... see replay: r["t"] == k-1)
        self.assertIn("safety_switch", rules_fired)
        self.assertTrue(all(x["to_meeting"] for x in o["cases"]))
        self.assertEqual(o["feedback"]["rule_cases"], 0)        # nothing decided by a rule
        self.assertEqual(o["feedback"]["no_world_fits_months"], 12 - 2)
        self.assertEqual(o["feedback"]["to_meeting_by_safety"], 10)
        teardown = [x for x in o["cases"] if x["rule"] == "teardown_extra"][0]
        self.assertEqual(teardown["decision"], "会議へ（安全スイッチ）")
        self.assertTrue(o["feedback"]["add_world"])

    def test_no_change_point_lets_rules_decide(self):
        act = dict(self.act, streams=None)
        c = track.change_points(act, self.timeline, self.prior, _P0)
        self.assertIsNone(c)
        o = ooda.replay(self.b, act, self.timeline, c, ooda.DEFAULT_RULES, _P0)
        teardown = [x for x in o["cases"] if x["rule"] == "teardown_extra"]
        self.assertEqual(len(teardown), 1)
        self.assertFalse(teardown[0]["to_meeting"])
        self.assertEqual(o["feedback"]["rule_cases"], 1)


# ---------------------------------------------------------------- 4/7. credibility and unit value

class CredAndUnitValueTest(unittest.TestCase):
    def test_cred_is_n_over_n_plus_k0(self):
        self.assertEqual(roll.K0["delay"], 12)
        self.assertAlmostEqual(roll.cred(12, 12), 0.5)
        self.assertAlmostEqual(roll.cred(0, 12), 0.0)
        self.assertAlmostEqual(roll.cred(11, 12), 11 / 23)

    def test_unit_value_formula(self):
        b = {"norms": {"spend_per_year_k": 120_000}}
        self.assertAlmostEqual(ooda.unit_value(b, _P0), 120_000 / (30 - 2) / 12)

    def test_rules_json_missing_falls_back_to_defaults(self):
        for co in ("jal", "ana"):
            if not (ROOT / "data" / co / "rules.json").exists():
                self.assertIs(ooda.load_rules(co), ooda.DEFAULT_RULES)


# ---------------------------------------------------------------- 5. bridge identity (produced results)

class BridgeIdentityTest(unittest.TestCase):
    def test_delta_steps_sum_to_level_difference(self):
        for co in ("jal", "ana"):
            p = RESULTS / f"{co}-roll-2027-10.json"
            if not p.exists():
                self.skipTest(f"{p} missing")
            steps = json.loads(p.read_text(encoding="utf-8"))["bridge"]["steps"]
            levels = [s["value"] for s in steps if s["kind"] == "level"]
            deltas = [s["value"] for s in steps if s["kind"] == "delta"]
            self.assertEqual(len(levels), 2)
            self.assertAlmostEqual(sum(deltas), levels[1] - levels[0], places=3, msg=co)
            method = [s for s in steps if s["label"].startswith("決め方を変えた分")]
            self.assertEqual(len(method), 1, co)
            self.assertEqual(method[0]["value"], 0.0, co)


if __name__ == "__main__":
    unittest.main()
