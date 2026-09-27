"""The PDCA / OODA review: the rule layer covers both loops, findings carry evidence and a
question, and the AI layer degrades to the rule layer without credentials."""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import review  # noqa: E402

RESULTS = ROOT / "handover" / "02_results"


class ReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        b = json.loads((ROOT / "baselines" / "jal-2026-10.json").read_text(encoding="utf-8"))
        tr = next(iter(RESULTS.glob("jal-track-crunch.json")), None)
        ro = next(iter(sorted(RESULTS.glob("jal-roll-*.json"))), None)
        ru = ROOT / "runout" / "jal.json"
        load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None  # noqa: E731
        cls.F = review.facts(b, load(tr), load(ro), load(ru))
        cls.sym = review.symptoms(cls.F)

    def test_both_loops_have_findings(self):
        loops = {s["loop"] for s in self.sym}
        self.assertIn("PDCA", loops)
        if self.F.get("track"):
            self.assertIn("OODA", loops)

    def test_findings_are_well_formed(self):
        for s in self.sym:
            self.assertIn(s["stage"], review.STAGES[s["loop"]])
            self.assertIn(s["severity"], ("crit", "warn", "info", "ok"))
            self.assertTrue(s["finding"] and s["evidence"])
            if s["severity"] in ("crit", "warn"):
                self.assertTrue(s["ask"], s["finding"])

    def test_coverage_counts(self):
        cov = review.coverage(self.sym)
        self.assertEqual(sum(c["n"] for c in cov.values()), len(self.sym))

    def test_ai_layer_degrades_to_rules_without_credentials(self):
        saved = {k: os.environ.pop(k, None) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        try:
            r = review.ai_review(self.F, self.sym)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        self.assertEqual(r["mode"], "rules")
        self.assertIn("PDCA", r["text"]); self.assertIn("OODA", r["text"])


if __name__ == "__main__":
    unittest.main()
