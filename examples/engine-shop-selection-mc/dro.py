#!/usr/bin/env python3
"""Distributionally robust plans (Wasserstein DRO) against the SAA plan.

Many Monte Carlo inputs are assumptions without a source. This asks how much the plan
should hedge against the assumptions being wrong:

  1. support: nominal scenarios + scenarios from stressed worlds (congestion, stress)
  2. for each radius theta, solve the DRO plan (theta = 0 is the SAA plan)
  3. evaluate every plan out of sample in each world, plus a held-out world that is
     not in the support (stronger congestion), to see if the hedge carries over
  4. pick theta by the worst world mean among the support worlds (validation);
     the held-out world is the test
  5. (--service) benchmark: SAA with the existing AOG chance constraint, on as many
     base-world scenarios as the DRO support has

Cost differences are paired (same scenarios for every plan), so they are much tighter
than the per-plan standard errors.

  python dro.py
  python dro.py --thetas 0 0.25 0.5 1 --nominal 100 --per-world 50 --json-out dro.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from decide import case_problem
import numpy as np

from shop_mc import Requirements, evaluate, load, sample, solve_saa
from shop_mc.dro import pool, remap

HERE = Path(__file__).resolve().parent
SUPPORT_WORLDS = ("backlog", "stress")
HELD_OUT = ("backlog@2",)


def plan_rows(sc, plan):
    return {o.visit.esn: (o.shop.id, o.workscope, o.month, o.rush) for o in (sc.options[i] for i in plan.chosen)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--thetas", type=float, nargs="+", default=[0.0, 0.25, 0.5, 1.0, 2.0])
    ap.add_argument("--nominal", type=int, default=100, help="nominal (base-world) scenarios")
    ap.add_argument("--per-world", type=int, default=50, help="support scenarios per stressed world")
    ap.add_argument("--eval-scenarios", type=int, default=2000, help="out-of-sample runs per world")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int)
    ap.add_argument("--time-limit", type=int, default=300)
    ap.add_argument("--gap", type=float, default=1e-3)
    ap.add_argument("--service", action="store_true", help="add the SAA + AOG chance constraint benchmark")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)

    p = load(args.fleet, args.shops)
    sup = pool(p, {w: case_problem(p, w) for w in SUPPORT_WORLDS}, args.nominal, args.per_world, args.seed)
    worlds = ("base",) + SUPPORT_WORLDS + HELD_OUT
    # one seed for every world (common random numbers): the worlds differ only in their assumptions
    evals = {
        w: remap(p, sample(p if w == "base" else case_problem(p, w), args.eval_scenarios, args.seed + 999))
        for w in worlds
    }

    solve_kw = dict(time_limit=args.time_limit, gap=args.gap, threads=args.threads)
    runs = [(f"DRO theta {th}", th, lambda th=th: solve_saa(p, sup.sc, ambiguity=sup.ambiguity(th), **solve_kw))
            for th in args.thetas]
    if args.service:
        base_sc = sample(p, sup.sc.n, args.seed)
        runs.append(("SAA + service", None, lambda: solve_saa(p, base_sc, req=Requirements(service=True), **solve_kw)))

    results, ref, ref_costs = [], None, None
    for name, theta, solve in runs:
        plan = solve()
        rows = plan_rows(sup.sc, plan)
        ref = ref or rows
        ev = {w: evaluate(p, plan, sc) for w, sc in evals.items()}
        ref_costs = ref_costs or {w: e.costs for w, e in ev.items()}
        diff = {w: e.costs - ref_costs[w] for w, e in ev.items()}
        results.append({
            "name": name,
            "theta": theta,
            "status": plan.status,
            "objective": plan.objective,
            "long_spares": plan.long_spares,
            "changed_visits": sum(rows[e] != ref[e] for e in rows),
            "rushed": sum(r[3] for r in rows.values()),
            "worlds": {w: {"mean": e.mean, "stderr": e.stderr, "p90": e.p90, "aog_prob": e.aog_prob,
                           "diff_vs_saa": float(diff[w].mean()),
                           "diff_ci95": float(1.96 * diff[w].std(ddof=1) / np.sqrt(len(diff[w])))}
                       for w, e in ev.items()},
            "worst_support": max(ev[w].mean for w in ("base",) + SUPPORT_WORLDS),
            "plan": [{"esn": e, "shop": r[0], "workscope": r[1], "month": r[2], "rush": r[3]} for e, r in sorted(rows.items())],
        })
        print(f"{name:<16} solved ({plan.status}), objective {plan.objective:,.0f} k$", flush=True)

    dro = [r for r in results if r["theta"] is not None]
    best = min(dro, key=lambda r: r["worst_support"])
    base0 = results[0]
    note = f"{args.eval_scenarios} runs each; {', '.join(HELD_OUT)} is held out"
    print(f"\nout-of-sample mean cost by world (k$, {note})")
    print(f"  {'plan':<16} changed spares" + "".join(f"{w:>12}" for w in worlds) + "   worst(support)")
    for r in results:
        cells = "".join(f"{r['worlds'][w]['mean']:>12,.0f}" for w in worlds)
        mark = "  <- chosen" if r is best else ""
        print(f"  {r['name']:<16} {r['changed_visits']:>7} {r['long_spares']:>6}{cells}   {r['worst_support']:>12,.0f}{mark}")
    print("\ncost against the SAA plan, paired (k$, mean ± 95% CI)")
    for r in results[1:]:
        cells = "".join(f"{r['worlds'][w]['diff_vs_saa']:>+9,.0f}±{r['worlds'][w]['diff_ci95']:<5,.0f}" for w in worlds)
        print(f"  {r['name']:<16}{cells}")
    print("\nP(any AOG month) by world")
    for r in results:
        cells = "".join(f"{r['worlds'][w]['aog_prob']:>12.1%}" for w in worlds)
        print(f"  {r['name']:<16}{' ' * 15}{cells}")
    print(
        f"\nchosen theta {best['theta']}: worst support world {best['worst_support'] - base0['worst_support']:+,.0f} k$, "
        f"base world {best['worlds']['base']['mean'] - base0['worlds']['base']['mean']:+,.0f} k$ (price of robustness), "
        + ", ".join(f"{w} {best['worlds'][w]['mean'] - base0['worlds'][w]['mean']:+,.0f} k$" for w in HELD_OUT)
        + " against the SAA plan (theta 0)"
    )
    if args.json_out:
        args.json_out.write_text(json.dumps({
            "support": {"nominal": args.nominal, "per_world": args.per_world, "worlds": list(SUPPORT_WORLDS)},
            "held_out": list(HELD_OUT),
            "chosen_theta": best["theta"],
            "results": results,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
