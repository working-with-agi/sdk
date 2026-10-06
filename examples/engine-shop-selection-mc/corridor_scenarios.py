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


def linear_osaka(s: dict, C: dict, years_ahead: int, base: dict, overrides: dict | None = None) -> dict:
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
                cells[f"{own}/{riv}"] = _summary(cs.run(s, years_ahead, dest=True, corridor=cor, overrides=overrides), base)
        best = {riv: max(("stay", "move"), key=lambda o: cells[f"{o}/{riv}"]["margin_oku"]) for riv in ("stay", "move")}
        rows.append({"air_keeps": keep, "cells": cells, "best_response": best,
                     "value_of_moving_slots_oku": {riv: round(cells[f"move/{riv}"]["margin_oku"] - cells[f"stay/{riv}"]["margin_oku"], 1) for riv in ("stay", "move")}})
    return {"rows": rows, "how": "セルは「会社 A が空いた枠を他の幹線に移すか／移さないか」×「他社も移すか／移さないか」。差し引きの変化は、リニアがない基準（同じ年度）から。羽田–伊丹の需要は air_keeps 倍。空いた枠を幹線で使わない分は幹線の外（他の路線）に回るとして、枠を使う下限は外す"}


def linear_game(C: dict, years_ahead: int, cids: tuple = ("jal", "ana"), overrides: dict | None = None) -> dict:
    """Both companies' payoffs for the Linear-to-Osaka slot game, each solved with its own fleet and
    slots, the other's move entering as a shift of the other carriers' frequencies. Pure-strategy
    equilibria and the pair that leaves the two together best off (by the sum of their margins)."""
    sol = {}
    for cid in cids:
        s = cs.setup(cid)
        ov = (overrides or {}).get(cid)
        base = cs.run(s, years_ahead, dest=True, overrides=ov)
        sol[cid] = linear_osaka(s, C, years_ahead, base, ov)
    a, b = cids
    acts = ("stay", "move")
    rows = []
    for i, keep in enumerate(C["linear_osaka"]["air_keeps"]):
        ra, rb = sol[a]["rows"][i], sol[b]["rows"][i]
        cells = {}
        for x in acts:
            for y in acts:
                pa = ra["cells"][f"{x}/{y}"]["margin_change_oku"]                   # A plays x, B plays y
                pb = rb["cells"][f"{y}/{x}"]["margin_change_oku"]
                cells[f"{x}/{y}"] = {"a": pa, "b": pb, "sum": round(pa + pb, 1),
                                     "spill_pax_k": {"a": ra["cells"][f"{x}/{y}"]["spill_pax_k"], "b": rb["cells"][f"{y}/{x}"]["spill_pax_k"]}}
        nash = [k for k, v in cells.items()
                if all(v["a"] >= cells[f"{x2}/{k.split('/')[1]}"]["a"] - 1e-9 for x2 in acts)
                and all(v["b"] >= cells[f"{k.split('/')[0]}/{y2}"]["b"] - 1e-9 for y2 in acts)]
        best = max(cells, key=lambda k: cells[k]["sum"])
        dilemma = any(all(cells[k][w] > cells[n][w] for w in ("a", "b")) for n in nash for k in cells if k != n)   # some pair leaves both better off than an equilibrium
        rows.append({"air_keeps": keep, "cells": cells, "nash": nash, "joint_best": best, "dilemma": dilemma})
    return {"companies": {"a": a, "b": b}, "rows": rows,
            "how": "セルは「A の手/B の手」。各社の損得は、その会社の機材と枠で機材割当を解いた差し引きの変化（リニアがない同じ年度から）。相手が移すことは、他社の便数の移動（伊丹 −(1−残る割合)×相手の便数、新千歳・福岡・那覇に +3・+2・+6 往復、no_source）として入る。均衡は純粋戦略のナッシュ均衡、joint_best は二社の合計が最大のセル。dilemma は、ある均衡より両社とも得になるセルがあること（囚人のジレンマの形）",
            "caveat": "会社 B の運航費の係数は会社 A のように 2024 年の搭乗率に合わせていない。737 の需要の割合（0.28）が機材に対して大きすぎる問題も残る"}


