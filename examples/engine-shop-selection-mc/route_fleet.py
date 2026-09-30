#!/usr/bin/env python3
"""Route layer: demand per trunk route -> aircraft per route -> engines.

An aircraft that flies is somewhere else afterwards, so the unit of planning is not a seat-km
but a pattern: a day's chain of legs that leaves the hub (HND) and returns to it, the next leg
departing from where the previous one landed. `data/routes_trunk.json` holds the five trunk
routes (one-way monthly passengers, block hours, a seasonal deviation per route that is
normalised so the whole follows the market's seasonal index) and six patterns.

For each month and each demand quantile the smallest number of aircraft that carries every
route's passengers at the target load factor is a small integer programme over the patterns
(PuLP + HiGHS). The 737 carries only its share of each trunk route (the widebodies carry the rest, up to their
L/F cap). The yearly version's assignment (the smallest mix for the first 12 months) is scored
against the same demand: load factor per route, spilled passengers, aircraft usable after
airframe checks and engine waits (engine swaps and spares are at the hub only, so an aircraft
waiting for an engine sits at HND). Levers for a short month: move aircraft in from the other
routes, re-mix the patterns, fly longer days, wet-lease, or spill.

Cycles come from the patterns: a short-sector pattern flies more legs per day, so the engines
of the aircraft on it consume their windows faster. The trunk's cycles per aircraft-day, blended
with the rest of the fleet, is the utilisation multiplier handed to plan_from_demand.build_fleet.

Everything is synthetic; the route inputs are flagged no_source in the data file.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pulp

import demand as demand_mod
import plan_from_demand as pfd

HERE = Path(__file__).resolve().parent
ROUTES = HERE / "data" / "routes_trunk.json"
DAYS = 365 / 12
USD_JPY = 157.0
WET_LEASE_K_PER_AC_MONTH = 850.0
DAY_STRETCH = 1.10          # a pattern's day can be stretched this much (one more short leg) before crews and curfews bind


def load() -> dict:
    return json.loads(ROUTES.read_text(encoding="utf-8"))


def _route_of(leg: str, ids: set[str]) -> str:
    a, b = leg.split("-")
    return f"{a}-{b}" if f"{a}-{b}" in ids else f"{b}-{a}"


def pattern_table(R: dict) -> list[dict]:
    """Legs per route, block hours and cycles per day for each pattern."""
    ids = {r["id"] for r in R["routes"]}
    bh = {r["id"]: r["block_h"] for r in R["routes"]}
    out = []
    for p in R["patterns"]:
        legs = {}
        for l in p["legs"]:
            legs[_route_of(l, ids)] = legs.get(_route_of(l, ids), 0) + 1
        block = sum(bh[_route_of(l, ids)] for l in p["legs"])
        day = block + R["turnaround_h"] * (len(p["legs"]) - 1)
        out.append({"id": p["id"], "name": p["name"], "legs": legs, "cycles_per_day": len(p["legs"]), "block_h": round(block, 1), "day_h": round(day, 1),
                    "fits_day": day <= R["day_block_cap_h"], "cycles_per_block_h": round(len(p["legs"]) / block, 2)})
    return out


def route_demand(R: dict, D: dict, cid: str, band: list[dict]) -> list[dict]:
    """Passengers per route per month, both directions, p10/p50/p90, split by aircraft type.
    The route's seasonal deviation is normalised each month so the passenger-weighted whole equals
    the market's seasonal index; the trend and the band's relative width come from the company-level
    band. The widebodies (A350, 767, 787) carry the route's non-737 share; their seats are fixed over
    the year (sized at the base L/F), so in a busy month their L/F rises to the cap and the overflow
    moves to the 737. What the 737 must carry is the 737 share plus that overflow."""
    mv = demand_mod.market_view(D)
    idx = {c["month"]: c["demand_index"] for c in mv["seasonal"]}
    scale = R["companies"][cid]["scale"]
    lf_base, lf_cap = R["wide_lf_base"], R["wide_lf_cap"]
    w = {r["id"]: r["pax_month_k"] for r in R["routes"]}
    W = sum(w.values())
    out = []
    for b in band:
        m = int(b["label"][5:])
        norm = sum(w[r["id"]] * r["season_dev"][m - 1] for r in R["routes"]) / W
        rows, alls, wide = {}, {}, {}
        for r in R["routes"]:
            base = r["pax_month_k"] * 2 * scale
            seats_wide = (1 - r["share_737"]) * base / lf_base                     # thousand seats a month, fixed
            tot = base * idx[m] * r["season_dev"][m - 1] / norm * b["trend"]
            q = {"p10": tot * b["p10"] / b["p50"], "p50": tot, "p90": tot * b["p90"] / b["p50"]}
            carried = {k: min((1 - r["share_737"]) * v, seats_wide * lf_cap) for k, v in q.items()}
            rows[r["id"]] = {k: round(q[k] - carried[k], 1) for k in q}
            alls[r["id"]] = round(tot, 1)
            wide[r["id"]] = {"seats_k": round(seats_wide, 1), "carried_p50_k": round(carried["p50"], 1), "lf_p50": round(carried["p50"] / seats_wide, 3) if seats_wide else None,
                             "overflow_to_737_p50_k": round(max(0.0, (1 - r["share_737"]) * tot - carried["p50"]), 1)}
        out.append({"t": b["t"], "label": b["label"], "fy": b["fy"], "routes": rows, "total_p50": round(sum(v["p50"] for v in rows.values()), 1),
                    "all_types_p50": alls, "all_types_total_p50": round(sum(alls.values()), 1), "wide": wide})
    return out


def min_aircraft(P: list[dict], need_pax: dict[str, float], seats: int, lf_t: float, stretch: float = 1.0, fixed_total: int | None = None) -> dict:
    """Smallest number of aircraft over the patterns that carries every route's passengers at the
    target L/F (integer programme). With fixed_total the total is held and spilled passengers are
    minimised instead (the re-mix lever)."""
    cap = {p["id"]: {r: n * seats * DAYS * stretch / 1e3 for r, n in p["legs"].items()} for p in P}   # thousand pax a month one aircraft on the pattern carries per route
    prob = pulp.LpProblem("routes", pulp.LpMinimize)
    x = {p["id"]: pulp.LpVariable(f"x_{p['id']}", lowBound=0, cat="Integer") for p in P}
    spill = {r: pulp.LpVariable(f"s_{r.replace('-', '_')}", lowBound=0) for r in need_pax}
    if fixed_total is None:
        prob += pulp.lpSum(x.values()) + 1e-3 * pulp.lpSum(spill.values())
        for r, pax in need_pax.items():
            prob += pulp.lpSum(x[p] * cap[p].get(r, 0) for p in x) >= pax / lf_t   # spill forced to 0 by the constraint below
            prob += spill[r] == 0
    else:
        prob += pulp.lpSum(spill.values())
        prob += pulp.lpSum(x.values()) == fixed_total
        for r, pax in need_pax.items():
            prob += pulp.lpSum(x[p] * cap[p].get(r, 0) for p in x) * lf_t + spill[r] >= pax
    prob.solve(pulp.HiGHS(msg=False))
    xs = {p: int(round(v.value() or 0)) for p, v in x.items()}
    return {"aircraft": sum(xs.values()), "by_pattern": xs, "spill_pax_k": {r: round(v.value() or 0, 1) for r, v in spill.items()}}


def per_route(P: list[dict], xs: dict[str, int]) -> dict[str, float]:
    """Aircraft attributed to each route: each pattern's aircraft split by block hours."""
    bh = {}
    for p in P:
        tot = sum(p["legs"].values())
        for r, n in p["legs"].items():
            bh[r] = bh.get(r, 0.0) + xs.get(p["id"], 0) * n / tot
    return {r: round(v, 2) for r, v in bh.items()}


