#!/usr/bin/env python3
"""Airline layer on the trunk routes: route demand -> which aircraft type flies which day pattern
-> aircraft per type -> engines per type, inside the slots the airport layer gives.

An aircraft that flies is somewhere else afterwards, so the unit of planning is a pattern: a day's
chain of legs that leaves the hub (HND) and returns to it. `data/routes_trunk.json` holds the five
trunk routes with the whole market's passengers (2024, public), block hours, a seasonal deviation
per route normalised so the whole follows the market's seasonal index, the patterns, and per
company the aircraft types (seats, cost per block hour, turnaround, how many may fly the trunk).

The airport layer (airport_slots.py) supplies, per company: the round trips a day it flies on the
four hub trunk routes (its slots there), the per-route bounds, the use-it-or-lose-it floor, and the
share of each route's passengers its frequencies win against the other carriers.

Each month is a fleet assignment problem (Hane et al. 1995, reduced to day patterns): integer
aircraft per (type, pattern), 737 wet-lease aircraft and spilled passengers, minimising operating
cost + lease + lost revenue; every route carries at most its seats x the operating load factor, its
round trips stay within the bounds, and the hub routes use their slots. Solved with PuLP + HiGHS
for p10/p50/p90 demand. The yearly version solves the first 12 months' average at the planning load
factor; its frequencies feed back into the share (a few fixed-point rounds), so a slot scenario
moves demand as well as capacity.

Everything is synthetic except the inputs with a source in the data files.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pulp

import airport_slots as ap
import demand as demand_mod

HERE = Path(__file__).resolve().parent
ROUTES = HERE / "data" / "routes_trunk.json"
DAYS = 365 / 12
USD_JPY = 157.0
MIP_GAP = 0.002          # relative optimality gap accepted from the solver
CANCEL_K_PER_ROUND_TRIP_MONTH = 5000.0   # penalty for flying fewer round trips than the slots/bounds ask (k$ per round trip a day, a month): only when no aircraft can fly them.
                                         # About a month of what one hub round trip is worth a year in the slot scenarios (10-13 oku yen); assumption
MIP_TIME_S = 15          # time limit per monthly solve (a feasible solution found by then is used)


def spill_cv(R: dict) -> float:
    """Spread of one flight's demand around the route's mean flight demand: time of day, day of week,
    and booking noise combined (independent parts add in squares)."""
    m = R["spill_model"]
    return math.sqrt(m["cv_within_band"] ** 2 + m["cv_day_of_week"] ** 2 + m["cv_booking"] ** 2)


def leg_bands(R: dict, legs: list[str]) -> list[str]:
    """Peak or off-peak for each leg of a day pattern, by its departure hour."""
    m = R["spill_model"]; ids = {r["id"] for r in R["routes"]}; bh = {r["id"]: r["block_h"] for r in R["routes"]}
    t = m["first_departure_h"]; out = []
    for l in legs:
        out.append("peak" if any(a <= t < b for a, b in m["peak_hours"]) else "off")
        t += bh[_route_of(l, ids)] + m["timing_turnaround_h"]
    return out


def band_means(R: dict, pax: dict[str, float], legs_band: dict[str, dict[str, float]]) -> dict[tuple, float]:
    """Mean passengers per flight by route and band, from the month's passengers and the legs a day
    flown in each band (peak flights see peak_to_offpeak times the off-peak mean)."""
    k = R["spill_model"]["peak_to_offpeak_demand"]
    out = {}
    for r, v in pax.items():
        lp, lo = legs_band[r].get("peak", 0.0), legs_band[r].get("off", 0.0)
        denom = (k * lp + lo) * DAYS
        off = v * 1e3 / denom if denom > 0 else 0.0
        out[(r, "peak")], out[(r, "off")] = k * off, off
    return out


def carried_share(x: float, cv: float) -> float:
    """E[min(u, x)] for flight demand u ~ lognormal with mean 1 and the given cv, x = seats / mean demand.
    A flight carries min(demand, seats); this is the expected carried passengers per unit of mean demand."""
    if x <= 0:
        return 0.0
    sg2 = math.log(1 + cv * cv); sg = math.sqrt(sg2); mu = -sg2 / 2
    Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
    lx = math.log(x)
    return Phi((lx - mu - sg2) / sg) + x * (1 - Phi((lx - mu) / sg))


def fare_yen(R: dict, yld: float) -> dict[str, float]:
    """Fare per passenger by route: proportional to distance^exponent, scaled so the passenger-weighted
    average yield equals the company's yield (yen per passenger-km)."""
    e = R.get("fare_taper", {}).get("exponent", 1.0)
    w = {r["id"]: r["market_pax_2024"] for r in R["routes"]}; km = {r["id"]: r["km"] for r in R["routes"]}
    scale = yld * sum(w[r] * km[r] for r in w) / sum(w[r] * km[r] ** e for r in w)
    return {r: scale * km[r] ** e for r in w}


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
    types = types or [{"type": "737", "turnaround_h": 0.83}]
    out = []
    for p in R["patterns"]:
        legs, lb = {}, {}
        for l, b in zip(p["legs"], leg_bands(R, p["legs"])):
            r = _route_of(l, ids)
            legs[r] = legs.get(r, 0) + 1
            lb.setdefault(r, {"peak": 0, "off": 0})[b] += 1
        block = sum(bh[_route_of(l, ids)] for l in p["legs"])
        day = {t["type"]: round(block + t["turnaround_h"] * (len(p["legs"]) - 1), 1) for t in types}
        ok = [t["type"] for t in types if day[t["type"]] <= R["day_block_cap_h"] and t["type"] not in p.get("types_excluded", [])]
        out.append({"id": p["id"], "name": p["name"], "legs": legs, "legs_band": lb, "cycles_per_day": len(p["legs"]), "block_h": round(block, 1), "day_h": day,
                    "types": ok, "fits_day": bool(ok), "cycles_per_block_h": round(len(p["legs"]) / block, 2)})
    return out


