#!/usr/bin/env python3
"""Capacity from the ground: the Linear to Osaka, Centrair by rail, and a smaller Itami.

The airport story ended on two caps -- Haneda's slots and the airports at the other end -- and on
the price of new runways. Three cases put the ground transport into it (data/corridor.json):

  1. linear_osaka   the Linear reaches Shin-Osaka (Tokyo-Osaka about 67 minutes) and takes a share
                    of the Haneda-Itami market. The fleet assignment is re-solved with that market
                    shrunk, for four cells: company A moves its freed slots to the other trunk routes
                    or not, x the other carriers move theirs or not (they then share those routes).
                    Margin, passengers, the spill, and the engines.
  2. rail_airports  an airport reached by rail from central Tokyo (Centrair via the Linear to Nagoya,
                    a Yamanashi airport via the Linear, Narita for reference): the extra access time
                    and fare as a share of the air fare, and the share of Haneda's spilled passengers
                    who would still fly from there (the same linear demand curve as the fares, on the
                    whole trip cost). Screening only: no new patterns are solved.
  3. itami_smaller  after the Linear, Itami's remaining flights move to Kansai/Kobe: the passengers'
                    extra access cost (time and fare) against the land the airport frees. Screening.

Everything is synthetic or public and flagged no_source where it has no source.

  python corridor_scenarios.py jal --out fleet/corridor_jal.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import airport_slots as ap
import capacity_scenarios as cs
import route_fleet as rf

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "corridor.json"


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _summary(r: dict, base: dict) -> dict:
    eng = {e["type"]: e for e in r["engines"]}
    eng0 = {e["type"]: e for e in base["engines"]}
    return {"round_trips": r["version_round_trips"], "margin_oku": r["margin_oku"], "margin_change_oku": round(r["margin_oku"] - base["margin_oku"], 1),
            "carried_pax_k": r["carried_pax_k"], "spill_pax_k": r["spill_pax_k"], "carried_change_pax_k": round(r["carried_pax_k"] - base["carried_pax_k"], 1),
            "engines": {t: {"utilisation_multiplier": eng[t].get("utilisation_multiplier"), "spend_per_year_oku_yen": eng[t].get("spend_per_year_oku_yen"),
                            "spend_change_oku": round((eng[t].get("spend_per_year_oku_yen") or 0) - (eng0[t].get("spend_per_year_oku_yen") or 0), 1)}
                        for t in ("737", "767", "787") if t in eng}}


def linear_osaka(s: dict, C: dict, years_ahead: int, base: dict) -> dict:
    """Four cells for each share of the Haneda-Itami market the air keeps."""
    L = C["linear_osaka"]
    S = ap.load()
    cur = ap.current_freq(S, s["cid"])
    caps = ap.destination_caps(S, s["cid"])
    rival_itm = ap.competitor_freq(S, s["cid"])["HND-ITM"]
    rows = []
    for keep in L["air_keeps"]:
        freed_bounds = {"HND-ITM": (0, cur["HND-ITM"] + 1)}
        move = {**freed_bounds, **{r: (cur[r] - 1, caps[r]) for r in ("HND-CTS", "HND-FUK", "HND-OKA")}}
        rival = {"HND-ITM": -(1 - keep) * rival_itm, **L["rival_moves_to"]}
        cells = {}
        for own in ("stay", "move"):
            for riv in ("stay", "move"):
                cor = {"market_scale": {"HND-ITM": keep}, "bounds": move if own == "move" else freed_bounds, "use_min": 0.0}
                if riv == "move":
                    cor["rival_shift"] = rival
                cells[f"{own}/{riv}"] = _summary(cs.run(s, years_ahead, dest=True, corridor=cor), base)
        best = {riv: max(("stay", "move"), key=lambda o: cells[f"{o}/{riv}"]["margin_oku"]) for riv in ("stay", "move")}
        rows.append({"air_keeps": keep, "cells": cells, "best_response": best,
                     "value_of_moving_slots_oku": {riv: round(cells[f"move/{riv}"]["margin_oku"] - cells[f"stay/{riv}"]["margin_oku"], 1) for riv in ("stay", "move")}})
    return {"rows": rows, "how": "セルは「会社 A が空いた枠を他の幹線に移すか／移さないか」×「他社も移すか／移さないか」。差し引きの変化は、リニアがない基準（同じ年度）から。羽田–伊丹の需要は air_keeps 倍。空いた枠を幹線で使わない分は幹線の外（他の路線）に回るとして、枠を使う下限は外す"}


def rail_airports(s: dict, C: dict, base: dict) -> dict:
    """Screening: of Haneda's spilled passengers on the long trunk routes, how many fly from an
    airport reached by rail, given the extra access cost against the air fare."""
    R = rf.load()
    fare = rf.fare_yen(R, s["D"]["companies"][s["cid"]]["yield_yen_per_rpk"])
    vot = C["value_of_time_yen_per_hour"]["value"]
    e = C["rail_airports"]["elasticity"]
    spill = base.get("spill_by_route_pax_k") or {}
    routes = ("HND-CTS", "HND-FUK", "HND-OKA")
    out = []
    for a in C["rail_airports"]["airports"]:
        dt = (a["access_min"] - C["rail_airports"]["haneda_access_min"]) / 60
        dfare = a["access_fare_yen"] - C["rail_airports"]["haneda_access_fare_yen"]
        extra = dt * vot + dfare                                                       # one way, yen
        rows = {}
        for r in routes:
            rel = extra / fare[r]
            keep = max(0.0, 1 + e * rel)                                                  # the linear demand curve on the whole trip cost
            rows[r] = {"fare_yen": round(fare[r]), "extra_cost_share": round(rel, 2), "would_still_fly": round(keep, 2),
                       "spill_pax_k": spill.get(r), "captured_pax_k": round(spill[r] * keep, 1) if r in spill else None}
        cap = sum(x["captured_pax_k"] or 0 for x in rows.values())
        out.append({"airport": a["name"], "access_min": a["access_min"], "access_fare_yen": a["access_fare_yen"], "extra_cost_one_way_yen": round(extra),
                    "routes": rows, "captured_pax_k": round(cap, 1), "note": a.get("note")})
    return {"airports": out, "value_of_time": vot, "elasticity": e,
            "how": "片道の追加費用 ＝ アクセスの時間差 × 時間価値 ＋ 運賃差。航空運賃に対する比で、運賃と同じ直線の需要曲線（弾力性 e）に当てて、羽田で乗れなかった旅客のうち、その空港からなら飛ぶ割合を出す。便を飛ばす費用と機材は解いていない（ふるい分け）"}


def itami_smaller(C: dict, linear: dict) -> dict:
    """Screening: the land Itami frees against the passengers' extra access to Kansai/Kobe."""
    I = C["itami_smaller"]
    vot = C["value_of_time_yen_per_hour"]["value"]
    extra = I["extra_access_min"] / 60 * vot + I["extra_access_fare_yen"]          # one way, yen per passenger
    rows = []
    for keep in C["linear_osaka"]["air_keeps"]:
        pax_m = I["itami_pax_million_per_year"] * (I["share_on_tokyo_route"] * keep + (1 - I["share_on_tokyo_route"]))
        cost_year = pax_m * 1e6 * extra / 1e8                                           # 億円 a year
        rows.append({"air_keeps": keep, "itami_pax_million": round(pax_m, 2), "extra_cost_oku_per_year": round(cost_year, 1)})
    land_lo = I["area_ha"] * 1e4 * I["usable_share"] * I["land_price_yen_m2"][0] / 1e8
    land_hi = I["area_ha"] * 1e4 * I["usable_share"] * I["land_price_yen_m2"][1] / 1e8
    A = (1 - 1.04 ** -30) / 0.04
    for r in rows:
        r["passenger_cost_pv_oku"] = round(r["extra_cost_oku_per_year"] * A)
    mc = itami_monte_carlo(C)
    return {"land_value_oku": [round(land_lo), round(land_hi)], "extra_cost_one_way_yen": round(extra), "rows": rows, "annuity_30y_4pct": round(A, 2),
            "monte_carlo": mc,
            "how": "土地の値 ＝ 面積 × 使える割合 × 地価（幅）。旅客の損 ＝ 伊丹に残る旅客 × 片道の追加費用（時間 × 時間価値 ＋ 運賃差）を 30 年・4% で現在価値に。空港の運営費・跡地の造成費・関西の追加の容量は入れていない（ふるい分け）"}


