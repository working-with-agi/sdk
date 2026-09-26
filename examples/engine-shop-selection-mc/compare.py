#!/usr/bin/env python3
"""Solve the same planning problem with several methods in parallel, evaluate every
plan on one common out-of-sample Monte Carlo sample, and write a comparison
(JSON + a self-contained HTML chooser) so a planner can pick by judgement.

Methods (a portfolio from naive to risk-averse):
  quote      deterministic, quoted price / TAT taken at face value
  ev         deterministic, every parameter at its mean (mean-value problem)
  p90        deterministic, pessimistic: cost / off-wing time / removals at their P90
  saa        two-stage stochastic, risk neutral (SAA)
  cvar-*     two-stage stochastic, E + lambda * CVaR90 for several lambda

  python compare.py                       # writes compare.json and compare.html
  python compare.py --workers 4 --scenarios 200 --eval-scenarios 5000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from shop_mc import evaluate, load, mean_value, sample, solve_saa
from shop_mc.scenarios import ScenarioSet

HERE = Path(__file__).resolve().parent

METHODS = [
    # key, label, short label, kind, cvar weight
    ("quote", "見積もりどおり", "見積", "deterministic", 0.0),
    ("ev", "期待値", "期待値", "deterministic", 0.0),
    ("p90", "悲観値 (P90)", "P90", "deterministic", 0.0),
    ("saa", "確率計画 (リスク中立)", "SAA", "stochastic", 0.0),
    ("cvar-0.3", "確率計画 + CVaR λ=0.3", "λ=0.3", "stochastic", 0.3),
    ("cvar-1", "確率計画 + CVaR λ=1", "λ=1", "stochastic", 1.0),
    ("cvar-3", "確率計画 + CVaR λ=3", "λ=3", "stochastic", 3.0),
]


def quoted(p, seed):
    """Quotes at face value: no findings overrun, no delay, no unscheduled removals."""
    sc = sample(p, 1, seed)
    for i, (_v, k, w, _t) in enumerate(sc.options):
        sc.cost[0, i] = k.quotes[w].price + k.transport_cost
        sc.down[0, i] = k.transport_months + k.quotes[w].tat
    sc.unsched[:] = 0
    return sc


def pessimistic(p, seed, n=20000, q=90):
    big = sample(p, n, seed)
    return ScenarioSet(
        cost=np.percentile(big.cost, q, axis=0, keepdims=True),
        down=np.ceil(np.percentile(big.down, q, axis=0, keepdims=True)).astype(int),
        unsched=np.percentile(big.unsched, q, axis=0, keepdims=True),
        options=big.options,
    )


def run_method(args):
    """Worker: build the method's scenario set and solve (one solver thread per worker)."""
    key, cvar, fleet, shops, n, seed, time_limit = args
    p = load(fleet, shops)
    t0 = time.perf_counter()
    if key == "quote":
        sc = quoted(p, seed)
    elif key == "ev":
        sc = mean_value(p, seed=seed + 7)
    elif key == "p90":
        sc = pessimistic(p, seed + 11)
    else:
        sc = sample(p, n, seed)
    plan = solve_saa(p, sc, cvar_weight=cvar, time_limit=time_limit, threads=1)
    return key, plan, time.perf_counter() - t0