def game_robustness(C: dict, years_ahead: int, settings: tuple = ((3.5, 0.5), (3.5, 0.7), (3.5, 0.9), (4.0, 0.6), (3.0, 0.8))) -> dict:
    """The same game with company B's operating costs from several (base_737, seat_exponent) pairs,
    since no pair fits company B's 2024 load factors well: do the readings survive?"""
    import calibrate_costs as cc
    R = rf.load()
    out = []
    for b, e in settings:
        ov = {"ana": {t: {"cost_per_block_h_k": c} for t, c in cc.costs(R, "ana", b, e).items()}}
        g = linear_game(C, years_ahead, overrides=ov)
        rows = []
        for r in g["rows"]:
            n = r["nash"]
            pareto = any(all(r["cells"][k][w] > r["cells"][x][w] for w in ("a", "b")) for x in n for k in r["cells"] if k != x)
            rows.append({"air_keeps": r["air_keeps"], "nash": n, "joint_best": r["joint_best"],
                         "joint_loss_oku": [round(r["cells"][r["joint_best"]]["sum"] - r["cells"][x]["sum"], 1) for x in n],
                         "both_better_than_an_equilibrium": pareto})
        out.append({"b_base_737": b, "b_seat_exponent": e, "fares": "distance", "rows": rows})
    # the route fare levels fitted to both companies' 2024 load factors (company B fits far better)
    old = rf.FARE_MODE
    rf.FARE_MODE = "fitted"
    try:
        g = linear_game(C, years_ahead)
    finally:
        rf.FARE_MODE = old
    rows = []
    for r in g["rows"]:
        n = r["nash"]
        pareto = any(all(r["cells"][k][w] > r["cells"][x][w] for w in ("a", "b")) for x in n for k in r["cells"] if k != x)
        rows.append({"air_keeps": r["air_keeps"], "nash": n, "joint_best": r["joint_best"],
                     "joint_loss_oku": [round(r["cells"][r["joint_best"]]["sum"] - r["cells"][x]["sum"], 1) for x in n],
                     "both_better_than_an_equilibrium": pareto, "cells": r["cells"]})
    out.append({"b_base_737": 3.5, "b_seat_exponent": 0.7, "fares": "fitted", "rows": rows})
    return {"settings": out, "how": "会社 B の運航費の係数（737 の 1 時間あたりの費用と座席数の指数）を変えて、同じゲームを解き直す。最後の 1 通りは、両社の 2024 年の搭乗率に合わせた路線ごとの運賃の水準（fare_taper.route_adjust_fitted）で両社を解いたもの。均衡、合計が最大の組み合わせ、均衡での合計の目減り、均衡より両社とも得なセルがあるか"}