def itami_monte_carlo(C: dict, n: int = 20000, seed: int = 7) -> dict:
    """The same screening with the uncertain inputs drawn from their ranges (uniform): how often the
    land is worth more than the passengers' extra access, and by how much either way."""
    import numpy as np
    I = C["itami_smaller"]; U = I["ranges"]
    rng = np.random.default_rng(seed)
    u = lambda k: rng.uniform(U[k][0], U[k][1], n)  # noqa: E731
    keep, price, usable = u("air_keeps"), u("land_price_yen_m2"), u("usable_share")
    dmin, dfare, vot, pax = u("extra_access_min"), u("extra_access_fare_yen"), u("value_of_time_yen_per_hour"), u("itami_pax_million_per_year")
    rate, years = I["discount_rate"], I["years"]
    A = (1 - (1 + rate) ** -years) / rate
    land = I["area_ha"] * 1e4 * usable * price / 1e8
    pax_left = pax * (I["share_on_tokyo_route"] * keep + (1 - I["share_on_tokyo_route"]))
    loss = pax_left * 1e6 * (dmin / 60 * vot + dfare) / 1e8 * A
    net = land - loss
    q = lambda x: [round(float(v)) for v in np.percentile(x, [10, 50, 90])]  # noqa: E731
    return {"draws": n, "p_land_exceeds_loss": round(float((net > 0).mean()), 3), "net_oku_p10_p50_p90": q(net),
            "land_oku_p10_p50_p90": q(land), "passenger_loss_pv_oku_p10_p50_p90": q(loss), "years": years, "discount_rate": rate,
            "how": "不確かな入力（航空に残る割合・地価・使える割合・追加の時間と運賃・時間価値・伊丹の旅客数）を幅の中で一様に引き、土地の値 − 旅客の損（現在価値）が正になる確率を出す。運営費の節約・騒音の解消・跡地の造成費・関西の追加の容量は入れていない"}