def route_demand(R: dict, D: dict, band: list[dict], share: dict[str, float], to_start: float) -> list[dict]:
    """The company's passengers per route per month, both directions, p10/p50/p90: the market's 2024
    passengers grown to the start (to_start), times the company's share, the seasonal shape and the
    trend; the band's relative width comes from the company-level band."""
    idx = {c["month"]: c["demand_index"] for c in demand_mod.market_view(D)["seasonal"]}
    w = {r["id"]: r["market_pax_2024"] for r in R["routes"]}
    W = sum(w.values())
    out = []
    for b in band:
        m = int(b["label"][5:])
        norm = sum(w[r["id"]] * r["season_dev"][m - 1] for r in R["routes"]) / W
        rows, market = {}, {}
        for r in R["routes"]:
            mk = r["market_pax_2024"] / 12 / 1e3 * to_start * idx[m] * r["season_dev"][m - 1] / norm * b["trend"]   # thousand pax a month, both directions
            tot = mk * share[r["id"]]
            market[r["id"]] = round(mk, 1)
            rows[r["id"]] = {"p10": round(tot * b["p10"] / b["p50"], 1), "p50": round(tot, 1), "p90": round(tot * b["p90"] / b["p50"], 1)}
        out.append({"t": b["t"], "label": b["label"], "fy": b["fy"], "routes": rows, "market_p50": market, "total_p50": round(sum(v["p50"] for v in rows.values()), 1)})
    return out


def scale_demand(dem: list[dict], scale: dict | None) -> list[dict]:
    """The route's passengers (every quantile) times scale[route]: a market that shrinks or grows for
    a reason outside the airline (e.g. the passengers a new rail line takes)."""
    if not scale:
        return dem
    out = []
    for d in dem:
        rows = {r: ({q: round(v * scale.get(r, 1.0), 1) for q, v in x.items()}) for r, x in d["routes"].items()}
        out.append({**d, "routes": rows, "market_p50": {r: round(v * scale.get(r, 1.0), 1) for r, v in d["market_p50"].items()},
                    "total_p50": round(sum(x["p50"] for x in rows.values()), 1)})
    return out


