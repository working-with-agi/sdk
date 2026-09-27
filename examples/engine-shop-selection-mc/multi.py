#!/usr/bin/env python3
"""Plan several fleets of one company together.

Each fleet (737-800 / CFM56-7B, 787 / GEnx or Trent, 767 / CF6) has its own engines, shop
contract, spares and lead times, so its plan is solved on its own (baseline.py freeze).
What the fleets share is the company's money and its attention:

  1. budget: the fiscal-year budget is one pot. For every fleet the base plan is re-solved
     at a few budget levels (tighter / as is / looser) to get its cost-of-money curve; the
     company then splits the pot where the marginal value is highest (enumeration over the
     grid, objective = expected cost + expected AOG cost, subject to the pot).
  2. landing: the fiscal-year landing of all fleets added up, with its 10-90 % range
     (fleets are independent draws) and the chance of exceeding the company budget.
  3. decisions: the deadlines of all fleets by month, so the meeting sees its load.

  python multi.py jal --out multi/jal.json

All numbers are synthetic; the other fleets' assumptions carry no_source in companies.json.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

import baseline

HERE = Path(__file__).resolve().parent
LEVELS = (0.9, 1.0, 1.1)          # budget multipliers tried per fleet
AOG_COST_K = 900                  # k$ per AOG-engine-month, used to price the AOG probability (assumption)
AOG_MONTHS = 3                    # an AOG episode is priced as three engine-months short (assumption)


def fleets_of(cid: str) -> list[dict]:
    conf = json.loads((HERE / "data" / "companies.json").read_text(encoding="utf-8"))
    c = conf["companies"][cid]
    out = [{"key": "737", "type": "737-800", "engine": "CFM56-7B", "fleet": HERE / "data" / cid / "fleet.json",
            "shops": HERE / "data" / cid / "shops.json", "baseline": HERE / "baselines" / f"{cid}-2026-10.json"}]
    for f in c.get("fleets", []):
        out.append({"key": f["type"], "type": f["type"], "engine": f["engine"], "fleet": HERE / "data" / cid / f["type"] / "fleet.json",
                    "shops": HERE / "data" / cid / f["type"] / "shops.json", "baseline": HERE / "baselines" / f"{cid}-{f['type']}-2026-10.json"})
    return out


def solve_at(fleet_path: Path, shops_path: Path, mult: float, tmp: Path, scenarios: int, seed: int, time_limit: int):
    """The base plan with every fiscal-year budget scaled by mult; None if infeasible even
    after relaxing the budget (then the budget is not the binding constraint)."""
    f = json.loads(fleet_path.read_text(encoding="utf-8"))
    f["budget"]["by_fiscal_year"] = {fy: round(v * mult, -2) for fy, v in f["budget"]["by_fiscal_year"].items()}
    fp = tmp / f"fleet_{mult:.2f}.json"
    fp.write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
    _a, _c, summ, rows = baseline.solve_summary(((), "base", str(fp), str(shops_path), scenarios, seed, 800, time_limit, ("budget",)))
    if summ is None:
        return None
    return {"mult": mult, "budget": f["budget"]["by_fiscal_year"], "cost": summ["total_cost"], "aog_prob": summ["aog_prob"],
            "relaxed": summ.get("relaxed", []), "visits": len(rows), "spend_by_fy": summ.get("by_fiscal_year", {})}


def allocate(curves: dict, pot: dict) -> dict:
    """Pick one level per fleet: min total expected cost + AOG cost, total budget <= pot."""
    keys = list(curves)
    best = None
    for combo in itertools.product(*[range(len(curves[k])) for k in keys]):
        pts = [curves[k][i] for k, i in zip(keys, combo)]
        if any(p is None for p in pts):
            continue
        used = {fy: sum(p["budget"].get(fy, 0) for p in pts) for fy in pot}
        over = sum(max(0.0, used[fy] - pot[fy]) for fy in pot)
        obj = sum(p["cost"] + p["aog_prob"] * AOG_COST_K * AOG_MONTHS for p in pts) + over * 10  # over the pot: heavily penalised
        if best is None or obj < best["objective"]:
            best = {"objective": obj, "levels": {k: curves[k][i]["mult"] for k, i in zip(keys, combo)},
                    "used": used, "over_pot": over, "cost": sum(p["cost"] for p in pts),
                    "aog": {k: curves[k][i]["aog_prob"] for k, i in zip(keys, combo)}}
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--scenarios", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=int, default=60)
    ap.add_argument("--no-curves", action="store_true", help="skip the budget re-solves (landing and deadlines only)")
    args = ap.parse_args(argv)
    cid = args.company
    fl = [f for f in fleets_of(cid) if f["baseline"].exists()]
    if not fl:
        print("no frozen baselines; run baseline.py freeze for each fleet first"); return 1
    B = {f["key"]: json.loads(f["baseline"].read_text(encoding="utf-8")) for f in fl}
    fys = sorted({fy for b in B.values() for fy in b["budgets"]})
    pot = {fy: sum(b["budgets"].get(fy, 0) for b in B.values()) for fy in fys}

    # 1. per-fleet summary and 2. combined landing (independent draws per fleet)
    rng = np.random.default_rng(args.seed)
    draws = 4000
    landing = {fy: np.zeros(draws) for fy in fys}
    per = {}
    for f in fl:
        b = B[f["key"]]
        pr = b["plan_of_record"]
        by_fy = pr["by_fiscal_year"]
        # spread of the fleet's 2-year cost from its evaluation (p10/p90 if recorded, else +-12 %)
        spread = pr.get("p90", pr["total_cost"] * 1.12) - pr.get("p10", pr["total_cost"] * 0.88)
        sd = max(1.0, spread / 2.56)
        for fy in fys:
            s = by_fy.get(fy, {}).get("spend", 0.0)
            landing[fy] += rng.normal(s, sd * (s / max(1.0, pr["total_cost"])), draws)
        per[f["key"]] = {"type": f["type"], "engine": f["engine"], "name": b["company"]["name"],
                         "visits": len(b["plan"]), "total_cost": pr["total_cost"], "aog_prob": pr["aog_prob"],
                         "relaxed": pr.get("relaxed", []), "budgets": b["budgets"],
                         "by_fy": {fy: by_fy.get(fy, {"visits": 0, "spend": 0.0}) for fy in fys},
                         "norms": {k: b["norms"][k] for k in ("visits_per_year", "spend_per_year_k", "usd_per_efh")},
                         "months": {"labels": b["monthly"]["labels"], "plan_visits": b["monthly"]["plan_visits"],
                                    "plan_spend": b["monthly"]["plan_spend"], "shop_load": b["monthly"].get("shop_load"),
                                    "shop_slots": b["monthly"].get("shop_slots"),
                                    "deadlines": [sum(1 for r in b["plan"] if r["deadline_t"] == t) for t in range(len(b["monthly"]["labels"]))],
                                    "margin": [b["monthly"]["serviceable"][t] - b["monthly"]["required"][t] - b["monthly"]["buffer"][t]
                                               for t in range(len(b["monthly"]["labels"]))]}}
    comb = {}
    for fy in fys:
        x = landing[fy]
        comb[fy] = {"budget": pot[fy], "plan": float(sum(per[k]["by_fy"][fy]["spend"] for k in per)),
                    "p10": float(np.percentile(x, 10)), "p50": float(np.percentile(x, 50)), "p80": float(np.percentile(x, 80)),
                    "p90": float(np.percentile(x, 90)), "p_over": float((x > pot[fy]).mean()) if pot[fy] else 0.0,
                    "contingency_p80": float(max(0.0, np.percentile(x, 80) - pot[fy]))}
    labels = per[fl[0]["key"]]["months"]["labels"]
    deadlines = {k: per[k]["months"]["deadlines"] for k in per}

    # 3. the budget curves and the split of the pot
    curves, alloc = {}, None
    if not args.no_curves:
        with tempfile.TemporaryDirectory() as tmpd:
            tmp = Path(tmpd)
            for f in fl:
                curves[f["key"]] = [solve_at(f["fleet"], f["shops"], m, tmp, args.scenarios, args.seed, args.time_limit) for m in LEVELS]
                print(f"{cid} {f['key']}: " + ", ".join(f"x{m}: {'-' if c is None else f'{c[chr(99)+chr(111)+chr(115)+chr(116)]:,.0f} k$ / AOG {c[chr(97)+chr(111)+chr(103)+chr(95)+chr(112)+chr(114)+chr(111)+chr(98)]:.1%}'}" for m, c in zip(LEVELS, curves[f["key"]])))
        alloc = allocate(curves, pot)

    out = {"company": cid, "fleets": per, "fiscal_years": fys, "pot": pot, "landing": comb, "labels": labels,
           "deadlines_by_fleet": deadlines, "deadlines_total": [sum(d[t] for d in deadlines.values()) for t in range(len(labels))],
           "curves": curves, "allocation": alloc,
           "settings": {"levels": LEVELS, "aog_cost_k": AOG_COST_K, "aog_months": AOG_MONTHS, "scenarios": args.scenarios},
           "note": "合成データ。737-800 以外の機種の前提は出典なし（companies.json の fleets）。機種ごとに解き、予算の配分だけ会社全体で決める。"}
    out_path = args.out or HERE / "multi" / f"{cid}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"{cid}: {len(per)} fleets, pot " + ", ".join(f"{fy} {v / 1000:,.1f} M$" for fy, v in pot.items())
          + " | landing " + ", ".join(f"{fy} p50 {c['p50'] / 1000:,.1f} p_over {c['p_over']:.0%}" for fy, c in comb.items()))
    if alloc:
        print("  split: " + ", ".join(f"{k} x{m}" for k, m in alloc["levels"].items()) + f", cost {alloc['cost']:,.0f} k$, over pot {alloc['over_pot']:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
