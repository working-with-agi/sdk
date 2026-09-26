#!/usr/bin/env python3
"""What can we do, and what does each action change?

Every action in the catalogue is applied on its own, re-optimised and evaluated by
Monte Carlo in three cases; then pairs are solved to see which actions add up and which
cancel out; finally a greedy bundle is built, one action at a time, to show how far the
outcome improves as more is done.

Cases
  base         inputs as given
  backlog      external shops +1 month TAT (MRO congestion)
  transition   737-8 deliveries replace 737-800s: from 2027-01 one aircraft every two
               months (21 announced from 2026), so the 737-800 fleet needs 2 fewer
               engines on wing per delivery

Action catalogue (prices are rough public-market estimates, not quotes)
  procurement  midlife     swap in a mid-life engine instead of a shop visit
                           (net 5,000 k$ per swap, at most 8 on the market)
               usm         used serviceable material in CORE / FULL: -10 %
               kits_ahead  order 4 LLP kits now (holding cost 6 %/year on 3,500 k$ each)
  contracts    slots       reserve 2 more slots at the OEM network shop (400 k$/year)
               fixed       Asian independent shop at fixed price (+8 %)
               pool        engine pool / exchange: +2 short-term engines (350 k$/year)
  operations   substitute  fly missing capacity with another type (450 k$ / engine-month)
               rotate      move high-margin engines to low-utilisation aircraft: one in
                           three engines can run one month longer (60 k$ per move)
  assets       spares      two more long-term leased spare engines
               partout     part out an engine instead of overhauling it (1,800 k$ credit,
                           the engine leaves the fleet) -- pays when the fleet shrinks

  python actions.py                    # writes actions.json
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from shop_mc import Requirements, evaluate, load, sample, solve_saa
from shop_mc.data import Quote, Shop
from shop_mc.model import InfeasibleError

from decide import ALL_HARD, REQS, assess, case_problem
from levers import apply as apply_lever

HERE = Path(__file__).resolve().parent

CATALOGUE = {
    "midlife": ("調達", "中寿命エンジンへの入れ替え（正味 5,000 k$、最大 8 基）"),
    "usm": ("調達", "USM 部品の活用（CORE/FULL −10%）"),
    "kits_ahead": ("調達", "LLP キット 4 セットを先行発注"),
    "slots": ("契約", "OEM 工場の枠を 2 つ事前確保"),
    "fixed": ("契約", "アジア独立系を固定価格化（+8%）"),
    "pool": ("契約", "エンジン・プール契約（+2 台）"),
    "substitute": ("運用", "別機種での代替運航"),
    "rotate": ("運用", "ローテーションで寿命を 1 か月延ばす（3 基に 1 基）"),
    "spares": ("資産", "予備エンジン +2 基（長期リース）"),
    "partout": ("資産", "整備せず部品取りで打ち切る"),
}
CASES = {"base": "基準", "backlog": "MRO 混雑", "transition": "機材更新（737-8 受領）"}
REQ = {**ALL_HARD, "kits_on_hand_only": False, "no_new_spares": False}


def with_case(p, case):
    if case == "transition":
        req = []
        for t in range(p.horizon):
            y, m = p.calendar(t)
            delivered = max(0, (y - 2027) * 12 + m + 1) // 2  # one every two months from 2027-01
            req.append(max(0, p.required_positions[t] - 2 * delivered))
        return dataclasses.replace(p, required_positions=req)
    return case_problem(p, case)


def apply_action(p, a):
    if a in ("usm", "pool", "fixed", "spares"):
        return apply_lever(p, {"usm": ("usm", 0.10), "pool": ("pool", 2), "fixed": ("fixed", 0.08), "spares": ("spares", 2)}[a])
    if a == "substitute":
        return apply_lever(p, ("substitute", 450))
    if a == "midlife":
        p = apply_lever(p, ("midlife", 8))
        return dataclasses.replace(p, shops=[
            dataclasses.replace(k, quotes={"GT": dataclasses.replace(k.quotes["GT"], price=5000.0)}) if k.id == "MIDLIFE" else k
            for k in p.shops])
    if a == "kits_ahead":
        return dataclasses.replace(p, llp_kits_on_hand=p.llp_kits_on_hand + 4,
                                   extra_fixed_cost=p.extra_fixed_cost + 4 * 3500 * 0.06 * p.horizon / 12)
    if a == "slots":
        return dataclasses.replace(p, shops=[dataclasses.replace(k, slots=k.slots + 2) if k.id == "OEM-ASIA" else k for k in p.shops],
                                   extra_fixed_cost=p.extra_fixed_cost + 400 * p.horizon / 12)
    if a == "rotate":
        visits = [dataclasses.replace(v, latest=min(p.horizon - 1, v.latest + 1)) if j % 3 == 0 else v for j, v in enumerate(p.visits)]
        moved = sum(1 for j, v in enumerate(p.visits) if j % 3 == 0 and v.latest < p.horizon - 1)
        return dataclasses.replace(p, visits=visits, extra_fixed_cost=p.extra_fixed_cost + 60 * moved)
    if a == "partout":
        yard = Shop(
            id="PARTOUT", name="部品取り（退役）", slots=99, transport_cost=0, transport_months=0,
            overrun_share=0.0, quotes={"PO": Quote(price=-1800.0, tat=10 * p.horizon)}, findings_prob=0.0,
            overrun_mean=0.1, overrun_cv=0.1, shop_delay_months=(0,), shop_delay_probs=(1.0,),
            engine_delay_months=(0,), engine_delay_probs=(1.0,),
        )
        visits = [dataclasses.replace(v, allowed_workscopes=v.allowed_workscopes + ("PO",)) for v in p.visits]
        return dataclasses.replace(p, shops=p.shops + [yard], visits=visits, build_value={**p.build_value, "PO": 0.0})
    raise ValueError(a)


def build(fleet, shops, actions, case):
    p = load(fleet, shops)
    for a in actions:
        p = apply_action(p, a)
    return with_case(p, case)


def job(args):
    actions, case, fleet, shops, n, seed, time_limit, n_eval = args
    p = build(fleet, shops, actions, case)
    t0 = time.perf_counter()
    try:
        plan = solve_saa(p, sample(p, n, seed), req=Requirements(**REQ), time_limit=time_limit, threads=1)
    except InfeasibleError:
        return actions, case, None
    sc = sample(p, n_eval, seed + 999)
    a = assess(p, plan, sc)
    ch = [sc.options[i] for i in plan.chosen]
    return actions, case, {
        "mean": a["mean"], "p90": a["p90"], "aog_prob": a["aog_prob"],
        "budget_over_max": max(a["budget_over"].values()),
        "met": a["met"], "spares": a["long_spares"], "kits": a["emergency_kits"],
        "swaps": sum(o.workscope == "GT" for o in ch), "partouts": sum(o.workscope == "PO" for o in ch),
        "early_months": sum(o.visit.latest - o.month for o in ch if o.workscope != "PO"),
        "seconds": round(time.perf_counter() - t0, 1),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--scenarios", type=int, default=40)
    ap.add_argument("--eval-scenarios", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=int, default=120)
    ap.add_argument("--bundle-steps", type=int, default=5)
    ap.add_argument("--json-out", type=Path, default=Path("actions.json"))
    args = ap.parse_args(argv)
    common = (str(args.fleet), str(args.shops), args.scenarios, args.seed, args.time_limit, args.eval_scenarios)
    t0 = time.perf_counter()

    def run(jobs):
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            return {(tuple(a), c): r for a, c, r in pool.map(job, jobs)}

    # 1. every action alone, in every case
    singles = run([(acts, c, *common) for acts in [()] + [(a,) for a in CATALOGUE] for c in CASES])
    # 2. pairs in the base and transition cases
    pairs = run([(pair, c, *common) for pair in itertools.combinations(CATALOGUE, 2) for c in ("base", "transition")])

    def score(r):
        # requirements broken are counted first (priority order does not matter here: any
        # break disqualifies), then expected cost
        return (10**9 if r is None else sum(not v for k, v in r["met"].items() if k != "service") * 10**7 + r["mean"])

    # 3. greedy bundle on the probability-weighted cases
    weights = {"base": 0.5, "backlog": 0.25, "transition": 0.25}
    bundle, curve = [], []
    cur = {c: singles[((), c)] for c in CASES}
    curve.append({"actions": [], **{c: cur[c] for c in CASES}})
    for _ in range(args.bundle_steps):
        cand = [a for a in CATALOGUE if a not in bundle]
        res = run([(tuple(bundle + [a]), c, *common) for a in cand for c in CASES])
        best, best_val = None, sum(weights[c] * score(cur[c]) for c in CASES)
        for a in cand:
            val = sum(weights[c] * score(res[(tuple(bundle + [a]), c)]) for c in CASES)
            if val < best_val - 50:  # ignore gains inside Monte Carlo noise
                best, best_val = a, val
        if best is None:
            break
        bundle.append(best)
        cur = {c: res[(tuple(bundle), c)] for c in CASES}
        curve.append({"actions": list(bundle), **{c: cur[c] for c in CASES}})
    wall = time.perf_counter() - t0

    ref = {c: singles[((), c)] for c in CASES}
    single_rows = []
    for a, (cat, label) in CATALOGUE.items():
        row = {"key": a, "category": cat, "label": label, "cases": {}}
        for c in CASES:
            r = singles[((a,), c)]
            row["cases"][c] = None if r is None else {
                **r, "delta": r["mean"] - ref[c]["mean"], "aog_delta": r["aog_prob"] - ref[c]["aog_prob"]}
        single_rows.append(row)
    inter = []
    for (pair, c), r in pairs.items():
        a, b = pair
        ra, rb = singles[((a,), c)], singles[((b,), c)]
        if r is None or ra is None or rb is None:
            continue
        inter.append({"a": a, "b": b, "case": c,
                      "delta_pair": r["mean"] - ref[c]["mean"],
                      "interaction": (r["mean"] - ref[c]["mean"]) - ((ra["mean"] - ref[c]["mean"]) + (rb["mean"] - ref[c]["mean"]))})
    inter.sort(key=lambda x: x["interaction"])
    out = {"catalogue": {k: {"category": v[0], "label": v[1]} for k, v in CATALOGUE.items()}, "cases": CASES,
           "reference": ref, "singles": single_rows, "interactions": inter, "bundle": curve,
           "weights": weights, "wall_seconds": round(wall, 1)}
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"done in {wall:.0f}s")
    print(f"{'action':<40}" + "".join(f"{CASES[c]:>22}" for c in CASES))
    for row in single_rows:
        cells = "".join(
            f"{'infeasible':>22}" if row['cases'][c] is None else f"{row['cases'][c]['delta']:>+12,.0f} {100 * row['cases'][c]['aog_prob']:>6.1f}%  "
            for c in CASES)
        print(f"{row['label']:<36}{cells}")
    print("strongest complements / substitutes (interaction k$, negative = more than additive):")
    for x in inter[:4] + inter[-4:]:
        print(f"  {CATALOGUE[x['a']][1][:18]} + {CATALOGUE[x['b']][1][:18]}  [{CASES[x['case']]}]  {x['interaction']:+,.0f}")
    print("greedy bundle:")
    for step in curve:
        print("  " + (" + ".join(step["actions"]) or "(none)") + "  " + "  ".join(
            f"{CASES[c]} {step[c]['mean']:,.0f}/{100 * step[c]['aog_prob']:.1f}%" for c in CASES if step[c]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