def linear_world(s: dict, C: dict, years_ahead: int) -> dict:
    """The world after the Linear (both companies move their freed slots, the rule's case): what the
    Haneda expansion is worth there, against the world before it."""
    S = ap.load()
    cid = s["cid"]
    cur = ap.current_freq(S, cid)
    rival_itm = ap.competitor_freq(S, cid)["HND-ITM"]
    pre = cs.run(s, years_ahead, dest=True, windows=False)
    out = []
    for keep in C["linear_osaka"]["air_keeps"][:2]:
        rival = {"HND-ITM": -(1 - keep) * rival_itm, **C["linear_osaka"]["rival_moves_to"]}
        def corridor(extra=None):
            capx = ap.destination_caps(S, cid, extra=extra)
            b = {"HND-ITM": (0, cur["HND-ITM"] + 1), **{r: (cur[r] - 1, capx[r]) for r in ("HND-CTS", "HND-FUK", "HND-OKA")}}
            return {"market_scale": {"HND-ITM": keep}, "bounds": b, "use_min": 0.0, "rival_shift": rival}
        base = cs.run(s, years_ahead, dest=True, corridor=corridor())
        rows = {}
        for k, delta, extra in (("hnd20", 20, None), ("hnd20_cts_fuk", 20, {"CTS": 4, "FUK": 4})):
            r = cs.run(s, years_ahead, delta=delta, dest=extra or True, windows=False, corridor=corridor(extra))
            rows[k] = {"gain_oku_per_year": round(r["margin_oku"] - base["margin_oku"], 1), "pax_added_k": round(r["carried_pax_k"] - base["carried_pax_k"], 1),
                       "round_trips": r["version_round_trips"], "unusable_round_trips": r["unusable_round_trips"]}
        out.append({"air_keeps": keep, "base_margin_oku": base["margin_oku"], "vs_before_oku": round(base["margin_oku"] - pre["margin_oku"], 1),
                    "base_round_trips": base["version_round_trips"], "expansion": rows,
                    "engines": {e["type"]: {"utilisation_multiplier": e.get("utilisation_multiplier"), "spend_per_year_oku_yen": e.get("spend_per_year_oku_yen")} for e in base["engines"] if e["type"] in ("737", "767", "787")}})
    return {"rows": out, "how": "リニアの後の世界：羽田–伊丹の需要は air_keeps 倍、両社とも空いた枠を新千歳・福岡・那覇に移した状態（配分の規則で移す場合）。そこで羽田 +20 往復（対向空港そのまま／新千歳・福岡 各 +4 往復）の増分を出す"}


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
    C50 = json.loads(json.dumps(C)); C50["itami_smaller"]["years"] = 50
    mc50 = itami_monte_carlo(C50)
    mc["years_50"] = {"steps": mc50.get("steps"), "p_all_items": mc50.get("p_all_items"), "net_all_items_oku_p10_p50_p90": mc50.get("net_all_items_oku_p10_p50_p90")}
    return {"land_value_oku": [round(land_lo), round(land_hi)], "extra_cost_one_way_yen": round(extra), "rows": rows, "annuity_30y_4pct": round(A, 2),
            "monte_carlo": mc,
            "how": "土地の値 ＝ 面積 × 使える割合 × 地価（幅）。旅客の損 ＝ 伊丹に残る旅客 × 片道の追加費用（時間 × 時間価値 ＋ 運賃差）を 30 年・4% で現在価値に。空港の運営費・跡地の造成費・関西の追加の容量は入れていない（ふるい分け）"}


def itami_monte_carlo(C: dict, n: int = 20000, seed: int = 7, steps: bool = True) -> dict:
    """The same screening with the uncertain inputs drawn from their ranges (uniform): how often the
    land (plus what closing saves) is worth more than the passengers' extra access (plus what moving
    the flights costs). With steps, the items left out of the first screening are added one at a
    time so each one's pull on the probability shows."""
    import numpy as np
    I = C["itami_smaller"]; U = I["ranges"]; M = I.get("more", {})
    rng = np.random.default_rng(seed)
    u = lambda lo_hi: rng.uniform(lo_hi[0], lo_hi[1], n)  # noqa: E731
    keep, price, usable = u(U["air_keeps"]), u(U["land_price_yen_m2"]), u(U["usable_share"])
    dmin, dfare, vot, pax = u(U["extra_access_min"]), u(U["extra_access_fare_yen"]), u(U["value_of_time_yen_per_hour"]), u(U["itami_pax_million_per_year"])
    rate, years = I["discount_rate"], I["years"]
    A = (1 - (1 + rate) ** -years) / rate
    area_m2 = I["area_ha"] * 1e4 * usable
    land = area_m2 * price / 1e8
    left = I["share_on_tokyo_route"] * keep + (1 - I["share_on_tokyo_route"])
    loss = pax * left * 1e6 * (dmin / 60 * vot + dfare) / 1e8 * A
    q = lambda x: [round(float(v)) for v in np.percentile(x, [10, 50, 90])]  # noqa: E731
    out = {"draws": n, "years": years, "discount_rate": rate,
           "land_oku_p10_p50_p90": q(land), "passenger_loss_pv_oku_p10_p50_p90": q(loss)}
    net = land - loss
    out["p_land_exceeds_loss"] = round(float((net > 0).mean()), 3)
    out["net_oku_p10_p50_p90"] = q(net)
    if steps and M:
        st = [{"step": "跡地 − 旅客の損", "p": out["p_land_exceeds_loss"], "net_p50": q(net)[1]}]
        save = (u(M["operating_saving_oku_per_year"]) + 0) * A
        net = net + save
        st.append({"step": "＋ 運営費の節約", "p": round(float((net > 0).mean()), 3), "net_p50": q(net)[1]})
        noise = u(M["noise_benefit_oku_per_year"]) * A
        net = net + noise
        st.append({"step": "＋ 騒音の解消", "p": round(float((net > 0).mean()), 3), "net_p50": q(net)[1]})
        prep = area_m2 * u(M["site_prep_yen_m2"]) / 1e8
        drop = land * u(M["land_price_drop_share"])
        net = net - prep - drop
        st.append({"step": "− 造成費・地価の下落", "p": round(float((net > 0).mean()), 3), "net_p50": q(net)[1]})
        need = M["itami_movements_per_year"] * left
        room = (M["kix_target"] - M["kix_movements_2024"]) * u(M["kix_share_for_itami"]) + M["kobe_added_movements_per_year"]
        short = np.maximum(0.0, need - room)
        cap_cost = short / 730 * u(M["capacity_cost_oku_per_round_trip_day"])
        net = net - cap_cost
        st.append({"step": "− 関西・神戸で足りない容量の手当て", "p": round(float((net > 0).mean()), 3), "net_p50": q(net)[1]})
        out["steps"] = st
        out["kix_kobe"] = {"itami_movements_to_move_p10_p50_p90": q(need), "room_p10_p50_p90": q(room), "shortfall_p10_p50_p90": q(short),
                           "p_shortfall": round(float((short > 0).mean()), 3), "capacity_cost_oku_p10_p50_p90": q(cap_cost)}
        out["p_all_items"] = st[-1]["p"]
        out["net_all_items_oku_p10_p50_p90"] = q(net)
    out["how"] = ("不確かな入力を幅の中で一様に引き、跡地の値 − 旅客の損（現在価値）が正になる確率を出す。steps は最初に入れていなかった項目"
                  "（運営費の節約・騒音の解消・造成費・地価の下落・関西と神戸で足りない容量の手当て）を一つずつ足したときの確率。足した項目の幅は no_source")
    return out


