#!/usr/bin/env python3
"""Which answer holds under which conditions? Sweep the parameters nobody can pin down,
let the optimiser pick the levers in every combination, then classify the answers and
extract the thresholds where the best course of action changes.

Uncertain parameters (full factorial, 108 combinations by default):
  value        value of one 737-800 aircraft-month to the network (scales the
               cancellation tiers): x0.5 / x1 / x2 -- it comes from fleet assignment,
               which is a separate optimisation problem
  substitute   other fleets can fly missing capacity: none / available
  backlog      extra TAT at external shops (MRO congestion): +0 / +1 / +2 months
  llp          LLP kit supply: normal (8 on hand, 8 months) / crunch (4, 12 months)
  midlife      net price of a mid-life engine swap: 2,600 / 5,000 / 7,500 k$

Levers the optimiser may use in every combination: shop and workscope choice, timing,
expedite, extra long-term spares, emergency LLP kits, mid-life engine swaps (up to 8).
Company requirements kept: budget, shelf buffer, contracted volume.

  python explore.py                   # writes explore.json (+ explore.html)
  python explore.py --workers 8
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

import numpy as np

from shop_mc import Requirements, evaluate, load, sample, solve_saa
from shop_mc.model import InfeasibleError

from levers import apply

HERE = Path(__file__).resolve().parent

FACTORS = {
    "value": [0.5, 1.0, 2.0],
    "substitute": [0, 1],
    "backlog": [0, 1, 2],
    "llp": [0, 1],
    "midlife": [2600, 5000, 7500],
}
LABELS = {
    "value": "1機・1か月の価値（倍率）",
    "substitute": "別機種での代替",
    "backlog": "外部工場の TAT 延び（月）",
    "llp": "LLP 逼迫",
    "midlife": "中寿命エンジン正味価格（k$）",
}
REQ = dict(budget=True, buffer=True, volume=True, kits_on_hand_only=False, no_new_spares=False, service=False)


def build(p, f):
    p = apply(p, ("midlife", 8))
    p = dataclasses.replace(p, shops=[
        dataclasses.replace(k, quotes={"GT": dataclasses.replace(k.quotes["GT"], price=float(f["midlife"]))})
        if k.id == "MIDLIFE" else k for k in p.shops])
    p = dataclasses.replace(p, aog_tiers=[(cap, c * f["value"]) for cap, c in p.aog_tiers])
    if f["substitute"]:
        # substitution stays cheaper than cancelling: scale its cost down with the value
        p = apply(p, ("substitute", 450 * min(1.0, f["value"])))
    if f["backlog"]:
        p = dataclasses.replace(p, shops=[
            dataclasses.replace(k, quotes={w: dataclasses.replace(q, tat=q.tat + f["backlog"]) for w, q in k.quotes.items()})
            if k.transport_months > 0 else k for k in p.shops])
    if f["llp"]:
        p = dataclasses.replace(p, llp_kit_lead_months=12, llp_kits_on_hand=4)
    return p


def job(args):
    f, fleet, shops, n, seed, time_limit, n_eval = args
    p = build(load(fleet, shops), f)
    t0 = time.perf_counter()
    try:
        plan = solve_saa(p, sample(p, n, seed), req=Requirements(**REQ), time_limit=time_limit, threads=1)
    except InfeasibleError:
        return {"f": f, "feasible": False}
    ev = evaluate(p, plan, sample(p, n_eval, seed + 999))
    sc = sample(p, 1, seed)
    chosen = [sc.options[i] for i in plan.chosen]
    ext = sum(1 for o in chosen if o.shop.transport_months > 0 and o.shop.id != "MIDLIFE")
    return {
        "f": f, "feasible": True, "status": plan.status, "seconds": round(time.perf_counter() - t0, 1),
        "mean": ev.mean, "p90": ev.p90, "aog_prob": ev.aog_prob,
        "lease": ev.lease_engine_months,
        "spares": plan.long_spares, "kits": plan.emergency_kits,
        "swaps": sum(1 for o in chosen if o.workscope == "GT"),
        "rush": sum(1 for o in chosen if o.rush),
        "early_months": sum(o.visit.latest - o.month for o in chosen),
        "external_share": ext / max(1, len(chosen)),
        "full_visits": sum(1 for o in chosen if o.workscope == "FULL"),
    }


def pattern(r) -> str:
    if not r["feasible"]:
        return "実行可能な計画なし"
    parts = []
    if r["swaps"] >= 6:
        parts.append("中寿命エンジン中心")
    elif r["swaps"] >= 1:
        parts.append("中寿命エンジン併用")
    if r["spares"] >= 1:
        parts.append("予備を追加")
    if r["kits"] >= 1:
        parts.append("キット緊急調達")
    if not parts:
        parts.append("工場整備のみ")
    return "＋".join(parts)


def rules(results):
    """Shallow decision tree: parameters -> pattern, printed as if-then rules."""
    from sklearn.tree import DecisionTreeClassifier, _tree

    keys = list(FACTORS)
    X = np.array([[r["f"][k] for k in keys] for r in results], dtype=float)
    y = [r["pattern"] for r in results]
    tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=4, random_state=0).fit(X, y)
    t = tree.tree_
    out = []

    def walk(node, conds):
        if t.feature[node] == _tree.TREE_UNDEFINED:
            counts = t.value[node][0]
            k = int(np.argmax(counts))
            out.append({
                "if": conds, "then": tree.classes_[k],
                "purity": float(counts[k] / counts.sum()), "n": int(t.n_node_samples[node]),
            })
            return
        name, thr = keys[t.feature[node]], t.threshold[node]
        walk(t.children_left[node], conds + [(name, "<=", float(thr))])
        walk(t.children_right[node], conds + [(name, ">", float(thr))])

    walk(0, [])
    return out, float(tree.score(X, y))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--scenarios", type=int, default=40)
    ap.add_argument("--eval-scenarios", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=int, default=120)
    ap.add_argument("--json-out", type=Path, default=Path("explore.json"))
    args = ap.parse_args(argv)

    combos = [dict(zip(FACTORS, v)) for v in itertools.product(*FACTORS.values())]
    jobs = [(f, str(args.fleet), str(args.shops), args.scenarios, args.seed, args.time_limit, args.eval_scenarios) for f in combos]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(job, jobs))
    wall = time.perf_counter() - t0
    for r in results:
        r["pattern"] = pattern(r)
    rule_list, fit = rules(results)

    # robustness: for each pattern's most common decision profile, how often is the chosen
    # pattern within 3 % of the best cost? (answers "which course never goes badly wrong")
    patterns = {}
    for r in results:
        patterns.setdefault(r["pattern"], []).append(r)
    summary = [
        {"pattern": k, "count": len(v),
         "mean_cost": float(np.mean([x["mean"] for x in v if x["feasible"]])) if any(x["feasible"] for x in v) else None,
         "mean_aog": float(np.mean([x["aog_prob"] for x in v if x["feasible"]])) if any(x["feasible"] for x in v) else None}
        for k, v in sorted(patterns.items(), key=lambda kv: -len(kv[1]))
    ]
    # marginal effect of each factor level on the chosen levers
    effects = {}
    for k, levels in FACTORS.items():
        effects[k] = []
        for lv in levels:
            sub = [r for r in results if r["f"][k] == lv and r["feasible"]]
            effects[k].append({
                "level": lv, "n": len(sub),
                "swaps": float(np.mean([r["swaps"] for r in sub])) if sub else None,
                "spares": float(np.mean([r["spares"] for r in sub])) if sub else None,
                "kits": float(np.mean([r["kits"] for r in sub])) if sub else None,
                "aog": float(np.mean([r["aog_prob"] for r in sub])) if sub else None,
                "cost": float(np.mean([r["mean"] for r in sub])) if sub else None,
            })
    out = {"factors": FACTORS, "labels": LABELS, "wall_seconds": round(wall, 1), "runs": results,
           "patterns": summary, "rules": rule_list, "rule_fit": fit, "effects": effects}
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(jobs)} combinations solved in parallel: {wall:.0f}s")
    print("patterns:")
    for s in summary:
        print(f"  {s['pattern']:<28} {s['count']:>3}  cost {s['mean_cost'] or 0:>10,.0f}  AOG {100 * (s['mean_aog'] or 0):.1f}%")
    print(f"rules (tree accuracy {fit:.0%}):")
    for r in rule_list:
        cond = " かつ ".join(f"{LABELS[k]} {op} {v:g}" for k, op, v in r["if"])
        print(f"  もし {cond} → {r['then']}  ({r['n']} 件, 一致 {r['purity']:.0%})")
    print("effects (mean chosen levers by level):")
    for k, rows in effects.items():
        print(f"  {LABELS[k]}: " + "  ".join(
            f"{r['level']}: 中寿命{r['swaps']:.1f} 予備{r['spares']:.1f} キット{r['kits']:.1f} 欠航{100 * r['aog']:.1f}%"
            for r in rows if r["n"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
