#!/usr/bin/env python3
"""Route layer with several aircraft types: demand per trunk route -> which type flies which
day pattern -> aircraft per type -> engines per type.

An aircraft that flies is somewhere else afterwards, so the unit of planning is a pattern: a
day's chain of legs that leaves the hub (HND) and returns to it, the next leg departing from
where the previous one landed. `data/routes_trunk.json` holds the five trunk routes (one-way
monthly passengers of all types, block hours, a seasonal deviation per route normalised so the
whole follows the market's seasonal index), the patterns, and per company the aircraft types
that fly them: seats, cost per block hour, turnaround, and how many aircraft of each widebody
type these routes get (the rest flies international or other domestic routes). The 737-800
shares its whole fleet between the trunk and the regional network.

Each month is a fleet assignment problem (Hane et al. 1995, reduced to day patterns): integer
aircraft per (type, pattern) within each type's available aircraft, 737 wet-lease aircraft,
and spilled passengers, minimising operating cost + lease + lost revenue, with every route's
capacity at the target load factor covering what is carried, and the legs a day on each route
within the hub's slots (the slots are what makes the widebodies worth flying on the trunk). Solved with PuLP + HiGHS for the
p10/p50/p90 demand. A pattern is open to a type only if its day (block + turnarounds) fits.

The yearly version is the same problem on the first 12 months' average demand with the 737
unconstrained; the 737's trunk share of that solution fixes how much of the company's 737
demand is regional. In a month the 737 may use on the trunk what the regional network and the
airframe checks leave. Cycles per type come from the patterns flown; each type's utilisation
multiplier goes to plan_from_demand.build_fleet (types with a fleet file: 737, 767, 787).

Everything is synthetic; the route inputs are flagged no_source in the data file.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pulp

import demand as demand_mod

HERE = Path(__file__).resolve().parent
ROUTES = HERE / "data" / "routes_trunk.json"
DAYS = 365 / 12
USD_JPY = 157.0
LF_MAX = 0.95          # the load factor a flight can reach in operation (booked out); the plan uses the target (0.85)


def load() -> dict:
    return json.loads(ROUTES.read_text(encoding="utf-8"))


def _route_of(leg: str, ids: set[str]) -> str:
    a, b = leg.split("-")
    return f"{a}-{b}" if f"{a}-{b}" in ids else f"{b}-{a}"


def types_of(R: dict, cid: str) -> list[dict]:
    return R["companies"][cid]["types"]


def pattern_table(R: dict, types: list[dict] | None = None) -> list[dict]:
    """Legs per route, block hours, cycles per day, and which types can fly each pattern."""
    ids = {r["id"] for r in R["routes"]}
    bh = {r["id"]: r["block_h"] for r in R["routes"]}
    types = types or [{"type": "737", "turnaround_h": R.get("turnaround_h", 0.83)}]
    out = []
    for p in R["patterns"]:
        legs = {}
        for l in p["legs"]:
            legs[_route_of(l, ids)] = legs.get(_route_of(l, ids), 0) + 1
        block = sum(bh[_route_of(l, ids)] for l in p["legs"])
        day = {t["type"]: round(block + t["turnaround_h"] * (len(p["legs"]) - 1), 1) for t in types}
        ok = [t["type"] for t in types if day[t["type"]] <= R["day_block_cap_h"] and t["type"] not in p.get("types_excluded", [])]
        out.append({"id": p["id"], "name": p["name"], "legs": legs, "cycles_per_day": len(p["legs"]), "block_h": round(block, 1), "day_h": day,
                    "types": ok, "fits_day": bool(ok), "cycles_per_block_h": round(len(p["legs"]) / block, 2)})
    return out


def route_demand(R: dict, D: dict, cid: str, band: list[dict]) -> list[dict]:
    """Passengers per route per month, both directions, all types, p10/p50/p90. The route's seasonal
    deviation is normalised each month so the passenger-weighted whole equals the market's seasonal
    index; the trend and the band's relative width come from the company-level band."""
    idx = {c["month"]: c["demand_index"] for c in demand_mod.market_view(D)["seasonal"]}
    scale = R["companies"][cid]["scale"]
    w = {r["id"]: r["pax_month_k"] for r in R["routes"]}
    W = sum(w.values())
    out = []
    for b in band:
        m = int(b["label"][5:])
        norm = sum(w[r["id"]] * r["season_dev"][m - 1] for r in R["routes"]) / W
        rows = {}
        for r in R["routes"]:
            tot = r["pax_month_k"] * 2 * scale * idx[m] * r["season_dev"][m - 1] / norm * b["trend"]
            rows[r["id"]] = {"p10": round(tot * b["p10"] / b["p50"], 1), "p50": round(tot, 1), "p90": round(tot * b["p90"] / b["p50"], 1)}
        out.append({"t": b["t"], "label": b["label"], "fy": b["fy"], "routes": rows, "total_p50": round(sum(v["p50"] for v in rows.values()), 1)})
    return out


