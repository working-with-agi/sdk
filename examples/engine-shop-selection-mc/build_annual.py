#!/usr/bin/env python3
"""Build the annual plan page (use case 1): the frozen baseline shown fiscal year by fiscal
year -- visits by month and workscope, spend against budget, engines available against
what the schedule needs plus the shelf buffer, the induction list, shop allocation -- and
a 10-year outlook from the life-cycle simulation (stationary vs aging).

  python build_annual.py --html-out annual.html        # JAL and ANA baselines, one page with a company switch
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def dataset(baseline: Path, shops: Path | None) -> dict:
    b = json.loads(baseline.read_text(encoding="utf-8"))
    shops = shops or HERE / b.get("paths", {}).get("shops", "data/shop_quotes.json")
    names = {k["id"]: k["name"] for k in json.loads(shops.read_text(encoding="utf-8"))["shops"]}
    data = {k: b[k] for k in ("version", "norms", "plan_of_record", "plan", "monthly", "budgets", "outlook")}
    data["company"] = b.get("company", {})
    data["shops"] = names
    return {"label": data["company"].get("name") or baseline.stem, "data": data}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", type=Path, nargs="+",
                    default=[HERE / "baselines" / "jal-2026-10.json", HERE / "baselines" / "ana-2026-10.json"])
    ap.add_argument("--shops", type=Path, help="default: the shop file each baseline was frozen from")
    ap.add_argument("--html-out", type=Path, default=Path("annual.html"))
    args = ap.parse_args(argv)
    sets = [dataset(b, args.shops) for b in args.baseline]
    html = (HERE / "annual_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(sets, ensure_ascii=False))
    args.html_out.write_text(html, encoding="utf-8")
    print(", ".join(f"{s['label']}: {len(s['data']['plan'])} inductions" for s in sets) + f" -> {args.html_out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
