"""The document critic's rule layer: overclaims, unsourced assumptions, the unverified ledger,
public-repository words, structure, and numbers checked against the model outputs at the
precision they are shown with."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import doc_critic as dc  # noqa: E402

DOC = """# 結果
すべて合成データ。
羽田の枠で決まっていた。
需要の伸びは 3.8% と仮定した。
需要の伸びは 3.8% と仮定した（no_source）。
この値は原典で未確認。
JAL の機材。
| a | b |
|---|---|
| 1 | 2 | 3 |
差し引きは 1063.5 億円、手計算で 123.4。
## 限界
"""


class DocCriticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vals = {d: {round(1063.5, d)} for d in range(7)}
        cls.F = dc.rules(DOC, cls.vals)
        cls.kinds = [f["kind"] for f in cls.F]

    def test_overclaim_and_assumption(self):
        self.assertIn("overclaim", self.kinds)
        a = [f for f in self.F if f["kind"] == "assumption"]
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["line"], 4)

    def test_ledger_public_structure(self):
        self.assertIn("unverified", self.kinds)
        self.assertTrue(any(f["kind"] == "public" for f in self.F))
        self.assertTrue(any(f["kind"] == "structure" and "列数" in f["why"] for f in self.F))
        self.assertFalse(any(f["kind"] == "structure" and "限界" in f["why"] for f in self.F))
        self.assertEqual(len(dc.rules(DOC, None, public=False)) < len(dc.rules(DOC, None)), True)

    def test_numbers_at_shown_precision(self):
        nums = [f for f in self.F if f["kind"] == "number"]
        flagged = " ".join(f["why"] for f in nums)
        self.assertIn("123.4", flagged)
        self.assertNotIn("1063.5", flagged)
        self.assertTrue(dc.number_found("106.35", {d: {round(1063.5, d)} for d in range(7)}))   # a power-of-ten shift
        self.assertFalse(dc.number_found("1063.6", {d: {round(1063.5, d)} for d in range(7)}))

    def test_rule_text_without_ai(self):
        r = dc.build(ROOT / "README.md", use_ai=False, check_numbers=False)
        self.assertEqual(r["critique"]["mode"], "rules")
        self.assertIn("規則層のみ", r["critique"]["text"])


if __name__ == "__main__":
    unittest.main()
