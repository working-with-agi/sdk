#!/usr/bin/env python3
"""How far to raise fares when the hub's capacity is capped.

Under the cap the trunk cannot add flights, so the other lever is the fare. Each month's fleet
assignment (route_fleet.assign) also picks each route's fare as a multiple of today's (0.8 to 1.5,
step 0.05) to earn the most (revenue carried - operating cost - lease): a higher fare leaves fewer
passengers, so smaller aircraft can fly the same slots, and the spill falls (route_fleet.price).

Demand follows a linear curve through today's fare with an elasticity there (no_source; reference
values: about -0.8 when the whole market moves together, about -1.4 at the route level when the
rivals keep their fares -- InterVISTAS 2007 for IATA, not checked against the original here). A
constant elasticity is not used: with an inelastic market it raises fares without end.

  python fare_scenarios.py jal --out fleet/fares_jal.json

Compared with today's fares in the same year: the fare by route (weighted by passengers carried,
and in the busiest and quietest months), passengers, spill, revenue, operating cost and margin,
the aircraft each type flies, and the engines (a smaller gauge moves cycles between types).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import capacity_scenarios as cs

ELASTICITIES = (-0.8, -1.1, -1.4)
YEARS = (0, 3)
ENGINE_KEYS = ("type", "utilisation_multiplier", "windows", "spend_per_year_oku_yen")


def compare(base: dict, x: dict) -> dict:
    d = lambda k: round(x[k] - base[k], 1)
    return {"revenue_oku": d("revenue_oku"), "operating_cost_oku": d("operating_cost_oku"), "margin_oku": d("margin_oku"),
            "carried_pax_k": d("carried_pax_k"), "spill_pax_k": d("spill_pax_k")}


def build(cid: str, out: Path | None = None, elasticities: tuple = ELASTICITIES, years: tuple = YEARS, lift: int = 20, log=print) -> dict:
    s = cs.setup(cid)
    t0 = time.time()
    rows = []
    for k in years:
        base = cs.run(s, k)
        rows.append({"years_ahead": k, "fiscal_year": cs.fy_after(s["fy"], k), "elasticity": None, "lift": 0, **base, "vs_today_fares": None})
        for e in elasticities:
            x = cs.run(s, k, fares={"elasticity": e})
            rows.append({"years_ahead": k, "fiscal_year": cs.fy_after(s["fy"], k), "elasticity": e, "lift": 0, **x, "vs_today_fares": compare(base, x)})
            if log:
                log(f"  [{time.time() - t0:4.0f}s] FY+{k} e {e}: margin {compare(base, x)['margin_oku']:+} 億円")
    # does a fare rise stand in for slots? the hub +lift round trips at today's fares and with fares set
    k = max(years); e = -1.1
    base = next(r for r in rows if r["years_ahead"] == k and r["elasticity"] is None)
    lifted = cs.run(s, k, delta=lift)
    lifted_f = cs.run(s, k, delta=lift, fares={"elasticity": e})
    sub = {"years_ahead": k, "fiscal_year": cs.fy_after(s["fy"], k), "lift": lift, "elasticity": e,
           "slots_today_fares": compare(base, lifted), "slots_and_fares": compare(base, lifted_f),
           "fares_only": next(r["vs_today_fares"] for r in rows if r["years_ahead"] == k and r["elasticity"] == e),
           "fare_with_slots": lifted_f["fare"]["by_route"]}
    result = {"company": cid, "elasticities": list(elasticities), "rows": rows, "fares_vs_slots": sub,
              "assumptions": {"demand": "直線の需要曲線（今の運賃で弾力性 e）。no_source。参考：市場全体が一緒に動くと約 −0.8、他社が据え置くと路線で約 −1.4（InterVISTAS 2007、原典は未照合）",
                              "search": "月ごと・路線ごとに、今の運賃の 0.8〜1.5 倍（0.05 刻み）から、売上 − 運航費 − リース費 が最大になる運賃を座標ごとに探す。各候補で機材割当を解き直す",
                              "share": "便数の取り分は運賃で変えない（運賃の効き目は弾力性に入れる）",
                              "frequencies": "年次の版（便数）は今の運賃で決めたまま。羽田の枠を使う下限 98% は変わらない"},
              "note": "数値はすべて合成データ。p50"}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("company")
    a.add_argument("--out", type=Path)
    args = a.parse_args(argv)
    r = build(args.company, args.out)
    for x in r["rows"]:
        f = x["fare"]
        print(f"{x['fiscal_year']} e {x['elasticity']}: carried {x['carried_pax_k']} spill {x['spill_pax_k']} rev {x['revenue_oku']} op {x['operating_cost_oku']} margin {x['margin_oku']} vs {x['vs_today_fares']}")
        print(f"    used {x['aircraft_used_avg']} lf {x['lf_avg']}")
        if f:
            print(f"    fare {f['by_route']} busy {f['busiest_3_months']} quiet {f['quietest_3_months']}")
        print("    engines", [{k: e.get(k) for k in ENGINE_KEYS} for e in x["engines"] if e["type"] in ("737", "767", "787")])
    print("fares vs slots", r["fares_vs_slots"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