def assign(R: dict, P: list[dict], types: list[dict], pax: dict[str, float], avail: dict[str, float | None], lf_t: float, yld: float,
           lease: bool = True, stretch: float = 1.0, cid: str | None = None, lf_cap: float | None = None) -> dict:
    """One month's fleet assignment. avail[type] None = unconstrained. Returns aircraft per (type,
    pattern), lease aircraft per pattern, carried and spilled passengers per route, costs (k$)."""
    km = {r["id"]: r["km"] for r in R["routes"]}
    T = {t["type"]: t for t in types}
    prob = pulp.LpProblem("fam", pulp.LpMinimize)
    x = {(t, p["id"]): pulp.LpVariable(f"x_{t}_{p['id']}", lowBound=0, cat="Integer") for p in P for t in p["types"]}
    lt = R["lease"]["type"]
    l = {p["id"]: pulp.LpVariable(f"l_{p['id']}", lowBound=0, cat="Integer") for p in P if lease and lt in p["types"]}
    c = {r: pulp.LpVariable(f"c_{r.replace('-', '_')}", lowBound=0, upBound=pax[r]) for r in pax}
    bh = {p["id"]: p["block_h"] for p in P}
    op = pulp.lpSum(x[k] * T[k[0]]["cost_per_block_h_k"] * bh[k[1]] * DAYS for k in x)
    ls = pulp.lpSum(v * (R["lease"]["k_per_aircraft_month"] + T[lt]["cost_per_block_h_k"] * bh[k] * DAYS) for k, v in l.items())   # lease on top of the operating cost
    rev = {r: km[r] * yld / USD_JPY for r in pax}                                  # k$ per thousand passengers
    spill = pulp.lpSum((pax[r] - c[r]) * rev[r] for r in pax)
    prob += op + ls + spill
    for r in pax:
        seats = pulp.lpSum(x[(t, p["id"])] * T[t]["seats"] * p["legs"].get(r, 0) for p in P for t in p["types"]) \
            + pulp.lpSum(l[p["id"]] * T[lt]["seats"] * p["legs"].get(r, 0) for p in P if p["id"] in l)
        prob += seats * DAYS * stretch / 1e3 * (lf_cap or lf_t) >= c[r]
    scale = R["companies"][cid]["scale"] if cid else 1.0
    for r in R["routes"]:                                                            # hub slots: legs a day on the route
        rid = r["id"]
        prob += pulp.lpSum(x[(t, p["id"])] * p["legs"].get(rid, 0) for p in P for t in p["types"]) \
            + pulp.lpSum(l[p["id"]] * p["legs"].get(rid, 0) for p in P if p["id"] in l) <= math.floor(r["slots_legs_per_day"] * scale + 1e-9)
    for t in T:
        if avail.get(t) is not None:
            prob += pulp.lpSum(v for k, v in x.items() if k[0] == t) <= max(0, math.floor(avail[t] + 1e-9))
    prob.solve(pulp.HiGHS(msg=False))
    xs = {k: int(round(v.value() or 0)) for k, v in x.items()}
    ls_ = {k: int(round(v.value() or 0)) for k, v in l.items()}
    by_type = {t: sum(v for k, v in xs.items() if k[0] == t) for t in T}
    carried = {r: round(c[r].value() or 0, 1) for r in pax}
    sp = {r: round(pax[r] - carried[r], 1) for r in pax}
    cap = {}
    for r in pax:
        s = sum(xs[(t, p["id"])] * T[t]["seats"] * p["legs"].get(r, 0) for p in P for t in p["types"]) + sum(ls_.get(p["id"], 0) * T[lt]["seats"] * p["legs"].get(r, 0) for p in P)
        cap[r] = s * DAYS * stretch / 1e3
    seats_by_type_route = {t: {r: round(sum(xs.get((t, p["id"]), 0) * T[t]["seats"] * p["legs"].get(r, 0) for p in P if t in p["types"]) * DAYS / 1e3, 1) for r in pax} for t in T}
    cyc = {t: sum(xs.get((t, p["id"]), 0) * p["cycles_per_day"] for p in P if t in p["types"]) for t in T}
    return {"by_type": by_type, "by_type_pattern": {f"{k[0]}:{k[1]}": v for k, v in xs.items() if v}, "lease": sum(ls_.values()), "lease_by_pattern": {k: v for k, v in ls_.items() if v},
            "carried_pax_k": carried, "spill_pax_k": sp, "spill_total_pax_k": round(sum(sp.values()), 1),
            "lf": {r: round(carried[r] / cap[r], 3) if cap[r] else None for r in pax}, "seats_k_by_type": seats_by_type_route,
            "cycles_per_day_by_type": cyc, "lease_cycles_per_day": sum(ls_.get(p["id"], 0) * p["cycles_per_day"] for p in P),
            "slots_used": {r["id"]: sum(xs.get((t, p["id"]), 0) * p["legs"].get(r["id"], 0) for p in P for t in p["types"]) + sum(ls_.get(p["id"], 0) * p["legs"].get(r["id"], 0) for p in P) for r in R["routes"]},
            "cost_k": {"operating": round(pulp.value(op)), "lease": round(pulp.value(ls)) if l else 0, "lost_revenue": round(sum(sp[r] * rev[r] for r in pax))}}


