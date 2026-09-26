#!/usr/bin/env python3
"""How much do the usual levers change the outcome? Each lever is applied on its own to
the same problem, solved in parallel, and evaluated on the same Monte Carlo sample in the
base case and in the MRO-backlog case.

Levers (prices are rough public-market estimates, not quotes):
  midlife      replace a shop visit by swapping in a mid-life ("green-time") engine
               bought on the used market; the removed engine is parted out.
               net 2,600 k$ per swap (~4,800 buy - ~2,200 part-out), 1 month off wing,
               no shop slot, no LLP kit; at most 4 (6 / 8) engines on the market
  spares       two more long-term leased spare engines (120 k$/month each)
  usm          used serviceable material in CORE / FULL workscopes: -10 % on those quotes
  pool         engine pool / exchange membership: +2 short-term engines (also in peak),
               350 k$/year fee
  fixed        the Asian independent shop moves to fixed price: no overrun for the
               operator, +8 % on its quotes
  substitute   fly the missing 737-800 capacity with another type (737-8 / A321neo / 767):
               450 k$ per engine-month; other fleets can spare 2 aircraft (4 engines)
               off-peak, 1 aircraft in peaks, +1 aircraft once 737-8 deliveries build up

  python levers.py                      # writes levers.json
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
from shop_mc.data import Quote, Shop
from shop_mc.model import InfeasibleError

from decide import ALL_HARD, case_problem

HERE = Path(__file__).resolve().parent

LEVERS = {
    "none": ("打ち手なし（案A の条件）", None),
    "midlife4": ("中寿命エンジン 4 基まで", ("midlife", 4)),
    "midlife8": ("中寿命エンジン 8 基まで", ("midlife", 8)),
    "spares2": ("予備エンジン +2 基（長期リース）", ("spares", 2)),
    "usm": ("USM 部品の活用（CORE/FULL −10%）", ("usm", 0.10)),
    "pool": ("エンジン・プール契約（+2 台）", ("pool", 2)),
    "fixed": ("アジア独立系を固定価格化（+8%）", ("fixed", 0.08)),
    "substitute": ("別機種で代替運航", ("substitute", 450)),
}


def apply(p, lever):
    if lever is None:
        return p
    kind, x = lever
    if kind == "midlife":
        market = Shop(
            id="MIDLIFE", name="中寿命エンジン（中古市場）", slots=4, transport_cost=0, transport_months=0,
            overrun_share=0.0, quotes={"GT": Quote(price=2600, tat=1)}, findings_prob=0.0,
            overrun_mean=0.1, overrun_cv=0.1, shop_delay_months=(0, 1), shop_delay_probs=(0.8, 0.2),
            engine_delay_months=(0,), engine_delay_probs=(1.0,), currency="USD", booking_lead_months=2,
            max_visits=x,
        )
        visits = [dataclasses.replace(v, allowed_workscopes=v.allowed_workscopes + ("GT",)) for v in p.visits]
        # a green-time engine is expected to last to the type's retirement: valued like a CORE build
        return dataclasses.replace(p, shops=p.shops + [market], visits=visits,
                                   build_value={**p.build_value, "GT": p.build_value.get("CORE", 0.0)})
    if kind == "spares":
        return dataclasses.replace(p, owned_engines=p.owned_engines + x,
                                   extra_fixed_cost=p.extra_fixed_cost + x * p.long_spare_cost * p.horizon)
    if kind == "usm":
        shops = [dataclasses.replace(k, quotes={
            w: dataclasses.replace(q, price=q.price * (1 - x)) if w in p.llp_workscopes else q
            for w, q in k.quotes.items()}) for k in p.shops]
        return dataclasses.replace(p, shops=shops)
    if kind == "pool":
        return dataclasses.replace(p, short_lease_max=p.short_lease_max + x, short_lease_max_peak=p.short_lease_max_peak + x,
                                   extra_fixed_cost=p.extra_fixed_cost + 350 * p.horizon / 12)
    if kind == "fixed":
        shops = [dataclasses.replace(k, overrun_share=0.0, quotes={
            w: dataclasses.replace(q, price=q.price * (1 + x)) for w, q in k.quotes.items()})
            if k.id == "IND-ASIA" else k for k in p.shops]
        return dataclasses.replace(p, shops=shops)
    if kind == "substitute":
        cap = []
        for t in range(p.horizon):
            base = 2 if p.is_peak(t) else 4
            cap.append(base + (2 if p.calendar(t) >= (2027, 4) else 0))
        return dataclasses.replace(p, sub_cost=float(x), sub_cap=cap)
    raise ValueError(kind)


def job(args):
    key, fleet, shops, n, seed, time_limit, n_eval = args
    p = apply(load(fleet, shops), LEVERS[key][1])
    t0 = time.perf_counter()
    try:
        plan = solve_saa(p, sample(p, n, seed), req=Requirements(**ALL_HARD), time_limit=time_limit, threads=1)
    except InfeasibleError:
        return key, None
    out = {"solve_seconds": round(time.perf_counter() - t0, 1), "status": plan.status}
    for case in ("base", "backlog"):
        pc = case_problem(p, case)
        ev = evaluate(pc, plan, sample(pc, n_eval, seed + 999))
        out[case] = {"mean": ev.mean, "p90": ev.p90, "aog_prob": ev.aog_prob, "lease": ev.lease_engine_months}
    sc = sample(p, 1, seed)
    chosen = [sc.options[i] for i in plan.chosen]
    out["midlife_swaps"] = sum(1 for o in chosen if o.workscope == "GT")
    out["shop_mix"] = {}
    for o in chosen:
        out["shop_mix"][o.shop.id] = out["shop_mix"].get(o.shop.id, 0) + 1
    out["green_time_lost_months"] = sum(o.visit.latest - o.month for o in chosen)
    return key, out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--scenarios", type=int, default=60)
    ap.add_argument("--eval-scenarios", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=int, default=180)
    ap.add_argument("--json-out", type=Path, default=Path("levers.json"))
    args = ap.parse_args(argv)

    jobs = [(k, str(args.fleet), str(args.shops), args.scenarios, args.seed, args.time_limit, args.eval_scenarios) for k in LEVERS]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        res = dict(pool.map(job, jobs))
    wall = time.perf_counter() - t0
    ref = res["none"]
    rows = []
    for k, (label, _l) in LEVERS.items():
        r = res[k]
        if r is None:
            rows.append({"key": k, "label": label, "feasible": False})
            continue
        rows.append({
            "key": k, "label": label, "feasible": True, **r,
            "delta_base": r["base"]["mean"] - ref["base"]["mean"],
            "delta_backlog": r["backlog"]["mean"] - ref["backlog"]["mean"],
            "aog_delta_backlog": r["backlog"]["aog_prob"] - ref["backlog"]["aog_prob"],
        })
    args.json_out.write_text(json.dumps({"wall_seconds": round(wall, 1), "levers": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(jobs)} solves in parallel: {wall:.0f}s")
    print(f"{'lever':<34}{'base mean':>11}{'Δ':>8}{'AOG':>7}  {'backlog mean':>12}{'Δ':>8}{'AOG':>7}  swaps  gt-lost")
    for r in rows:
        if not r["feasible"]:
            print(f"{r['label']:<30}  infeasible")
            continue
        print(f"{r['label']:<30}{r['base']['mean']:>11,.0f}{r['delta_base']:>+8,.0f}{r['base']['aog_prob']:>7.1%}  "
              f"{r['backlog']['mean']:>12,.0f}{r['delta_backlog']:>+8,.0f}{r['backlog']['aog_prob']:>7.1%}  {r['midlife_swaps']:>5}  {r['green_time_lost_months']:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