def assign(R: dict, P: list[dict], types: list[dict], pax: dict[str, float], avail: dict[str, float | None], mu: dict[str, float], yld: float,
           slots: dict, lease: bool = True, gap: float = MIP_GAP, time_s: float = MIP_TIME_S,
           fare_mult: dict[str, float] | None = None, elasticity: float = 0.0) -> dict:
    """One month's fleet assignment. avail[type] None = unconstrained. slots: {"bounds": {route: (lo, hi)}
    round trips a day, "budget": hub trunk round trips, "use_min": floor share of the budget}.
    fare_mult: the route's fare times this; its passengers (and the mean per flight) follow a linear
    demand curve through today's fare with the given elasticity there: x (1 + elasticity (m - 1)).
    (Constant elasticity would make an inelastic market raise fares without end.)"""
    if fare_mult:
        f = {r: max(0.0, 1 + elasticity * (fare_mult.get(r, 1.0) - 1)) for r in pax}
        pax = {r: v * f[r] for r, v in pax.items()}
        mu = {k: v * f[k[0]] for k, v in mu.items()}
    km = {r["id"]: r["km"] for r in R["routes"]}
    T = {t["type"]: t for t in types}
    prob = pulp.LpProblem("fam", pulp.LpMinimize)
    x = {(t, p["id"]): pulp.LpVariable(f"x_{t.replace('-', '_')}_{p['id']}", lowBound=0, cat="Integer") for p in P for t in p["types"]}
    lt = R["lease"]["type"]
    l = {p["id"]: pulp.LpVariable(f"l_{p['id']}", lowBound=0, cat="Integer") for p in P if lease and lt in p["types"]}
    c = {r: pulp.LpVariable(f"c_{r.replace('-', '_')}", lowBound=0, upBound=pax[r]) for r in pax}
    bh = {p["id"]: p["block_h"] for p in P}
    op = pulp.lpSum(x[k] * T[k[0]]["cost_per_block_h_k"] * bh[k[1]] * DAYS for k in x)
    ls = pulp.lpSum(v * (R["lease"]["k_per_aircraft_month"] + T[lt]["cost_per_block_h_k"] * bh[k] * DAYS) for k, v in l.items())
    fare = fare_yen(R, yld)
    rev = {r: fare[r] * (fare_mult or {}).get(r, 1.0) / USD_JPY for r in pax}       # k$ per thousand passengers
    hub = [r for r in pax if r in ap.HUB_ROUTES]
    cut = {r: pulp.LpVariable(f"u_{r.replace('-', '_')}", lowBound=0) for r in pax}                 # round trips a day below the route's floor (cancelled)
    cut_hub = pulp.LpVariable("u_hub", lowBound=0)                                                  # round trips a day below the slot-use floor
    prob += op + ls + pulp.lpSum((pax[r] - c[r]) * rev[r] for r in pax) + CANCEL_K_PER_ROUND_TRIP_MONTH * (pulp.lpSum(cut.values()) + cut_hub)
    legs = {r: pulp.lpSum(x[(t, p["id"])] * p["legs"].get(r, 0) for p in P for t in p["types"]) + pulp.lpSum(l[p["id"]] * p["legs"].get(r, 0) for p in P if p["id"] in l) for r in pax}
    cv = spill_cv(R)
    # what one leg a day of type t carries on route r in a month (thousand pax): mean flight demand x E[min(u, seats/mean)]
    kc = {(t, r, b): (mu[(r, b)] * carried_share(T[t]["seats"] / mu[(r, b)], cv) if mu[(r, b)] > 0 else 0.0) * DAYS / 1e3
          for t in T for r in pax for b in ("peak", "off")}
    def per_leg(t, p, r):
        lb = p["legs_band"].get(r, {})
        return sum(n * kc[(t, r, b)] for b, n in lb.items())
    for r in pax:
        can = pulp.lpSum(x[(t, p["id"])] * per_leg(t, p, r) for p in P for t in p["types"] if r in p["legs"]) \
            + pulp.lpSum(l[p["id"]] * per_leg(lt, p, r) for p in P if p["id"] in l and r in p["legs"])
        prob += can >= c[r]
        lo, hi = slots["bounds"][r]
        prob += legs[r] <= 2 * hi
        prob += legs[r] + 2 * cut[r] >= 2 * math.ceil(lo - 1e-9)
    prob += pulp.lpSum(legs[r] for r in hub) <= 2 * slots["budget"]
    prob += pulp.lpSum(legs[r] for r in hub) + 2 * cut_hub >= 2 * math.floor(slots["budget"] * slots["use_min"])
    for t in T:
        if avail.get(t) is not None:
            prob += pulp.lpSum(v for k, v in x.items() if k[0] == t) <= max(0, math.floor(avail[t] + 1e-9))
    prob.solve(pulp.HiGHS(msg=False, gapRel=gap, timeLimit=time_s))
    if prob.sol_status not in (pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible):
        raise RuntimeError(f"fleet assignment: no feasible solution ({pulp.LpStatus[prob.status]})")
    xs = {k: int(round(v.value() or 0)) for k, v in x.items()}
    ls_ = {k: int(round(v.value() or 0)) for k, v in l.items()}
    by_type = {t: sum(v for k, v in xs.items() if k[0] == t) for t in T}
    carried = {r: round(c[r].value() or 0, 1) for r in pax}
    sp = {r: round(pax[r] - carried[r], 1) for r in pax}
    legs_v = {r: sum(xs.get((t, p["id"]), 0) * p["legs"].get(r, 0) for p in P for t in p["types"]) + sum(ls_.get(p["id"], 0) * p["legs"].get(r, 0) for p in P) for r in pax}
    cap = {r: (sum(xs.get((t, p["id"]), 0) * T[t]["seats"] * p["legs"].get(r, 0) for p in P for t in p["types"]) + sum(ls_.get(p["id"], 0) * T[lt]["seats"] * p["legs"].get(r, 0) for p in P)) * DAYS / 1e3 for r in pax}
    cyc = {t: sum(xs.get((t, p["id"]), 0) * p["cycles_per_day"] for p in P if t in p["types"]) for t in T}
    lbs = {r: {b: sum((xs.get((t, p["id"]), 0) if t != "_lease" else 0) * p["legs_band"].get(r, {}).get(b, 0) for p in P for t in p["types"])
                  + sum(ls_.get(p["id"], 0) * p["legs_band"].get(r, {}).get(b, 0) for p in P) for b in ("peak", "off")} for r in pax}
    legs_by_type = {t: sum(xs.get((t, p["id"]), 0) * sum(p["legs"].values()) for p in P if t in p["types"]) for t in T}
    return {"by_type": by_type, "by_type_pattern": {f"{k[0]}:{k[1]}": v for k, v in xs.items() if v}, "lease": sum(ls_.values()), "lease_by_pattern": {k: v for k, v in ls_.items() if v},
            "carried_pax_k": carried, "spill_pax_k": sp, "spill_total_pax_k": round(sum(sp.values()), 1),
            "round_trips": {r: legs_v[r] / 2 for r in pax}, "legs_band": lbs, "legs_by_type": legs_by_type, "seats_k": {r: round(v, 1) for r, v in cap.items()},
            "avg_seats": {r: round(cap[r] * 1e3 / DAYS / legs_v[r]) if legs_v[r] else None for r in pax},
            "lf": {r: round(carried[r] / cap[r], 3) if cap[r] else None for r in pax},
            "cycles_per_day_by_type": cyc, "lease_cycles_per_day": sum(ls_.get(p["id"], 0) * p["cycles_per_day"] for p in P),
            "revenue_carried_k": round(sum(carried[r] * rev[r] for r in pax)),
            "cancelled_round_trips": round(sum(v.value() or 0 for v in cut.values()) + (cut_hub.value() or 0), 2),
            "cost_k": {"operating": round(pulp.value(op)), "lease": round(pulp.value(ls)) if l else 0, "lost_revenue": round(sum(sp[r] * rev[r] for r in pax))},
            "fare_mult": {r: (fare_mult or {}).get(r, 1.0) for r in pax}, "pax_after_fare_k": {r: round(v, 1) for r, v in pax.items()}}