def per_route(P: list[dict], by_type_pattern: dict[str, int]) -> dict[str, float]:
    """Aircraft attributed to each route: each pattern's aircraft split by legs."""
    legs = {p["id"]: p["legs"] for p in P}
    out = {}
    for k, n in by_type_pattern.items():
        pid = k.split(":")[1]; tot = sum(legs[pid].values())
        for r, c in legs[pid].items():
            out[r] = out.get(r, 0.0) + n * c / tot
    return {r: round(v, 2) for r, v in out.items()}


def build(cid: str, D: dict, band: list[dict], ctx: dict) -> dict:
    """ctx: checks_rate[type][month] (share of that type's aircraft in airframe checks), regional
    737 need by t (callable after the version), engine waits by t for the 737, 737 fleet total."""
    R = load()
    types = types_of(R, cid)
    P = pattern_table(R, types)
    lf_t = D["assumptions"]["lf_capacity_threshold"]; yld = D["companies"][cid]["yield_yen_per_rpk"]
    km = {r["id"]: r["km"] for r in R["routes"]}
    dem = route_demand(R, D, cid, band)
    first = dem[:12]
    avg = {r: sum(d["routes"][r]["p50"] for d in first) / len(first) for r in first[0]["routes"]}
    wide_avail = {t["type"]: t["trunk_aircraft"] for t in types if t["trunk_aircraft"] is not None}   # checks are covered by the type's whole fleet
    version = assign(R, P, types, avg, {**wide_avail, "737": None}, lf_t, yld, lease=False, cid=cid)
    v737_rpk = sum(version["seats_k_by_type"]["737"][r] * lf_t * km[r] for r in avg) * 1e3 / 1e6     # million RPK a month the 737 flies on the trunk in the version
    trunk_share = ctx["set_trunk_737_rpk"](v737_rpk)                                                  # the caller fixes the regional split and returns the trunk share
    rows = []
    for d in dem:
        m = int(d["label"][5:]); t = d["t"]
        av = {}
        for ty in types:
            k = ty["type"]
            if ty["trunk_aircraft"] is None:
                av[k] = ctx["fleet_737"] * (1 - ctx["checks_rate"][k][m]) - ctx["regional_need"](t) - ctx["engine_wait"].get(t, 0)
            else:
                av[k] = ty["trunk_aircraft"]                                             # the widebody fleet (international included) covers its checks
        sol = {q: assign(R, P, types, {r: v[q] for r, v in d["routes"].items()}, av, lf_t, yld, cid=cid, lf_cap=LF_MAX) for q in ("p10", "p50", "p90")}
        nolease = assign(R, P, types, {r: v["p50"] for r, v in d["routes"].items()}, av, lf_t, yld, lease=False, cid=cid, lf_cap=LF_MAX)
        s = sol["p50"]
        rows.append({"t": t, "label": d["label"], "fy": d["fy"], "pax_k_p50": d["total_p50"],
                     "available": {k: round(v, 1) for k, v in av.items()},
                     "used_p50": s["by_type"], "used_p90": sol["p90"]["by_type"], "used_p10": sol["p10"]["by_type"],
                     "lease_p10": sol["p10"]["lease"], "lease_p50": s["lease"], "lease_p90": sol["p90"]["lease"],
                     "spill_p50_pax_k": s["spill_total_pax_k"], "spill_p90_pax_k": sol["p90"]["spill_total_pax_k"],
                     "carried_p50_pax_k": round(sum(s["carried_pax_k"].values()), 1), "carried_p90_pax_k": round(sum(sol["p90"]["carried_pax_k"].values()), 1),
                     "carried_p50_rpk_m": round(sum(v * km[r] for r, v in s["carried_pax_k"].items()) / 1e3, 1), "carried_p90_rpk_m": round(sum(v * km[r] for r, v in sol["p90"]["carried_pax_k"].items()) / 1e3, 1),
                     "short_p90": sol["p90"]["lease"] > 0 or sol["p90"]["spill_total_pax_k"] > 0.5,
                     "lf_p50": s["lf"], "slots_used_p50": s["slots_used"], "by_type_pattern_p50": s["by_type_pattern"], "aircraft_by_route_p50": per_route(P, s["by_type_pattern"]),
                     "cost_k_p50": s["cost_k"], "cycles_per_day_p50": s["cycles_per_day_by_type"], "lease_cycles_per_day_p50": s["lease_cycles_per_day"],
                     "no_lease_p50": {"spill_pax_k": nolease["spill_total_pax_k"], "lost_revenue_k": nolease["cost_k"]["lost_revenue"], "by_type": nolease["by_type"]}})
    return {"routes": [{k: r[k] for k in ("id", "name", "pax_month_k", "block_h", "km")} for r in R["routes"]], "patterns": P, "types": types,
            "version": {"by_type": version["by_type"], "by_type_pattern": version["by_type_pattern"], "lf": version["lf"], "trunk_737_rpk_million": round(v737_rpk, 1),
                        "trunk_share_of_737_rpk": trunk_share, "how": "最初の 12 か月の平均の需要（p50）で解いた機材割当。大型機はこの 5 航路に回る機数（整備で止まる分を年平均で引く）まで、737 は上限なし。737 の幹線分がこれで決まり、残りが地方路線"},
            "demand": dem, "rows": rows, "hub": R["hub"],
            "how": {"assignment": "月ごと・分位ごとに、機種 × パターンの機数（整数）・737 のウェットリース・乗せられない旅客を、運航費 ＋ リース費 ＋ 失う売上 が最小になるよう解く（機材割当モデル、PuLP＋HiGHS）。各航路は目標搭乗率で運べる座席の範囲で運ぶ",
                    "lf": f"年次の版は目標搭乗率 {0.85} で立てる。月の運航では 1 便に {LF_MAX} まで乗せられる（それを超えた旅客が乗せられない旅客）",
                    "available": "大型機：この 5 航路に回る機数（機体整備は国際線を含む機種全体でまかなう）。737：全機 − 機体整備 − 地方路線に要る機数 − エンジン待ち（羽田で止まる機）",
                    "attribution": "航路ごとの機数はパターンの機数を便数で按分", "reference": R.get("fleet_assignment_ref")},
            "assumptions": {"routes": "no_source: 旅客・飛行時間は航路ベースのデモの前提。機種ごとの座席・運航費・この 5 航路に回る機数、季節の偏り、パターンは仮定",
                            "lease": R["lease"], "day_cap_h": R["day_block_cap_h"], "engine_swaps": "エンジンの交換と予備は羽田だけ。エンジン待ちの機は羽田で止まる"}}
