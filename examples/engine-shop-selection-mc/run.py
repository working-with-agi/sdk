#!/usr/bin/env python3
"""Choose shop, workscope and induction month for planned engine shop visits
under cost / TAT / unscheduled-removal uncertainty.

Pipeline:
  1. Monte Carlo: sample N in-sample scenarios
  2. SAA: solve the two-stage stochastic MILP
  3. EV plan: solve the mean-value problem (deterministic benchmark)
  4. Evaluate both plans on an independent large Monte Carlo sample -> VSS, P90, CVaR
  5. (optional) statistical optimality gap from M SAA replications

  python run.py
  python run.py --cvar-weight 1.0 --replications 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shop_mc import evaluate, load, mean_value, saa_gap, sample, solve_saa

HERE = Path(__file__).resolve().parent


def describe(p, sc, plan):
    rows = []
    for i in sorted(plan.chosen, key=lambda i: sc.options[i].month):
        o = sc.options[i]
        v, k, w, t = o.visit, o.shop, o.workscope, o.month
        rows.append(
            f"  {v.esn:<6} {p.month_label(t)}  {w:<4} @ {k.id:<8}{' RUSH' if o.rush else '     '} "
            f"quote {k.quotes[w].price:>6,.0f} k$ / {o.tat()} mo"
            f"  E[cost] {sc.cost[:, i].mean():>6,.0f}  E[off-wing] {sc.down[:, i].mean():.1f} mo"
        )
    rows.append(f"  long-term spares leased: {plan.long_spares}")
    return "\n".join(rows)


def fmt_eval(name, ev):
    return (
        f"  {name:<10} mean {ev.mean:>8,.0f} (±{1.96 * ev.stderr:,.0f})  P50 {ev.p50:>8,.0f}  "
        f"P90 {ev.p90:>8,.0f}  CVaR90 {ev.cvar90:>8,.0f}  "
        f"P(AOG) {ev.aog_prob:>5.1%}  AOG eng-mo {ev.aog_engine_months:.2f}  "
        f"lease eng-mo {ev.lease_engine_months:.1f}"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--scenarios", type=int, default=200, help="in-sample scenarios for SAA")
    ap.add_argument("--eval-scenarios", type=int, default=5000, help="out-of-sample Monte Carlo runs")
    ap.add_argument("--cvar-weight", type=float, default=0.0, help="risk aversion lambda (0 = risk neutral)")
    ap.add_argument("--cvar-alpha", type=float, default=0.9)
    ap.add_argument("--replications", type=int, default=0, help="SAA replications for the gap estimate")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int)
    ap.add_argument("--time-limit", type=int, default=120)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)

    p = load(args.fleet, args.shops)
    solve_kw = dict(time_limit=args.time_limit, threads=args.threads)

    sc_in = sample(p, args.scenarios, args.seed)
    saa = solve_saa(p, sc_in, cvar_weight=args.cvar_weight, cvar_alpha=args.cvar_alpha, **solve_kw)
    ev_plan = solve_saa(p, mean_value(p, seed=args.seed + 7), **solve_kw)
    sc_out = sample(p, args.eval_scenarios, args.seed + 999)
    e_saa, e_ev = evaluate(p, saa, sc_out), evaluate(p, ev_plan, sc_out)

    print(f"SAA plan ({args.scenarios} scenarios, {saa.status})")
    print(describe(p, sc_out, saa))
    print("\nEV plan (mean-value problem)")
    print(describe(p, sc_out, ev_plan))
    print(f"\nout-of-sample Monte Carlo ({args.eval_scenarios} scenarios, k$, net of build value)")
    print(fmt_eval("SAA", e_saa))
    print(fmt_eval("EV", e_ev))
    print(f"  VSS (EV - SAA mean): {e_ev.mean - e_saa.mean:,.0f} k$")

    out = {"saa": vars(e_saa) | {"costs": None}, "ev": vars(e_ev) | {"costs": None}}
    if args.replications >= 2:
        if args.cvar_weight:
            print("\n(gap estimate skipped: only valid for the risk-neutral objective)")
        else:
            g, lows = saa_gap(p, saa, args.scenarios, args.replications, sc_out, args.seed, **solve_kw)
            print(
                f"\nSAA optimality gap ({args.replications} replications): "
                f"lower {g.lower:,.0f}  upper {g.upper:,.0f}  gap {g.gap:,.0f} k$  "
                f"95% UCL {g.gap_ci95(args.replications):,.0f} k$"
            )
            out["gap"] = {"lower": g.lower, "upper": g.upper, "gap": g.gap, "replicate_bounds": lows}
    if args.json_out:
        out["saa_plan"] = [
            {"esn": o.visit.esn, "shop": o.shop.id, "workscope": o.workscope, "month": o.month, "rush": o.rush}
            for o in (sc_out.options[i] for i in saa.chosen)
        ]
        out["saa_long_spares"] = saa.long_spares
        args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