def score_assignment(P: list[dict], xs: dict[str, int], need_pax: dict[str, float], seats: int, lf_t: float, available: float = 1.0) -> dict:
    """The fixed assignment against the month's demand: L/F and spill per route. `available` is the
    share of the assigned aircraft that can fly (checks and engine waits take the rest pro rata)."""
    out = {}
    for r, pax in need_pax.items():
        cap = sum(xs.get(p["id"], 0) * p["legs"].get(r, 0) for p in P) * seats * DAYS / 1e3 * available
        lf = pax / cap if cap else float("inf")
        out[r] = {"capacity_pax_k": round(cap, 1), "lf": round(lf, 3), "spill_pax_k": round(max(0.0, pax - cap * lf_t), 1)}
    return out


def build(cid: str, D: dict, band: list[dict], checks_by_month: dict[int, int], fleet_total: int, engine_wait_by_t: dict[int, int] | None = None) -> dict:
    R = load()
    P = pattern_table(R)
    C = D["companies"][cid]; lf_t = D["assumptions"]["lf_capacity_threshold"]
    seats, yld = C["seats_737_800"], C["yield_yen_per_rpk"]
    km = {r["id"]: r["km"] for r in R["routes"]}
    dem = route_demand(R, D, cid, band)
    # the yearly version: the smallest pattern mix that carries the first 12 months' average 737 demand
    first = dem[:12]
    avg = {r: sum(d["routes"][r]["p50"] for d in first) / len(first) for r in first[0]["routes"]}
    version = min_aircraft(P, avg, seats, lf_t)
    assign = version["by_pattern"]
    n_trunk = sum(assign.values())
    rows = []
    for d in dem:
        m = int(d["label"][5:])
        need = {q: min_aircraft(P, {r: v[q] for r, v in d["routes"].items()}, seats, lf_t) for q in ("p10", "p50", "p90")}
        checks = round(checks_by_month[m] * n_trunk / fleet_total, 1)             # the trunk's share of the airframe checks
        wait = (engine_wait_by_t or {}).get(d["t"], 0)
        usable = round(n_trunk - checks - wait, 1)
        fixed = score_assignment(P, assign, {r: v["p50"] for r, v in d["routes"].items()}, seats, lf_t, available=math.floor(usable) / n_trunk)
        remix = min_aircraft(P, {r: v["p50"] for r, v in d["routes"].items()}, seats, lf_t, fixed_total=int(math.floor(usable)))
        spill_fixed = sum(v["spill_pax_k"] for v in fixed.values())
        spill_remix = sum(remix["spill_pax_k"].values())
        rows.append({"t": d["t"], "label": d["label"], "fy": d["fy"], "pax_k_p50": d["total_p50"],
                     "need_p10": need["p10"]["aircraft"], "need_p50": need["p50"]["aircraft"], "need_p90": need["p90"]["aircraft"],
                     "need_by_route_p50": per_route(P, need["p50"]["by_pattern"]), "need_by_pattern_p50": need["p50"]["by_pattern"],
                     "assigned": n_trunk, "in_checks": checks, "waiting_engine": wait, "usable": usable,
                     "gap_p50": round(usable - need["p50"]["aircraft"], 1), "gap_p90": round(usable - need["p90"]["aircraft"], 1), "short_p90": need["p90"]["aircraft"] > usable,
                     "fixed_assignment": fixed, "spill_fixed_pax_k": round(spill_fixed, 1),
                     "remix": {"by_pattern": remix["by_pattern"], "spill_pax_k": round(spill_remix, 1)},
                     "lost_revenue_fixed_oku": round(sum(v["spill_pax_k"] * km[r] * yld * 1e3 / 1e8 for r, v in fixed.items()), 2)})
    # cycles: the trunk's aircraft fly their patterns; the others fly the company average
    cyc_trunk_day = sum(assign[p["id"]] * p["cycles_per_day"] for p in P) / n_trunk
    demo = dict(zip((p["id"] for p in P), R["companies"][cid]["assignment_demo"]))
    return {"routes": [{k: r[k] for k in ("id", "name", "pax_month_k", "block_h", "km", "share_737", "wide_types")} for r in R["routes"]], "patterns": P, "assignment": assign,
            "assignment_how": "年次の版：最初の 12 か月の 737 の需要（平均・p50）を目標搭乗率で運べる最小のパターンの組み合わせ",
            "assignment_demo": {"by_pattern": demo, "aircraft": sum(demo.values()), "note": "試作の割り当て（全旅客を 737 に載せた前提）。比較用"},
            "trunk_aircraft": n_trunk, "demand": dem, "rows": rows,
            "cycles_per_aircraft_day_trunk": round(cyc_trunk_day, 2), "hub": R["hub"],
            "how": {"need": "月ごと・分位ごとに、全航路の旅客を目標搭乗率で運べる最小の機数をパターン上の整数計画で解く（PuLP＋HiGHS）",
                    "usable": "割り当て − 機体整備で止まる機（幹線の按分）− エンジン待ち（羽田で止まる機）",
                    "types": "幹線の旅客は大型機と 737 で分ける。737 が運ぶのは 737 の分担 ＋ 大型機が搭乗率の上限を超えてあふれた分",
                    "remix": "割り当て総数を変えずにパターンの組み合わせだけ変えて、乗せられない旅客を最小にする",
                    "attribution": "航路ごとの機数はパターンの機数を便数で按分"},
            "assumptions": {"routes": "no_source: 旅客・飛行時間は航路ベースのデモの前提、季節の偏り・パターン・737 の分担は仮定",
                            "wide_lf": {"base": R["wide_lf_base"], "cap": R["wide_lf_cap"]}, "day_cap_h": R["day_block_cap_h"], "turnaround_h": R["turnaround_h"],
                            "engine_swaps": "エンジンの交換と予備は羽田だけ。エンジン待ちの機は羽田で止まる"}}