def margin_k(sol: dict) -> float:
    """What the month earns on the trunk: revenue carried - operating cost - lease (k$)."""
    return sol["revenue_carried_k"] - sol["cost_k"]["operating"] - sol["cost_k"]["lease"]


def price(R: dict, P: list[dict], types: list[dict], pax: dict[str, float], avail: dict, mu: dict, yld: float, slots: dict,
          elasticity: float, lo: float = 0.8, hi: float = 1.5, step: float = 0.05, passes: int = 3) -> dict:
    """The fares that earn the most in one month, route by route (coordinate ascent on a grid of
    multipliers of today's fare, each candidate re-solving the fleet assignment so the aircraft and
    their gauge follow the passengers the fare leaves)."""
    cache = {}
    def solve(m):
        key = tuple(round(m[r], 3) for r in sorted(m))
        if key not in cache:
            cache[key] = assign(R, P, types, pax, avail, mu, yld, slots, fare_mult=m, elasticity=elasticity)
        return cache[key]
    m = {r: 1.0 for r in pax}
    best = solve(m)
    for _ in range(passes):
        moved = False
        for r in pax:
            for d in (step, -step):
                while lo - 1e-9 <= m[r] + d <= hi + 1e-9:
                    cand = {**m, r: round(m[r] + d, 3)}
                    sol = solve(cand)
                    if margin_k(sol) > margin_k(best) + 1e-6:
                        m, best, moved = cand, sol, True
                    else:
                        break
        if not moved:
            break
    best["fare_search_solves"] = len(cache)
    return best


