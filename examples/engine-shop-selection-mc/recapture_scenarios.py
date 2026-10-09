#!/usr/bin/env python3
"""The passengers a full flight turns away are not all lost: some take another flight of the same
company on the same route (the same day, the days around). The numbers that counted every one of
them as lost, restated with a share who rebook (route_fleet.RECAPTURE).

Two ways (route_fleet.RECAPTURE_MODE):
  expost    the fleet plan as it is (planned as if every turned-away passenger is lost); the share
            who rebook fill the route's empty seats that month, up to 95 % (no_source). The fleet,
            the engines and the load factor targets do not move: this restates the lost revenue.
  optimize  the plan counts on the recapture (sensitivity): it then flies smaller aircraft and the
            load factors rise above the 2024 values the costs were fitted to.

Rates: 0.15 (a published case for a carrier with few frequencies, JAIRM 2014; a constant recapture
rate in itinerary-based fleet assignment, Barnhart et al. 2002), 0.3 / 0.5 / 0.7 (no_source: the
trunk routes fly 12-20 round trips a day, so more rebook than in that case).

What is restated (company A unless said, p50):
  years       FY2027-FY2032 under today's Haneda slots: passengers turned away, recaptured, lost revenue
  august      FY2027 August, by route
  trunk       FY2027: load factors against 2024, each type's share of the trunk flights, the 737 and
              767 engines (utilisation multiplier, shop visits pulled earlier)
  expansion   Haneda +20 round trips (destinations as they are / New Chitose and Fukuoka +4), FY2030
  market      the same capacity for the market: company A and company B, each +10 (expansion) or
              one +5 and the other -5 (the 2028 reallocation), each answering the other's flights
  linear      the Linear slot game (company A and B, the air keeps 66 / 46 / 22 %) and the allocation
              rule's gain and loss

  python recapture_scenarios.py      # fleet/recapture_jal.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import airport_slots as ap
import capacity_scenarios as cs
import corridor_scenarios as cor
import route_fleet as rf

HERE = Path(__file__).resolve().parent
RATES = (0.0, 0.15, 0.3, 0.5, 0.7)
KEY = (0.0, 0.5)
ENG = ("737", "767", "787")


def eng(r: dict) -> dict:
    return {e["type"]: {"utilisation_multiplier": e.get("utilisation_multiplier"), "earlier": (e.get("windows") or {}).get("earlier"),
                        "due_new": (e.get("windows") or {}).get("due_new"), "mean_shift_months": (e.get("windows") or {}).get("mean_shift_months"),
                        "spend_per_year_oku_yen": e.get("spend_per_year_oku_yen")} for e in r["engines"] if e["type"] in ENG}


def brief(r: dict) -> dict:
    return {k: r[k] for k in ("fiscal_year", "demand_pax_k", "carried_pax_k", "spill_pax_k", "recaptured_pax_k", "revenue_oku", "lost_revenue_oku", "margin_oku")}


def added(r: dict, base: dict) -> dict:
    return {k: v - base["version_round_trips"].get(k, 0) for k, v in r["version_round_trips"].items() if k in ap.HUB_ROUTES}


def pair(S: dict, years: int, da: float, db: float, extra: dict | None = None) -> dict:
    """Company A gets da round trips, company B db; each answers the other's added flights (one pass)."""
    a0 = cs.run(S["jal"], years, dest=extra or True, windows=False)
    b0 = cs.run(S["ana"], years, dest=extra or True, windows=False)
    a1 = cs.run(S["jal"], years, delta=da, dest=extra or True, windows=False)
    b1 = cs.run(S["ana"], years, delta=db, dest=extra or True, windows=False, corridor={"rival_shift": added(a1, a0)})
    a2 = cs.run(S["jal"], years, delta=da, dest=extra or True, windows=True, corridor={"rival_shift": added(b1, b0)})
    b2 = cs.run(S["ana"], years, delta=db, dest=extra or True, windows=True, corridor={"rival_shift": added(a2, a0)})
    a0w = cs.run(S["jal"], years, dest=extra or True, windows=True); b0w = cs.run(S["ana"], years, dest=extra or True, windows=True)
    out = {"a": {"margin_change_oku": round(a2["margin_oku"] - a0["margin_oku"], 1), "lost_revenue_oku": a2["lost_revenue_oku"], "carried_change_pax_k": round(a2["carried_pax_k"] - a0["carried_pax_k"], 1),
                 "round_trips": a2["version_round_trips"], "engines": eng(a2), "engines_base": eng(a0w)},
           "b": {"margin_change_oku": round(b2["margin_oku"] - b0["margin_oku"], 1), "lost_revenue_oku": b2["lost_revenue_oku"], "carried_change_pax_k": round(b2["carried_pax_k"] - b0["carried_pax_k"], 1),
                 "round_trips": b2["version_round_trips"], "engines": eng(b2), "engines_base": eng(b0w)}}
    out["market_margin_change_oku"] = round(out["a"]["margin_change_oku"] + out["b"]["margin_change_oku"], 1)
    out["market_carried_change_pax_k"] = round(out["a"]["carried_change_pax_k"] + out["b"]["carried_change_pax_k"], 1)
    return out