def levers(trunk: dict, others_slack: dict[int, float], D: dict, cid: str, norms: dict, growth_params: dict) -> list[dict]:
    """For a short month (p90): move aircraft in from the other routes, re-mix, stretch the day, wet-lease, spill."""
    C = D["companies"][cid]; lf_t = D["assumptions"]["lf_capacity_threshold"]
    P = trunk["patterns"]; seats = C["seats_737_800"]; yld = C["yield_yen_per_rpk"]
    km = {r["id"]: r["km"] for r in trunk["routes"]}
    run_cycles = growth_params.get("run_cycles", 11753); cost_visit = growth_params.get("cost_per_visit_k", 8067)
    mx_k_per_cycle = 2 * cost_visit / run_cycles
    cyc_day = trunk["cycles_per_aircraft_day_trunk"]
    out = []
    for r, d in zip(trunk["rows"], trunk["demand"]):
        short = max(0.0, r["need_p90"] - r["usable"])
        if short <= 0:
            continue
        from_others = min(short, max(0.0, others_slack.get(r["t"], 0.0)))
        rest = short - from_others
        remix_gain = max(0.0, r["spill_fixed_pax_k"] - r["remix"]["spill_pax_k"])
        stretch = min_aircraft(P, {k: v["p90"] for k, v in d["routes"].items()}, seats, lf_t, stretch=DAY_STRETCH)
        by_stretch = min(rest, max(0.0, r["need_p90"] - stretch["aircraft"]))
        rest2 = rest - by_stretch
        extra_cycles = by_stretch * cyc_day * DAYS                 # freeing one aircraft by stretching days costs about one aircraft-month of cycles
        pax90 = sum(v["p90"] for v in d["routes"].values())
        avg_km = sum(km[k] * v["p90"] for k, v in d["routes"].items()) / pax90
        rev_k_per_ac_month = pax90 / r["need_p90"] * avg_km * yld / USD_JPY   # thousand pax x km x yen / (yen per $) = k$
        out.append({"label": r["label"], "short_aircraft_p90": round(short, 1), "levers": [
            {"lever": "その他の路線から回す", "aircraft": round(from_others, 1), "cost_k": 0, "engine_effect": "会社全体のサイクルは変わらない（飛ぶ場所が変わるだけ）", "limit": "その他の路線の余り（p50）まで"},
            {"lever": "パターンの組み替え", "aircraft": 0, "cost_k": 0, "engine_effect": "短い区間のパターンが増えればサイクルが増える", "limit": f"乗せられない旅客を {remix_gain:.1f} 千人減らす（機数は変えない）"},
            {"lever": "1 日の飛び方を伸ばす", "aircraft": round(by_stretch, 1), "cost_k": round(extra_cycles * mx_k_per_cycle), "engine_effect": f"エンジン・サイクル +{extra_cycles:,.0f}（入場の前倒し {extra_cycles / run_cycles:.2f} 件分）", "limit": f"1 日 ×{DAY_STRETCH}（乗員・門限）"},
            {"lever": "機体を借りる（ウェットリース）", "aircraft": round(math.ceil(rest2 - 1e-9), 1) if rest2 > 0 else 0, "cost_k": round(math.ceil(rest2 - 1e-9) * WET_LEASE_K_PER_AC_MONTH) if rest2 > 0 else 0, "engine_effect": "自社エンジンに影響なし", "limit": "no_source: 850 k$/機・月"},
            {"lever": "見送る（乗せられない旅客）", "aircraft": round(rest2, 1), "cost_k": round(rest2 * rev_k_per_ac_month), "engine_effect": "なし", "limit": "失う売上 ＝ 機数 × 1 機の月の旅客 × 平均区間 × 単価（下限）"}]})
    return out


