#!/usr/bin/env python3
"""Two focused sweeps that follow up on explore.py.

  breakeven   net price of a mid-life engine swap from 4,500 to 8,000 k$ (no cap on
              swaps): where does "swap instead of overhaul" stop paying?
  coupling    owned engines (spare ratio) x aircraft value x substitution capacity,
              without the shelf-buffer rule: when does the link to fleet assignment
              (which aircraft flies which flight) start to matter?

  python sensitivity.py               # writes sensitivity.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from shop_mc import Requirements, evaluate, load, sample, solve_saa
from shop_mc.model import InfeasibleError

import explore

HERE = Path(__file__).resolve().parent
BASE = {"value": 1.0, "substitute": 0, "backlog": 0, "llp": 0, "midlife": 7500}


def run(args):
    kind, f, owned, cap, buffer, fleet, shops = args
    p = explore.build(load(fleet, shops), f)
    p = dataclasses.replace(p, shops=[dataclasses.replace(k, max_visits=cap) if k.id == "MIDLIFE" else k for k in p.shops])
    if owned:
        p = dataclasses.replace(p, owned_engines=owned, background_engines=owned - len(p.visits))
    try:
        plan = solve_saa(p, sample(p, 40, 42), req=Requirements(**{**explore.REQ, "buffer": buffer}), time_limit=120, threads=1)
    except InfeasibleError:
        return {"kind": kind, "f": f, "owned": owned or p.owned_engines, "feasible": False}
    ev = evaluate(p, plan, sample(p, 1500, 1041))
    ch = [sample(p, 1, 42).options[i] for i in plan.chosen]
    return {
        "kind": kind, "f": f, "owned": p.owned_engines, "feasible": True,
        "mean": ev.mean, "aog_prob": ev.aog_prob, "swaps": sum(o.workscope == "GT" for o in ch),
        "spares": plan.long_spares, "early_months": sum(o.visit.latest - o.month for o in ch),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--json-out", type=Path, default=Path("sensitivity.json"))
    args = ap.parse_args(argv)
    fs = (str(args.fleet), str(args.shops))
    jobs = [("breakeven", {**BASE, "midlife": m}, None, 999, True, *fs) for m in range(4500, 8001, 500)]
    jobs += [("coupling", {**BASE, "backlog": 1, "value": v, "substitute": s}, o, 8, False, *fs)
             for o in (156, 160, 166) for v in (0.5, 1.0, 2.0) for s in (0, 1)]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        res = list(pool.map(run, jobs))
    args.json_out.write_text(json.dumps({"wall_seconds": round(time.perf_counter() - t0, 1), "runs": res},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res:
        if not r["feasible"]:
            print(r["kind"], r["f"], "infeasible")
            continue
        print(f"{r['kind']:<9} owned {r['owned']}  midlife {r['f']['midlife']:>5}  value {r['f']['value']:<4} sub {r['f']['substitute']}"
              f"  cost {r['mean']:>10,.0f}  AOG {r['aog_prob']:5.1%}  swaps {r['swaps']:>2}  early {r['early_months']:>3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