def build(out: Path | None = None, log=print) -> dict:
    t0 = time.time()
    S = {c: cs.setup(c) for c in ("jal", "ana")}
    s = S["jal"]
    R = rf.load()
    lf24 = {r["id"]: r["market_lf_2024"] for r in R["routes"]}
    res = {"rates": list(RATES), "years": {}, "august": {}, "trunk": {}, "optimize": {}, "expansion": {}, "market": {}, "linear": {}}
    old = (rf.RECAPTURE, rf.RECAPTURE_MODE)
    try:
        rf.RECAPTURE_MODE = "expost"
        for v in RATES:
            rf.RECAPTURE = v
            ys = [cs.run(s, k, windows=(k == 0)) for k in range(6)]
            res["years"][str(v)] = [brief(y) for y in ys]
            m = next(x for x in ys[0]["by_month"] if x["label"].endswith("-08"))
            res["august"][str(v)] = m
            res.setdefault("months", {})[str(v)] = [{k: x[k] for k in ("label", "spill_pax_k", "lost_revenue_oku", "recaptured_pax_k")} for x in ys[0]["by_month"]]
            if v in KEY:
                res["trunk"][str(v)] = {"lf_avg": ys[0]["lf_avg"], "lf_2024": lf24, "legs_share_by_type": ys[0]["legs_share_by_type"], "engines": eng(ys[0])}
            log(f"  [{time.time() - t0:4.0f}s] rate {v}: FY2027 lost {ys[0]['lost_revenue_oku']} FY2032 {ys[5]['lost_revenue_oku']}")
        # the plan counting on recapture (sensitivity)
        rf.RECAPTURE_MODE = "optimize"
        for v in (0.3, 0.5, 0.7):
            rf.RECAPTURE = v
            y0 = cs.run(s, 0); y5 = cs.run(s, 5, windows=False)
            res["optimize"][str(v)] = {"fy2027": brief(y0), "fy2032": brief(y5), "lf_avg": y0["lf_avg"], "legs_share_by_type": y0["legs_share_by_type"], "engines": eng(y0)}
        rf.RECAPTURE_MODE = "expost"
        for v in KEY:
            rf.RECAPTURE = v
            base = cs.run(s, 3, dest=True, windows=True)
            e20 = cs.run(s, 3, delta=20, dest=True, windows=True)
            e20x = cs.run(s, 3, delta=20, dest={"CTS": 4, "FUK": 4}, windows=True)
            res["expansion"][str(v)] = {"base": {**brief(base), "engines": eng(base)},
                                        "hnd20": {"gain_oku": round(e20["margin_oku"] - base["margin_oku"], 1), "lost_revenue_oku": e20["lost_revenue_oku"], "engines": eng(e20)},
                                        "hnd20_cts_fuk": {"gain_oku": round(e20x["margin_oku"] - base["margin_oku"], 1), "lost_revenue_oku": e20x["lost_revenue_oku"], "engines": eng(e20x)}}
            res["market"][str(v)] = {"expansion_10_each": pair(S, 3, 10, 10), "realloc_a_plus5": pair(S, 1, 5, -5), "realloc_a_minus5": pair(S, 1, -5, 5)}
            log(f"  [{time.time() - t0:4.0f}s] rate {v}: +20 {res['expansion'][str(v)]['hnd20']['gain_oku']}, market done")
            C = cor.load()
            g = cor.linear_game(C, 3)
            w = cor.linear_world(s, C, 3)
            rows = []
            for r in g["rows"]:
                nash = r["nash"]
                rule = "stay/stay"
                rows.append({"air_keeps": r["air_keeps"], "cells": r["cells"], "nash": nash, "joint_best": r["joint_best"], "dilemma": r["dilemma"],
                             "rule_vs_nash": {n: {"a": round(r["cells"][rule]["a"] - r["cells"][n]["a"], 1), "b": round(r["cells"][rule]["b"] - r["cells"][n]["b"], 1)} for n in nash}})
            res["linear"][str(v)] = {"game": rows, "world": [{k: x[k] for k in ("air_keeps", "cell", "vs_before_oku", "expansion")} for x in w["rows"]]}
            log(f"  [{time.time() - t0:4.0f}s] rate {v}: linear done")
    finally:
        rf.RECAPTURE, rf.RECAPTURE_MODE = old
    d = {"company": "jal", "result": res,
         "how": "満席の便に乗れなかった旅客のうち、乗り換え率の分が同じ会社の同じ路線の別の便（同じ日・前後の日）に乗り換える。expost は計画を今のまま（乗れない旅客を全員失うとして立てた計画）にして、乗り換えた旅客がその月のその路線の空席（座席の 95% まで、no_source）を埋める。機材・エンジンは動かない。optimize は乗り換えを見込んで計画を立て直す（感度。搭乗率が 2024 年の実績を超える）。乗り換え率 0.15 は便数の少ない会社の事例値（JAIRM 2014、一定の乗り換え率は Barnhart ほか 2002 の旅程ベースの機材割当の置き方）、0.3・0.5・0.7 は no_source（幹線は 1 日 12〜20 往復あるので事例より高いとみる）。市場は会社 A と会社 B（他の航空会社は便数のまま）：拡張は両社 +10 往復、再配分は一方 +5・他方 −5、各社は相手の増えた便を競争相手の便として 1 回ずつ応じる",
         "sources": {"recapture_case": "https://www.jairm.org/index.php/jairm/article/download/20/56", "spill_basics": "https://ocw.mit.edu/courses/16-75j-airline-management-spring-2006/f990b2cd2141f75cd9b348051af762e7_lect4b.pdf"},
         "elapsed_s": round(time.time() - t0, 1)}
    out = out or HERE / "fleet" / "recapture_jal.json"
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"wrote {out} ({d['elapsed_s']} s)")
    return d


def months(path: Path | None = None) -> None:
    """Add the FY2027 months by rate to an existing output (expost)."""
    path = path or HERE / "fleet" / "recapture_jal.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    s = cs.setup("jal")
    old = (rf.RECAPTURE, rf.RECAPTURE_MODE)
    try:
        rf.RECAPTURE_MODE = "expost"
        d["result"]["months"] = {}
        for v in RATES:
            rf.RECAPTURE = v
            y = cs.run(s, 0, windows=False)
            d["result"]["months"][str(v)] = [{k: x[k] for k in ("label", "spill_pax_k", "lost_revenue_oku", "recaptured_pax_k")} for x in y["by_month"]]
    finally:
        rf.RECAPTURE, rf.RECAPTURE_MODE = old
    path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    import sys
    months() if "--months" in sys.argv else build()