def peak_decision(trunk: dict, D: dict, cid: str, months: list[str], rule: str = "recent") -> dict:
    """The July question about the busy month(s): borrow n aircraft at the lease rate, or spill.
    Revenue recovered = spilled passengers under the fixed assignment that n more aircraft carry."""
    C = D["companies"][cid]; lf_t = D["assumptions"]["lf_capacity_threshold"]
    seats, yld = C["seats_737_800"], C["yield_yen_per_rpk"]
    km = {r["id"]: r["km"] for r in trunk["routes"]}
    out = []
    for r, d in zip(trunk["rows"], trunk["demand"]):
        if r["label"] not in months:
            continue
        short = max(0, math.ceil(r["need_p50"] - r["usable"] - 1e-9))
        lost = r["lost_revenue_fixed_oku"]
        n = short
        cost = n * WET_LEASE_K_PER_AC_MONTH * USD_JPY / 1e5
        # what n aircraft on the best pattern mix recover: re-solve spill with usable + n
        P = trunk["patterns"]
        with_n = min_aircraft(P, {k: v["p50"] for k, v in d["routes"].items()}, seats, lf_t, fixed_total=int(math.floor(r["usable"])) + n)
        spill_after = sum(with_n["spill_pax_k"].values())
        avg_km = sum(km[k] * v["p50"] for k, v in d["routes"].items()) / sum(v["p50"] for v in d["routes"].values())
        recovered = max(0.0, (r["remix"]["spill_pax_k"] - spill_after)) * 1e3 * avg_km * yld / 1e8
        out.append({"label": r["label"], "borrow_aircraft": n, "lease_cost_oku": round(cost, 2), "revenue_recovered_oku": round(recovered, 2),
                    "net_oku": round(recovered - cost, 2), "lost_if_not_oku": round(lost, 2), "decision": "借りる" if recovered - cost > 0 else "借りない（見送る）"})
    return {"rule": rule, "months": out, "note": "借りる機数 ＝ p50 の要る機数 − 使える機数（切り上げ）。取り戻す収入は、割り当てを組み替えた上でさらに n 機足したときに減る乗せられない旅客 × 平均区間 × 単価。費用はウェットリース（no_source）"}
