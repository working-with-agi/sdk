import re
import unittest

import figures


class FiguresTest(unittest.TestCase):
    def test_two_pages_are_valid_svg(self):
        out = figures.svgs()
        self.assertEqual(set(out), {"plan_basic", "plan_detail"})
        for k, svg in out.items():
            self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"), k)
            self.assertNotIn(' fill="', re.search(r"<text[^>]*>", svg).group(0), k)  # text styling is inline style
            self.assertIn("px", re.search(r"<text[^>]*>", svg).group(0), k)

    def test_loops_reference_report_views_and_pages(self):
        for row in figures.LOOPS:
            self.assertEqual(len(row), 7)
            self.assertIn(row[5], ("P1", "P2"))
        self.assertTrue(any(r[0] == "F" for r in figures.LOOPS))  # the basic plan has its own loop
        self.assertTrue(any("Observe" in h[1] for h in figures.HANDOVER))  # OODA output feeds PDCA input

    def test_pages_carry_pdca_and_ooda_stages(self):
        out = figures.svgs()
        self.assertIn("PDCA：Plan", out["plan_basic"]); self.assertIn("OODA：Observe", out["plan_detail"])
        self.assertIn("← P2", out["plan_basic"]); self.assertIn("→ P1", out["plan_detail"])


if __name__ == "__main__":
    unittest.main()
