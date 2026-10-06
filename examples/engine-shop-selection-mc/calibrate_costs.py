#!/usr/bin/env python3
"""Choose a company's operating-cost coefficients so the trunk's load factors match 2024.

The fleet assignment picks aircraft by cost per seat, so the cost model decides how full the
flights run. The coefficients are no_source; they are chosen so the yearly version, solved at 2024
demand (the route data's year), gives each trunk route's load factor close to the 2024 market value
(MLIT, routes_trunk.json market_lf_2024):

  cost per block hour (k$) = base_737 x (seats / 165) ^ seat_exponent x premium (older types)

A grid over base_737 and seat_exponent; the score is the root mean square of (model - 2024) over the
routes. The best pair is written back to data/routes_trunk.json for that company (--write).

  python calibrate_costs.py ana [--write]
  python calibrate_costs.py fares [--write]   # route fare levels, both companies together

The route fare levels (fares): one multiplier per route on top of the distance taper, the same for
every company (they are market fares), found by coordinate descent (steps of 0.1, 0.5-1.8) on the sum
of both companies' load-factor RMSE; the average yield is kept. Written to fare_taper.route_adjust_fitted.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

import capacity_scenarios as cs
import fleet_from_demand as ffd
import route_fleet as rf

HERE = Path(__file__).resolve().parent
BASES = (2.5, 3.0, 3.5, 4.0, 4.5)
EXPONENTS = (0.5, 0.6, 0.7, 0.8, 0.9)


def costs(R: dict, cid: str, base: float, exponent: float) -> dict:
    prem = R["cost_model"].get("older_type_premium", {})
    return {t["type"]: round(base * (t["seats"] / 165) ** exponent * prem.get(t["type"], 1.0), 2) for t in rf.types_of(R, cid)}


def score(s: dict, R: dict, cid: str, base: float, exponent: float) -> dict:
    g = s["derived"]["demand_growth_per_year"]
    ctx, _ = ffd.trunk_context(cid, s["cfg"], s["rpk"], s["ac"], s["eng"], s["derived"], years_ahead=-2.25)   # back to 2024 demand
    ov = {t: {"cost_per_block_h_k": c} for t, c in costs(R, cid, base, exponent).items()}
    tr = rf.build(cid, s["D"], s["rpk"], ctx, quantiles=("p50",), detail=False, fiscal_years={"none"}, overrides=ov)
    lf = tr["version"]["lf"]
    target = {r["id"]: r["market_lf_2024"] for r in R["routes"]}
    err = [(lf[r] - target[r]) for r in target if lf.get(r) is not None]
    return {"base_737": base, "seat_exponent": exponent, "rmse": round(math.sqrt(sum(e * e for e in err) / len(err)), 4),
            "lf": {r: round(v, 3) if v is not None else None for r, v in lf.items()}, "target": target, "by_type": tr["version"]["by_type"],
            "growth_used": g}


def build(cid: str, write: bool = False, bases=BASES, exponents=EXPONENTS) -> dict:
    R = rf.load()
    s = cs.setup(cid)
    rows = [score(s, R, cid, b, e) for b, e in itertools.product(bases, exponents)]
    rows.sort(key=lambda x: x["rmse"])
    best = rows[0]
    cur = {t["type"]: t["cost_per_block_h_k"] for t in rf.types_of(R, cid)}
    out = {"company": cid, "best": best, "grid": rows, "current_costs": cur, "best_costs": costs(R, cid, best["base_737"], best["seat_exponent"])}
    if write:
        path = HERE / "data" / "routes_trunk.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data["companies"][cid]["types"]:
            t["cost_per_block_h_k"] = out["best_costs"][t["type"]]
        data["companies"][cid]["cost_calibration"] = {"base_737_k_per_block_h": best["base_737"], "seat_exponent": best["seat_exponent"], "rmse_lf_2024": best["rmse"],
                                                      "how": "calibrate_costs.py：2024 年の需要で解いた年次の版の路線ごとの搭乗率を、2024 年の座席利用率（国交省）に合わせる格子探索。no_source"}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def fit_fares(cids=("jal", "ana"), step: float = 0.1, lo: float = 0.5, hi: float = 1.8, passes: int = 4, write: bool = False) -> dict:
    import copy
    R0 = rf.load()
    S = {c: cs.setup(c) for c in cids}
    routes = [r["id"] for r in R0["routes"]]
    target = {r["id"]: r["market_lf_2024"] for r in R0["routes"]}
    cache = {}

    def lf(cid, adj):
        key = (cid, tuple(round(adj[r], 2) for r in routes))
        if key not in cache:
            R = copy.deepcopy(R0); R["fare_taper"]["route_adjust"] = adj
            orig = rf.load; rf.load = lambda: R
            try:
                s = S[cid]
                ctx, _ = ffd.trunk_context(cid, s["cfg"], s["rpk"], s["ac"], s["eng"], s["derived"], -2.25)
                cache[key] = rf.build(cid, s["D"], s["rpk"], ctx, quantiles=("p50",), detail=False, fiscal_years={"none"})["version"]["lf"]
            finally:
                rf.load = orig
        return cache[key]

    def rmse(cid, adj):
        l = lf(cid, adj)
        e = [l[r] - target[r] for r in routes if l.get(r) is not None]
        return math.sqrt(sum(x * x for x in e) / len(e))

    obj = lambda adj: sum(rmse(c, adj) for c in cids)  # noqa: E731
    adj = {r: 1.0 for r in routes}
    start = {c: round(rmse(c, adj), 4) for c in cids}
    best = obj(adj)
    for _ in range(passes):
        moved = False
        for r in routes:
            for d in (step, -step):
                while lo <= adj[r] + d <= hi:
                    cand = {**adj, r: round(adj[r] + d, 2)}
                    v = obj(cand)
                    if v < best - 1e-4:
                        adj, best, moved = cand, v, True
                    else:
                        break
        if not moved:
            break
    out = {"route_adjust": adj, "rmse_start": start, "rmse_fitted": {c: round(rmse(c, adj), 4) for c in cids},
           "lf_fitted": {c: {k: round(v, 3) for k, v in lf(c, adj).items()} for c in cids}, "target": target}
    if write:
        path = HERE / "data" / "routes_trunk.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fare_taper"]["route_adjust_fitted"] = adj
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("company")
    a.add_argument("--write", action="store_true")
    args = a.parse_args(argv)
    if args.company == "fares":
        r = fit_fares(write=args.write)
        print(json.dumps(r, ensure_ascii=False))
        return 0
    r = build(args.company, args.write)
    for x in r["grid"][:8]:
        print(f"base {x['base_737']} exp {x['seat_exponent']}: rmse {x['rmse']} lf {x['lf']} types {x['by_type']}")
    print("target", r["best"]["target"])
    print("current", r["current_costs"])
    print("best", r["best_costs"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
