#!/usr/bin/env python3
"""Carbon as emissions trading (cap and trade): what an allowance price does to the trunk and to the
Linear's slot game, and what the Linear does to the country's CO2 (data/carbon.json).

  1. The price enters each flight's cost: every block hour burns fuel (t/h by type), and every tonne
     of CO2 costs the allowance price whether the company bought the allowance or was given it (an
     allowance it does not use can be sold). The fleet assignment is re-solved with that cost.
  2. The free allocation is a fixed amount (the company's emissions in the world before the Linear,
     at no price, times the free share): it adds price x allocation to the margin whatever the
     company flies, so it moves the level of the margin but never the choice.
  3. The worlds: before the Linear, and after it (the air keeps 66 % / 46 % of Haneda-Itami) in the
     slot game's two cells, stay/stay (the freed slots leave the trunk) and move/move (both companies
     refill the other trunk routes). Refilling pays when its margin beats staying at that price.
  4. The country: if the cap binds on aviation and power, the total is the cap -- the Linear's cut
     frees allowances for other sectors (the waterbed) unless they are cancelled. If it does not
     bind, the change is the aircraft's CO2 change plus the Linear's electricity for the passengers
     who left the air (grid factor as a scale on JR Central's "1/3 of the aircraft").
  5. The two-company game at a few prices: does the price change the equilibria?

  python carbon_scenarios.py jal --out fleet/carbon_jal.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import airport_slots as ap
import capacity_scenarios as cs
import corridor_scenarios as cor
import route_fleet as rf

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "carbon.json"


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def co2_t(r: dict, K: dict) -> float:
    """Tonnes of CO2 in the year the run solved: block hours x fuel per hour x 3.16."""
    f = K["fuel_t_per_block_h"]
    return sum(h * f[t] * K["co2_t_per_t_fuel"] for t, h in r["block_h_by_type"].items() if h)


def overrides(cid: str, K: dict, price: float, base: dict | None = None) -> dict | None:
    """The allowance price laid on each type's cost per block hour (k$)."""
    if not price:
        return base
    R = rf.load()
    out = {}
    for t in rf.types_of(R, cid):
        ty = {**t, **(base or {}).get(t["type"], {})}
        add = price * K["co2_t_per_t_fuel"] * K["fuel_t_per_block_h"][t["type"]] / rf.USD_JPY / 1e3
        out[t["type"]] = {**(base or {}).get(t["type"], {}), "cost_per_block_h_k": round(ty["cost_per_block_h_k"] + add, 4)}
    return out


def corridor_of(s: dict, C: dict, keep: float | None, cell: str) -> dict | None:
    """The same two cells as corridor_scenarios.linear_world."""
    if keep is None:
        return None
    S = ap.load()
    cid = s["cid"]
    cur = ap.current_freq(S, cid)
    caps = ap.destination_caps(S, cid)
    if cell == "move/move":
        rival_itm = ap.competitor_freq(S, cid)["HND-ITM"]
        b = {"HND-ITM": (0, cur["HND-ITM"] + 1), **{r: (cur[r] - 1, caps[r]) for r in ("HND-CTS", "HND-FUK", "HND-OKA")}}
        return {"market_scale": {"HND-ITM": keep}, "bounds": b, "use_min": 0.0,
                "rival_shift": {"HND-ITM": -(1 - keep) * rival_itm, **C["linear_osaka"]["rival_moves_to"]}}
    return {"market_scale": {"HND-ITM": keep}, "bounds": {"HND-ITM": (0, cur["HND-ITM"] + 1)}, "use_min": 0.0}


WORLDS = (("before", None, None), ("66%_stay/stay", 0.66, "stay/stay"), ("66%_move/move", 0.66, "move/move"),
          ("46%_stay/stay", 0.46, "stay/stay"), ("46%_move/move", 0.46, "move/move"))


def worlds(s: dict, C: dict, K: dict, years_ahead: int, prices=None) -> dict:
    prices = prices if prices is not None else K["prices_yen_per_t"]
    km = {r["id"]: r["km"] for r in rf.load()["routes"]}
    out = {}
    for p in prices:
        ov = overrides(s["cid"], K, p)
        for name, keep, cell in WORLDS:
            r = cs.run(s, years_ahead, dest=True, windows=False, overrides=ov, corridor=corridor_of(s, C, keep, cell))
            e = co2_t(r, K)
            out[(p, name)] = {"price": p, "world": name, "air_keeps": keep, "cell": cell, "margin_oku": r["margin_oku"], "co2_kt": round(e / 1e3, 1),
                              "carbon_cost_oku": round(p * e / 1e8, 1), "carried_pax_k": r["carried_pax_k"],
                              "co2_g_per_pkm": round(e * 1e6 / max(1e-9, sum(v * 1e3 * km[k] for k, v in r["carried_by_route_pax_k"].items())), 1),
                              "itm_carried_pax_k": r["carried_by_route_pax_k"]["HND-ITM"], "round_trips": r["version_round_trips"], "by_type": r["version_by_type"],
                              "block_h_by_type": r["block_h_by_type"]}
    return out


