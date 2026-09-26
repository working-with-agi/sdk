#!/usr/bin/env python3
"""Build the annual plan page (use case 1): the frozen baseline shown fiscal year by fiscal
year -- visits by month and workscope, spend against budget, engines available against
what the schedule needs plus the shelf buffer, the induction list, shop allocation -- and
a 10-year outlook from the life-cycle simulation (stationary vs aging).

  python build_annual.py --baseline baselines/2026-10.json --html-out annual.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", type=Path, default=HERE / "baselines" / "2026-10.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--html-out", type=Path, default=Path("annual.html"))
    args = ap.parse_args(argv)
    b = json.loads(args.baseline.read_text(encoding="utf-8"))
    shops = {k["id"]: k["name"] for k in json.loads(args.shops.read_text(encoding="utf-8"))["shops"]}
    data = {k: b[k] for k in ("version", "norms", "plan_of_record", "plan", "monthly", "budgets", "outlook")}
    data["shops"] = shops
    html = (HERE / "annual_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    args.html_out.write_text(html, encoding="utf-8")
    print(f"{len(data['plan'])} inductions, {len(data['monthly']['labels'])} months -> {args.html_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