def per_route(P: list[dict], by_type_pattern: dict[str, int]) -> dict[str, float]:
    """Aircraft attributed to each route: each pattern's aircraft split by legs."""
    legs = {p["id"]: p["legs"] for p in P}
    out = {}
    for k, n in by_type_pattern.items():
        pid = k.split(":")[1]; tot = sum(legs[pid].values())
        for r, c in legs[pid].items():
            out[r] = out.get(r, 0.0) + n * c / tot
    return {r: round(v, 2) for r, v in out.items()}


def available(types: list[dict], m: int, fleet_737_free: float) -> dict[str, float]:
    av = {}
    for ty in types:
        k = ty["type"]
        if ty["trunk_aircraft"] is None:
            av[k] = fleet_737_free
        else:
            av[k] = ty.get("trunk_aircraft_peak", ty["trunk_aircraft"]) if m in ty.get("peak_months", []) else ty["trunk_aircraft"]
    return av


def build(cid: str, D: dict, band: list[dict], ctx: dict, delta: float = 0.0, quantiles: tuple = ("p10", "p50", "p90"), detail: bool = True,
          fiscal_years: set | None = None, overrides: dict | None = None, dest: bool | dict = False, fares: dict | None = None,
          corridor: dict | None = None) -> dict:
    """ctx: checks_rate (737), regional need by t (callable after the version), engine waits by t,
    737 fleet total, to_start (2024 -> start growth), set_trunk_737_rpk (fixes the regional split).
    delta: the hub trunk slots added (+) or taken away (-) by a re-allocation scenario.
    overrides: {type: {field: value}} laid over the company's types (e.g. more widebodies on the trunk).
    dest: lay the destination airports' caps over the per-route bounds; the hub slots above their sum
    cannot be flown (reported as unusable). A dict {airport code: round trips} adds that much headroom
    at those airports (an expansion there).
    fares: {"elasticity": e, optional "lo"/"hi"/"step"} -- each month's p50 assignment also sets the fare
    by route (price); the yearly version keeps today's fares.
    corridor: a change on the ground that moves the trunk, {"market_scale": {route: x} (the route's
    whole market times x, e.g. passengers moving to rail), "bounds": {route: (lo, hi)} (round trips a
    day, still under the destination caps), "use_min": floor share of the hub slots (the freed slots
    go to routes outside the trunk), "rival_shift": {route: round trips} (the other carriers move
    their slots too)}."""
    R = load(); S = ap.load()
    cor = corridor or {}
    types = [{**t, **(overrides or {}).get(t["type"], {})} for t in types_of(R, cid)]
    P = pattern_table(R, types)
    yld = D["companies"][cid]["yield_yen_per_rpk"]
    km = {r["id"]: r["km"] for r in R["routes"]}
    caps = ap.destination_caps(S, cid, extra=dest if isinstance(dest, dict) else None) if dest else None
    slots = {"bounds": ap.bounds(S, cid, delta, caps), "budget": ap.trunk_budget(S, cid, delta), "use_min": cor.get("use_min", S["rules"]["use_min_share"])}
    for r, (lo, hi) in cor.get("bounds", {}).items():
        hi = min(hi, caps[r]) if caps and r in caps else hi
        slots["bounds"][r] = (min(lo, hi), hi)
    budget_hub = slots["budget"]
    reach = sum(slots["bounds"][r][1] for r in ap.HUB_ROUTES)
    if slots["budget"] > reach:                                                              # the other ends cannot take them all
        slots["budget"] = reach
    # the yearly version, with the share following the frequencies it flies (fixed point)
    freq = ap.current_freq(S, cid)
    pk = {r: 0.5 for r in freq}                                                              # share of a route's legs in the peak (first guess)
    if delta:
        scale = slots["budget"] / ap.trunk_budget(S, cid)
        freq = {r: (v * scale if r in ap.HUB_ROUTES else v) for r, v in freq.items()}
    rounds = []
    for _ in range(6):
        sh = ap.share(S, cid, freq, comp_delta=cor.get("rival_shift"))
        dem = scale_demand(route_demand(R, D, band, sh, ctx["to_start"]), cor.get("market_scale"))
        first = dem[:12]
        avg = {r: sum(d["routes"][r]["p50"] for d in first) / len(first) for r in first[0]["routes"]}
        av_v = {t["type"]: (None if t["trunk_aircraft"] is None else t["trunk_aircraft"]) for t in types}
        mu_v = band_means(R, avg, {r: {"peak": 2 * freq[r] * pk[r], "off": 2 * freq[r] * (1 - pk[r])} for r in avg})   # mean passengers per flight by band
        version = assign(R, P, types, avg, av_v, mu_v, yld, slots, lease=False, gap=0.0, time_s=120)   # the yearly version: solved to optimality so the frequencies (and share) are unique
        new = version["round_trips"]
        new_pk = {r: (version["legs_band"][r]["peak"] / (2 * new[r]) if new[r] else 0.5) for r in new}
        rounds.append({"freq": dict(new), "peak_share": {r: round(v, 3) for r, v in new_pk.items()}, "share": {r: round(v, 3) for r, v in sh.items()}})
        if all(abs(new[r] - freq[r]) < 0.01 and abs(new_pk[r] - pk[r]) < 0.01 for r in new):
            break
        freq, pk = new, new_pk
    v737_rpk = 0.0
    for k, n in version["by_type_pattern"].items():
        t, pid = k.split(":")
        if t == "737":
            p = next(x for x in P if x["id"] == pid)
            seats = next(x for x in types if x["type"] == "737")["seats"]
            v737_rpk += sum(n * c * seats * DAYS * (version["lf"][r] or 0) * km[r] for r, c in p["legs"].items()) / 1e6
    trunk_share = ctx["set_trunk_737_rpk"](v737_rpk) if ctx.get("set_trunk_737_rpk") else None
    rows = []
    for d in dem:
        if fiscal_years and d["fy"] not in fiscal_years:
            continue
        m = int(d["label"][5:]); t = d["t"]
        free737 = ctx["fleet_737"] * (1 - ctx["checks_rate"][m]) - ctx["regional_need"](t) - ctx["engine_wait"].get(t, 0)
        av = available(types, m, free737)
        mu_q = {q: band_means(R, {r: v[q] for r, v in d["routes"].items()}, version["legs_band"]) for q in quantiles}
        sol = {q: (price(R, P, types, {r: v[q] for r, v in d["routes"].items()}, av, mu_q[q], yld, slots, **fares) if fares and q == "p50" else
                   assign(R, P, types, {r: v[q] for r, v in d["routes"].items()}, av, mu_q[q], yld, slots)) for q in quantiles}
        s = sol["p50"]
        row = {"t": t, "label": d["label"], "fy": d["fy"], "pax_k_p50": d["total_p50"], "available": {k: round(v, 1) for k, v in av.items()},
               "used_p50": s["by_type"], "lease_p50": s["lease"], "spill_p50_pax_k": s["spill_total_pax_k"],
               "carried_p50_pax_k": round(sum(s["carried_pax_k"].values()), 1),
               "carried_p50_rpk_m": round(sum(v * km[r] for r, v in s["carried_pax_k"].items()) / 1e3, 1),
               "revenue_carried_oku_p50": round(s["revenue_carried_k"] * USD_JPY / 1e5, 2),
               "round_trips_p50": s["round_trips"], "avg_seats_p50": s["avg_seats"], "lf_p50": s["lf"], "legs_by_type_p50": s["legs_by_type"], "legs_band_p50": s["legs_band"], "spill_by_route_p50": s["spill_pax_k"],
               "by_type_pattern_p50": s["by_type_pattern"], "aircraft_by_route_p50": per_route(P, s["by_type_pattern"]),
               "cost_k_p50": s["cost_k"], "cycles_per_day_p50": s["cycles_per_day_by_type"], "lease_cycles_per_day_p50": s["lease_cycles_per_day"],
               "fare_mult_p50": s["fare_mult"], "pax_after_fare_k_p50": s["pax_after_fare_k"], "carried_by_route_p50": s["carried_pax_k"]}
        for q in quantiles:
            if q != "p50":
                row.update({f"used_{q}": sol[q]["by_type"], f"lease_{q}": sol[q]["lease"], f"spill_{q}_pax_k": sol[q]["spill_total_pax_k"],
                            f"carried_{q}_rpk_m": round(sum(v * km[r] for r, v in sol[q]["carried_pax_k"].items()) / 1e3, 1)})
        if "p90" in sol:
            row["short_p90"] = sol["p90"]["lease"] > 0 or sol["p90"]["spill_total_pax_k"] > 0.5
            row["spill_by_route_p90"] = sol["p90"]["spill_pax_k"]
        if detail:
            nolease = assign(R, P, types, {r: v["p50"] for r, v in d["routes"].items()}, av, mu_q["p50"], yld, slots, lease=False)
            row["no_lease_p50"] = {"spill_pax_k": nolease["spill_total_pax_k"], "lost_revenue_k": nolease["cost_k"]["lost_revenue"], "by_type": nolease["by_type"]}
        rows.append(row)
    return {"routes": [{k: r[k] for k in ("id", "name", "market_pax_2024", "market_lf_2024", "block_h", "km", "slot_airport")} for r in R["routes"]], "patterns": P, "types": types,
            "airport": {**ap.summary(S, cid), "delta": delta, "budget": slots["budget"], "bounds": slots["bounds"], "use_min": slots["use_min"],
                        "hub_budget": budget_hub, "unusable_round_trips": round(budget_hub - slots["budget"], 1), "destination_caps": caps,
                        "destination_binding": [r for r in ap.HUB_ROUTES if caps and r in caps and slots["bounds"][r][1] >= caps[r] - 1e-9 and
                                                ap.bounds(S, cid, delta)[r][1] > caps[r]]},
            "version": {"by_type": version["by_type"], "by_type_pattern": version["by_type_pattern"], "round_trips": version["round_trips"], "avg_seats": version["avg_seats"],
                        "lf": version["lf"], "legs_band": version["legs_band"], "legs_by_type": version["legs_by_type"], "share_rounds": rounds, "share": rounds[-1]["share"], "trunk_737_rpk_million": round(v737_rpk, 1), "trunk_share_of_737_rpk": trunk_share,
                        "how": "最初の 12 か月の平均の需要（p50）での機材割当。便数が変わると需要の取り分も変わるので、取り分と便数が落ち着くまで解き直す。737 の幹線分がこれで決まり、残りが地方路線"},
            "demand": dem, "rows": rows, "hub": R["hub"],
            "how": {"assignment": f"月ごと・分位ごとに、機種 × パターンの機数（整数）・737 のウェットリース・乗せられない旅客を、運航費 ＋ リース費 ＋ 失う売上 が最小になるよう解く（機材割当モデル、PuLP＋HiGHS）。1 便が運ぶのは便の需要と座席の小さいほう。便の需要は路線の平均のまわりに時間帯・曜日・予約の取りこぼしでばらつく（取りこぼしの式）",
                    "slots": "空港側の層（airport_slots.py）：羽田の 4 幹線の往復便数の合計は幹線の枠以内、かつ枠の 98% 以上を使う（使わない枠は回収の対象）。路線ごとの便数は今の ±2 往復（再配分シナリオでは幅を広げる）。福岡–那覇は福岡空港の便で、今の便数と季節便の範囲",
                    "share": "自社の需要 ＝ 路線全体の旅客（2024 年の公開値を 2026-10 まで伸ばす）× 便数の比率",
                    "available": "大型機：幹線に回せる上限（機種の国内線の機数 − 他の路線・整備、根拠は routes_trunk.json）。737：全機 − 機体整備 − 地方路線に要る機数 − エンジン待ち",
                    "attribution": "航路ごとの機数はパターンの機数を便数で按分", "reference": R.get("fleet_assignment_ref")},
            "assumptions": {"sources": R.get("sources"), "spill_model": {**R["spill_model"], "cv_total": round(spill_cv(R), 3)},
                            "lease": R["lease"], "day_cap_h": R["day_block_cap_h"], "maintenance": R.get("maintenance_note")}}