def system(W: dict, K: dict, km_itm: float) -> list[dict]:
    """The country's CO2 for each world after the Linear, against before, at the same price."""
    L = K["linear"]
    rows = []
    for (p, name), w in W.items():
        if name == "before":
            continue
        pre = W[(p, "before")]
        moved_k = pre["itm_carried_pax_k"] * (1 - w["air_keeps"])                # the company's Itami passengers who take the Linear
        lin = {str(g): round(moved_k * 1e3 * km_itm * L["air_g_per_pkm"] * L["linear_vs_air_co2"] * g / 1e9, 1) for g in L["grid_scales"]}   # kt
        hub = lambda x: sum(v for k, v in x["round_trips"].items() if k in ap.HUB_ROUTES)  # noqa: E731
        off = max(0.0, hub(pre) - hub(w))                                          # Haneda round trips a day that leave the trunk (not modelled: a regional estimate)
        off_kt = off * K["regional_round_trip_block_h"] * K["fuel_t_per_block_h"]["737"] * K["co2_t_per_t_fuel"] * 365 / 1e3
        d_air = round(w["co2_kt"] - pre["co2_kt"] + off_kt, 1)
        rows.append({"price": p, "world": name, "air_change_kt": d_air, "round_trips_off_trunk": round(off, 1), "off_trunk_kt": round(off_kt, 1), "linear_kt_by_grid_scale": lin,
                     "not_binding_change_kt": {g: round(d_air + v, 1) for g, v in lin.items()},
                     "binding": {"country_change_kt": 0.0, "allowances_freed_kt": round(-d_air, 1),
                                 "to_make_it_count": "空いた排出枠を取り消すか、上限をその分下げる"}})
    return rows


def game(C: dict, K: dict, years_ahead: int, prices=(0, 4300, 10000, 20000, 30000)) -> list[dict]:
    out = []
    for p in prices:
        ov = {c: overrides(c, K, p) for c in ("jal", "ana")} if p else None
        g = cor.linear_game(C, years_ahead, overrides=ov)
        out.append({"price": p, "rows": [{"air_keeps": r["air_keeps"], "nash": r["nash"], "joint_best": r["joint_best"], "dilemma": r["dilemma"],
                                          "cells": {k: {"a": v["a"], "b": v["b"], "sum": v["sum"]} for k, v in r["cells"].items()}} for r in g["rows"]]})
    return out


def build(cid: str, out: Path | None = None, years_ahead: int = 3, with_game: bool = True, log=print) -> dict:
    t0 = time.time()
    C = cor.load()
    K = load()
    s = cs.setup(cid)
    W = worlds(s, C, K, years_ahead)
    e0 = W[(0, "before")]["co2_kt"] * 1e3
    rows = []
    for (p, name), w in W.items():
        rows.append({**w, "margin_with_allocation_oku": {str(f): round(w["margin_oku"] + p * f * e0 / 1e8, 1) for f in K["free_shares"]},
                     "allowance_surplus_kt": {str(f): round(f * e0 / 1e3 - w["co2_kt"], 1) for f in K["free_shares"]}})
    refill = [{"price": p, "air_keeps": k, "move_minus_stay_oku": round(W[(p, f"{int(k*100)}%_move/move")]["margin_oku"] - W[(p, f"{int(k*100)}%_stay/stay")]["margin_oku"], 1),
               "co2_move_minus_stay_kt": round(W[(p, f"{int(k*100)}%_move/move")]["co2_kt"] - W[(p, f"{int(k*100)}%_stay/stay")]["co2_kt"], 1)}
              for p in K["prices_yen_per_t"] for k in (0.66, 0.46)]
    km_itm = next(r["km"] for r in rf.load()["routes"] if r["id"] == "HND-ITM")
    res = {"company": cid, "fiscal_year": cs.fy_after(s["fy"], years_ahead), "reference_co2_kt": round(e0 / 1e3, 1), "rows": rows, "refill": refill,
           "system": system(W, K, km_itm), "game": game(C, K, years_ahead) if with_game else None, "assumptions": K,
           "how": "排出枠の価格を 1 ブロック時間あたりの運航費に足して機材割当を解き直す（枠を使えば売れたはずの分を失うので、無償の枠でも価格は効く）。無償の割当は、リニアがなく価格もない年の自社の排出量 × 無償の割合で、利益に一括で足す。refill は、空いた枠を幹線に移す（move/move）と移さない（stay/stay）の利益の差（割当は両方に同じなので消える）。system は国全体：上限が効いていれば総量は上限のまま（リニアで空いた枠は他の部門に回る）、効いていなければ航空の変化 ＋ リニアの電気（伊丹から移った自社の旅客 × 距離 × 航空の 1/3 × 電気の係数の倍率）",
           "elapsed_s": round(time.time() - t0, 1)}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"wrote {out} ({res['elapsed_s']} s)")
    return res


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("company", nargs="?", default="jal")
    a.add_argument("--out", type=Path, default=None)
    a.add_argument("--no-game", action="store_true")
    args = a.parse_args(argv)
    build(args.company, args.out or HERE / "fleet" / f"carbon_{args.company}.json", with_game=not args.no_game)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