def pareto(points):
    """Indices not dominated in (mean cost, P(AOG), CVaR90) - all minimised."""
    keep = []
    for i, a in enumerate(points):
        dominated = any(
            all(b[j] <= a[j] for j in range(3)) and any(b[j] < a[j] for j in range(3))
            for k, b in enumerate(points)
            if k != i
        )
        if not dominated:
            keep.append(i)
    return keep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--eval-scenarios", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=int, default=300)
    ap.add_argument("--json-out", type=Path, default=Path("compare.json"))
    ap.add_argument("--html-out", type=Path, default=Path("compare.html"))
    ap.add_argument("--fragment", action="store_true", help="HTML without <html>/<head> wrapper")
    args = ap.parse_args(argv)

    p = load(args.fleet, args.shops)
    jobs = [
        (key, cvar, str(args.fleet), str(args.shops), args.scenarios, args.seed, args.time_limit)
        for key, _label, _short, _kind, cvar in METHODS
    ]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        solved = {key: (plan, secs) for key, plan, secs in pool.map(run_method, jobs)}
    wall = time.perf_counter() - t0

    sc_out = sample(p, args.eval_scenarios, args.seed + 999)
    lo, hi = None, None
    results = []
    for key, label, short, kind, cvar in METHODS:
        plan, secs = solved[key]
        ev = evaluate(p, plan, sc_out)
        lo = ev.costs.min() if lo is None else min(lo, ev.costs.min())
        hi = ev.costs.max() if hi is None else max(hi, ev.costs.max())
        rows = []
        for i in sorted(plan.chosen, key=lambda i: sc_out.options[i][3]):
            v, k, w, t = sc_out.options[i]
            rows.append({
                "esn": v.esn, "shop": k.id, "workscope": w, "month": t,
                "quote": k.quotes[w].price, "quoted_tat": k.quotes[w].tat,
                "exp_cost": float(sc_out.cost[:, i].mean()),
                "exp_off_wing": float(sc_out.down[:, i].mean()),
                "p90_off_wing": float(np.percentile(sc_out.down[:, i], 90)),
            })
        results.append({
            "key": key, "label": label, "short": short, "kind": kind, "cvar_weight": cvar,
            "status": plan.status, "solve_seconds": round(secs, 1),
            "long_spares": plan.long_spares, "plan": rows,
            "mean": ev.mean, "stderr": ev.stderr, "p50": ev.p50, "p90": ev.p90, "p95": ev.p95,
            "cvar90": ev.cvar90, "aog_prob": ev.aog_prob,
            "aog_engine_months": ev.aog_engine_months, "lease_engine_months": ev.lease_engine_months,
            "_costs": ev.costs,
        })

    bins = np.linspace(lo, hi, 41)
    for r in results:
        r["hist"] = np.histogram(r.pop("_costs"), bins=bins)[0].tolist()
    sig = {}
    for r in results:
        key = (r["long_spares"], tuple((x["esn"], x["shop"], x["workscope"], x["month"]) for x in r["plan"]))
        r["same_as"] = sig.get(key)
        sig.setdefault(key, r["label"])
    front = pareto([(r["mean"], r["aog_prob"], r["cvar90"]) for r in results])
    for i, r in enumerate(results):
        r["pareto"] = i in front

    out = {
        "meta": {
            "horizon": p.horizon,
            "shops": [{"id": k.id, "name": k.name, "slots": k.slots, "overrun_share": k.overrun_share} for k in p.shops],
            "engines": [v.esn for v in p.visits],
            "in_sample_scenarios": args.scenarios,
            "eval_scenarios": args.eval_scenarios,
            "workers": args.workers,
            "wall_seconds": round(wall, 1),
            "hist_edges": bins.tolist(),
            "seed": args.seed,
        },
        "methods": results,
    }
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    html = (HERE / "compare_template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(out, ensure_ascii=False))
    if not args.fragment:
        html = (
            '<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            "</head><body>\n" + html + "\n</body></html>\n"
        )
    args.html_out.write_text(html, encoding="utf-8")

    print(f"{len(METHODS)} methods solved in parallel on {args.workers} workers: {wall:.1f}s wall")
    print(f"{'method':<24}{'mean':>9}{'P90':>9}{'CVaR90':>9}{'P(AOG)':>8}{'spares':>7}  pareto  solve[s]")
    for r in results:
        print(
            f"{r['label']:<22}{r['mean']:>9,.0f}{r['p90']:>9,.0f}{r['cvar90']:>9,.0f}"
            f"{r['aog_prob']:>8.1%}{r['long_spares']:>7}  {'  *   ' if r['pareto'] else '      '}  {r['solve_seconds']:>6}"
            + (f"  (= {r['same_as']})" if r["same_as"] else "")
        )
    print(f"\nwrote {args.json_out} and {args.html_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
