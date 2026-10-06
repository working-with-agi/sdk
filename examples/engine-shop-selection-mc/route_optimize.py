#!/usr/bin/env python3
"""Where to add capacity, and to whom: the government's choice solved as an optimization.

The upper level (government and airports) chooses, for each trunk route grown (New Chitose,
Fukuoka, Naha), how many round trips a day to add for company A and for company B (0, 2 or 4
each; the other carriers get enough to keep the two companies' combined share). The lower level
is each company's own fleet assignment (route_fleet, a mixed-integer program), which answers
with its fleet, its fares unchanged. The upper level is solved by enumerating the whole grid
(3 routes x 3 x 3 = 729 plans), so the best plan on the grid is exact for each objective:

  welfare      the passengers' surplus on the new passengers (fare x surplus share; with a linear
               demand curve through today's fare at elasticity e the average surplus of a passenger
               is fare / (2|e|): 0.45 at e = -1.1, sensitivity 0.25 / 0.70) + both companies' change
               in margin - the airport capacity's annual cost (capital / 30-year annuity at 4 %)
  welfare_ok   the same, but only plans where neither company loses (both margins >= today's)
  joint        both companies' margins together
  a, b         one company's margin
  pax_per_cost the airport's ratio: new passengers per 100 million yen of capital (the greedy
               order of route_growth.py)

New passengers: on a grown route, (A's + B's change) / the two companies' combined share (the
other carriers grow in proportion); on other routes, A's + B's change (aircraft that moved).

  python route_optimize.py --world before --fares distance      # one grid, fleet/route_opt/...
  python route_optimize.py --summary                             # fleet/route_opt_jal.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import airport_slots as ap
import capacity_scenarios as cs
import carbon_scenarios as cb
import investment_scenarios as inv
import route_fleet as rf
import route_growth as rg

HERE = Path(__file__).resolve().parent
OUT = HERE / "fleet" / "route_opt"
LEVELS = (0, 2, 4)
CIDS = ("jal", "ana")
SURPLUS = {"low": 0.25, "mid": 0.45, "high": 0.70}
WORLDS = ("before", "after_66_rule")
FARES = ("distance", "fitted")


def grid(world: str, fares: str, years_ahead: int = 3, log=print) -> dict:
    rf.FARE_MODE = fares
    t0 = time.time()
    SS = {c: cs.setup(c) for c in CIDS}
    S = ap.load()
    K = cb.load()
    unit = inv.unit_costs(inv.load())
    mid = {k: (sum(v) / 2 if v and v[0] is not None else None) for k, v in unit.items()}
    cur = {c: ap.current_freq(S, c) for c in CIDS}
    oth = ap.others_freq(S)
    big = {r: cur["jal"][r] + cur["ana"][r] for r in oth}
    s_ab = {r: big[r] / (big[r] + oth[r]) for r in oth}
    W = {c: rg.world_of(S, c, world) for c in CIDS}
    free = {c: rg.solve(SS[c], S, W[c], {}, {}, years_ahead, K) for c in CIDS}
    lock = {c: {r: free[c]["round_trips"][r] for r in ap.HUB_ROUTES} for c in CIDS}
    base = {c: rg.solve(SS[c], S, W[c], {}, {}, years_ahead, K, lock[c]) for c in CIDS}      # today's plan with the round trips held: the reference every plan is compared with
    fare = rf.fare_yen(rf.load(), SS["jal"]["D"]["companies"]["jal"]["yield_yen_per_rpk"])
    ann = inv.annuity(0.04, 30)
    rows = []
    plans = list(itertools.product(LEVELS, repeat=2 * len(rg.GROW)))
    for k, plan in enumerate(plans):
        add = {"jal": {}, "ana": {}}
        for i, code in enumerate(rg.GROW):
            a, b = plan[2 * i], plan[2 * i + 1]
            if a:
                add["jal"][code] = a
            if b:
                add["ana"][code] = b
        others = {rg.ROUTE[code]: (plan[2 * i] + plan[2 * i + 1]) * oth[rg.ROUTE[code]] / big[rg.ROUTE[code]] for i, code in enumerate(rg.GROW)}
        x = {}
        for c, o in (("jal", "ana"), ("ana", "jal")):
            rv = {r: v for r, v in others.items() if v}
            for code, n in add[o].items():
                rv[rg.ROUTE[code]] = rv.get(rg.ROUTE[code], 0) + n
            x[c] = rg.solve(SS[c], S, W[c], add[c], rv, years_ahead, K, lock[c])
        grown = {rg.ROUTE[code] for code in rg.GROW if add["jal"].get(code) or add["ana"].get(code)}
        new = {}
        for r in base["jal"]["carried_by_route_pax_k"]:
            d = sum(x[c]["carried_by_route_pax_k"][r] - base[c]["carried_by_route_pax_k"][r] for c in CIDS)
            new[r] = d / s_ab[r] if r in grown else d
        trips = {code: plan[2 * i] + plan[2 * i + 1] + others[rg.ROUTE[code]] for i, code in enumerate(rg.GROW)}
        capital = sum(t * (mid["HND"] + mid[code]) for code, t in trips.items())
        dm = {c: x[c]["margin_oku"] - base[c]["margin_oku"] for c in CIDS}
        value = sum(new[r] * 1e3 * fare[r] for r in new) / 1e8                         # oku: new passengers x fare
        rows.append({"plan": {"jal": add["jal"], "ana": add["ana"]}, "market_round_trips": {k2: round(v, 2) for k2, v in trips.items()},
                     "capital_oku": round(capital, 1), "annual_cost_oku": round(capital / ann, 2), "new_pax_k": round(sum(new.values()), 1),
                     "new_pax_by_route_k": {r: round(v, 1) for r, v in new.items()}, "fare_value_oku": round(value, 2),
                     "margin_change_oku": {c: round(v, 1) for c, v in dm.items()},
                     "aircraft": {c: rg.diff(base[c], x[c]) for c in CIDS}})
        if log and k % 50 == 0:
            log(f"  [{time.time() - t0:5.0f}s] {world}/{fares} {k}/{len(plans)}")
    out = {"world": world, "fares": fares, "annuity": round(ann, 2), "share_two_companies": {r: round(v, 3) for r, v in s_ab.items()},
           "fare_yen": {r: round(v) for r, v in fare.items()}, "airport_cost_mid_oku_per_round_trip_day": mid,
           "base": {c: {k2: base[c][k2] for k2 in ("margin_oku", "carried_pax_k", "round_trips", "aircraft_used_avg", "co2_kt", "engines")} for c in CIDS},
           "rows": rows, "elapsed_s": round(time.time() - t0, 1)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{world}_{fares}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def score(row: dict, surplus: float) -> dict:
    dm = row["margin_change_oku"]
    w = surplus * row["fare_value_oku"] + dm["jal"] + dm["ana"] - row["annual_cost_oku"]
    return {"welfare": w, "joint": dm["jal"] + dm["ana"], "a": dm["jal"], "b": dm["ana"],
            "pax_per_cost": (row["new_pax_k"] / row["capital_oku"]) if row["capital_oku"] else 0.0}


def brief(row: dict, surplus: float = SURPLUS["mid"]) -> dict:
    sc = score(row, surplus)
    a = row["aircraft"]
    return {"plan": row["plan"], "market_round_trips": row["market_round_trips"], "capital_oku": row["capital_oku"], "annual_cost_oku": row["annual_cost_oku"],
            "new_pax_k": row["new_pax_k"], "margin_change_oku": row["margin_change_oku"], "welfare_oku": round(sc["welfare"], 1),
            "aircraft_used": {c: a[c]["aircraft_used_avg"] for c in CIDS},
            "engines": {c: {t: e for t, e in a[c]["engines"].items() if e["utilisation_multiplier"] or e["spend_oku"]} for c in CIDS},
            "co2_kt": {c: a[c]["co2_kt"] for c in CIDS}}


def summarize(out: Path | None = None) -> dict:
    res = {}
    for world in WORLDS:
        for fares in FARES:
            p = OUT / f"{world}_{fares}.json"
            if not p.exists():
                continue
            g = json.loads(p.read_text(encoding="utf-8"))
            rows = g["rows"]
            for r in rows:                                                     # engine types with no engine data in the base (company B's 737) carry no change
                for c in CIDS:
                    r["aircraft"][c]["engines"] = {t: e for t, e in r["aircraft"][c]["engines"].items() if g["base"][c]["engines"].get(t, {}).get("utilisation_multiplier") is not None}
            best = {}
            for name, s in SURPLUS.items():
                ok = [r for r in rows if r["margin_change_oku"]["jal"] >= 0 and r["margin_change_oku"]["ana"] >= 0]
                best[f"welfare_{name}"] = brief(max(rows, key=lambda r: score(r, s)["welfare"]), s)
                best[f"welfare_ok_{name}"] = brief(max(ok, key=lambda r: score(r, s)["welfare"]), s) if ok else None
            for obj in ("joint", "a", "b", "pax_per_cost"):
                best[obj] = brief(max(rows, key=lambda r: score(r, SURPLUS["mid"])[obj]))
            top = sorted(rows, key=lambda r: -score(r, SURPLUS["mid"])["welfare"])[:5]
            nothing = next(r for r in rows if not r["plan"]["jal"] and not r["plan"]["ana"])
            res[f"{world}/{fares}"] = {"best": best, "top5_welfare_mid": [brief(r) for r in top], "do_nothing": brief(nothing), "n_plans": len(rows),
                                       "n_no_one_loses": sum(1 for r in rows if r["margin_change_oku"]["jal"] >= 0 and r["margin_change_oku"]["ana"] >= 0),
                                       "fare_yen": g["fare_yen"], "annuity": g["annuity"]}
    d = {"results": res, "surplus_shares": SURPLUS,
         "how": "上の段（政府・空港）が、新千歳・福岡・那覇のそれぞれで会社 A と会社 B に足す往復（0・2・4、他の航空会社は両社の合計の取り分を保つ分）を選び、下の段（各社）が自社の機材割当（混合整数計画）で応じる。上の段は 729 通りをすべて解いて、目的ごとの最良を出す（格子の上では厳密）。welfare ＝ 新しい旅客の利用者の得（運賃 × 割合。今の運賃を通る直線の需要で弾力性 e なら平均 1/(2|e|)、e=−1.1 で 0.45、感度 0.25・0.70）＋ 両社の差し引きの変化 − 空港の容量の年の費用（事業費 ÷ 30 年・4% の年金現価係数）。welfare_ok はどちらの会社も今より損をしない計画に限る。joint は両社の差し引きの合計。pax_per_cost は 1 億円あたりの新しい旅客（route_growth.py の順番の物差し）",
         "caveat": "他の航空会社の差し引きと機材は数えていない（新しい旅客の利用者の得には入る）。空港の着陸料などの収入、乗れなかった旅客の振り替え、需要の誘発は入れていない。下の段の解は月ごとの解の許容誤差（0.2%）を持つので、差の小さい計画の順位は確かではない。両社の解は相手の便数を与えたときの最適で、同時の均衡ではない"}
    out = out or HERE / "fleet" / "route_opt_jal.json"
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--world", choices=WORLDS)
    a.add_argument("--fares", choices=FARES, default="distance")
    a.add_argument("--summary", action="store_true")
    args = a.parse_args(argv)
    if args.summary:
        summarize()
        return 0
    grid(args.world, args.fares)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
