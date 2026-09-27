#!/usr/bin/env python3
"""CLI: solve the integrated engine maintenance plan for a fleet data file.

  python solve.py data/sample_fleet.json
  python solve.py data/sample_fleet.json --shop-slots 1 --lease-cost 250 --json-out plan.json
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from engine_mro import load, solve
from engine_mro.report import text_report, to_json


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", type=Path)
    ap.add_argument("--solver", choices=["highs", "cbc", "scip"], default="highs")
    ap.add_argument("--time-limit", type=int, default=120, help="seconds")
    ap.add_argument("--gap", type=float, default=0.005, help="relative MIP gap")
    ap.add_argument("--threads", type=int, help="parallel solver threads")
    ap.add_argument("--horizon", type=int, help="override horizon [months]")
    ap.add_argument("--shop-slots", type=int, help="override shop capacity")
    ap.add_argument("--lease-cost", type=float, help="override lease cost [k$/month]")
    ap.add_argument("--json-out", type=Path, help="write the full solution as JSON")
    ap.add_argument("-v", "--verbose", action="store_true", help="show solver log")
    args = ap.parse_args(argv)

    data = load(args.data)
    overrides = {
        "horizon": args.horizon,
        "shop_slots": args.shop_slots,
        "lease_cost_per_month": args.lease_cost,
    }
    data = dataclasses.replace(data, **{k: v for k, v in overrides.items() if v is not None})

    sol = solve(
        data, solver=args.solver, time_limit=args.time_limit, gap=args.gap,
        threads=args.threads, msg=args.verbose,
    )
    print(text_report(data, sol))
    if args.json_out:
        args.json_out.write_text(to_json(sol), encoding="utf-8")
    return 0 if sol.has_solution else 1


if __name__ == "__main__":
    sys.exit(main())