def build(cid: str, out: Path | None = None, years_ahead: int = 3, log=print) -> dict:
    C = load()
    s = cs.setup(cid)
    t0 = time.time()
    base = cs.run(s, years_ahead, dest=True)
    tr = rf.build(s["cid"], s["D"], s["rpk"], cs.ffd.trunk_context(s["cid"], s["cfg"], s["rpk"], s["ac"], s["eng"], s["derived"], years_ahead)[0],
                  quantiles=("p50",), detail=False, fiscal_years={s["fy"]}, dest=True)
    base["spill_by_route_pax_k"] = {r: round(sum(x["spill_by_route_p50"][r] for x in tr["rows"]), 1) for r in tr["rows"][0]["spill_by_route_p50"]}
    lin = linear_osaka(s, C, years_ahead, base)
    world = linear_world(s, C, years_ahead)
    if log:
        log(f"  [{time.time() - t0:4.0f}s] linear_osaka done")
    game = linear_game(C, years_ahead)
    if log:
        log(f"  [{time.time() - t0:4.0f}s] linear_game done")
    game["robustness"] = game_robustness(C, years_ahead)
    if log:
        log(f"  [{time.time() - t0:4.0f}s] robustness done")
    res = {"company": cid, "linear_game": game, "fiscal_year": cs.fy_after(s["fy"], years_ahead), "base": {"margin_oku": base["margin_oku"], "carried_pax_k": base["carried_pax_k"],
                                                                                         "spill_pax_k": base["spill_pax_k"], "spill_by_route_pax_k": base["spill_by_route_pax_k"]},
           "linear_osaka": lin, "linear_world": world, "rail_airports": rail_airports(s, C, base), "itami_smaller": itami_smaller(C, lin),
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
    for g in r["linear_game"]["rows"]:
        print(f" game keeps {g['air_keeps']}: nash {g['nash']} joint best {g['joint_best']} dilemma {g['dilemma']} " + str({k: (v['a'], v['b'], v['sum']) for k, v in g['cells'].items()}))
    for a_ in r["rail_airports"]["airports"]:
        print(f" {a_['airport']}: extra {a_['extra_cost_one_way_yen']} yen, captured {a_['captured_pax_k']} k  " + str({k: v['would_still_fly'] for k, v in a_['routes'].items()}))
    i = r["itami_smaller"]
    print(f" itami: land {i['land_value_oku']} 億円, extra {i['extra_cost_one_way_yen']} yen/pax, rows {i['rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