def build(cid: str, out: Path | None = None, years_ahead: int = 3, log=print) -> dict:
    C = load()
    s = cs.setup(cid)
    t0 = time.time()
    base = cs.run(s, years_ahead, dest=True)
    tr = rf.build(s["cid"], s["D"], s["rpk"], cs.ffd.trunk_context(s["cid"], s["cfg"], s["rpk"], s["ac"], s["eng"], s["derived"], years_ahead)[0],
                  quantiles=("p50",), detail=False, fiscal_years={s["fy"]}, dest=True)
    base["spill_by_route_pax_k"] = {r: round(sum(x["spill_by_route_p50"][r] for x in tr["rows"]), 1) for r in tr["rows"][0]["spill_by_route_p50"]}
    lin = linear_osaka(s, C, years_ahead, base)
    if log:
        log(f"  [{time.time() - t0:4.0f}s] linear_osaka done")
    res = {"company": cid, "fiscal_year": cs.fy_after(s["fy"], years_ahead), "base": {"margin_oku": base["margin_oku"], "carried_pax_k": base["carried_pax_k"],
                                                                                         "spill_pax_k": base["spill_pax_k"], "spill_by_route_pax_k": base["spill_by_route_pax_k"]},
           "linear_osaka": lin, "rail_airports": rail_airports(s, C, base), "itami_smaller": itami_smaller(C, lin),
           "facts": C, "note": "数値は合成データと公開値の混合。p50。2・3 はふるい分けの計算"}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("company")
    a.add_argument("--out", type=Path)
    args = a.parse_args(argv)
    r = build(args.company, args.out)
    print(f"{r['fiscal_year']} base {r['base']}")
    for x in r["linear_osaka"]["rows"]:
        print(f" air keeps {x['air_keeps']}: best response {x['best_response']} value of moving {x['value_of_moving_slots_oku']}")
        for k, c in x["cells"].items():
            print(f"   {k}: Δmargin {c['margin_change_oku']} carried {c['carried_change_pax_k']} spill {c['spill_pax_k']} rt {c['round_trips']} engines {c['engines']}")
    for a_ in r["rail_airports"]["airports"]:
        print(f" {a_['airport']}: extra {a_['extra_cost_one_way_yen']} yen, captured {a_['captured_pax_k']} k  " + str({k: v['would_still_fly'] for k, v in a_['routes'].items()}))
    i = r["itami_smaller"]
    print(f" itami: land {i['land_value_oku']} 億円, extra {i['extra_cost_one_way_yen']} yen/pax, rows {i['rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
