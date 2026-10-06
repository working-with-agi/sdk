#!/usr/bin/env python3
"""Which routes the airports should grow, and how that comes back to the aircraft.

The top-down reading of the story: management and politics set the premises (slot rule, carbon
as trading, the Linear), the airports decide where capacity goes, and the fleet and its engines
take the consequence. One fiscal year (p50); both large companies' fleet assignments re-solved
(company A and company B, each with its own fleet; the other carriers move only their frequencies).

  step      capacity added on one trunk route at both ends: Haneda and the airport at the other
            end (New Chitose, Fukuoka, Naha; Itami only as a one-step reference -- its cap is a
            noise agreement). Two ways to hand it out:
              market   the airport's view: +2 round trips a day to each large company, and the other
                       carriers enough to keep the two companies' combined share; the passengers the
                       market newly carries = (A's + B's added passengers) / that combined share
              airline  company A alone gets +4 round trips; company B loses share to them
  path      the airport's order: up to five market steps, each time the route that carries the most new
            passengers per 100 million yen of airport capacity (Haneda + the other end, the cost per
            round trip a day from data/airport_investment.json, mid value)
  aircraft  at every step: the aircraft used by type, the wet-lease months, each engine type's
            utilisation and shop spend, the block hours and the CO2
  worlds    before the Linear, and after it (the air keeps 66 % of Haneda-Itami, neither company
            moves its freed Itami slots to the other trunk routes: the slot rule's world)

  python route_growth.py jal                 # fleet/route_growth_jal.json
  python route_growth.py jal --fares fitted  # fleet/route_growth_jal_fitted.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import airport_slots as ap
import capacity_scenarios as cs
import carbon_scenarios as cb
import investment_scenarios as inv

HERE = Path(__file__).resolve().parent
ROUTE = {"CTS": "HND-CTS", "FUK": "HND-FUK", "OKA": "HND-OKA", "ITM": "HND-ITM"}
GROW = ("CTS", "FUK", "OKA")
MARKET_STEP = 2            # company A's round trips a day per market step (the others in proportion)
AIRLINE_STEP = 4           # company A's round trips a day when it alone gets them


def world_of(S: dict, cid: str, name: str) -> dict:
    cur = ap.current_freq(S, cid)
    if name == "before":
        return {}
    return {"market_scale": {"HND-ITM": 0.66}, "bounds": {"HND-ITM": (0, cur["HND-ITM"] + 1)}, "use_min": 0.0}


def solve(s: dict, S: dict, world: dict, extra: dict, rival: dict, years_ahead: int, K: dict, lock: dict | None = None, overrides: dict | None = None) -> dict:
    """lock: the hub routes held at these round trips a day (the base world's), so the capacity
    added at an airport goes to its route and nowhere else; the grown routes run from there up to
    the airport's cap."""
    cid = s["cid"]
    caps = ap.destination_caps(S, cid, extra=extra)
    b = dict(ap.bounds(S, cid, 0, caps))
    b.update(world.get("bounds", {}))
    if lock:
        b.update({r: (v, v) for r, v in lock.items() if r in ap.HUB_ROUTES})
    for code, n in extra.items():
        r = ROUTE[code]
        b[r] = (lock[r], min(caps[r], lock[r] + n)) if lock else (b[r][0], caps[r])     # the grown route takes exactly what was added there
    cor = {**world, "bounds": b}
    if rival:
        cor["rival_shift"] = rival
    delta = sum(extra.values())
    r = cs.run(s, years_ahead, delta=delta, dest=extra or True, windows=True, corridor=cor, overrides=overrides)
    hub = sum(v for k, v in r["version_round_trips"].items() if k in ap.HUB_ROUTES)
    return {"margin_oku": r["margin_oku"], "carried_pax_k": r["carried_pax_k"], "carried_by_route_pax_k": r["carried_by_route_pax_k"], "spill_pax_k": r["spill_pax_k"], "round_trips": r["version_round_trips"],
            "hub_round_trips": hub, "hub_budget": r["hub_budget"], "by_type": r["version_by_type"], "aircraft_used_avg": r["aircraft_used_avg"],
            "lease_aircraft_months": r["lease_aircraft_months"], "co2_kt": round(cb.co2_t(r, K) / 1e3, 1), "block_h_by_type": r["block_h_by_type"],
            "engines": {e["type"]: {"utilisation_multiplier": e.get("utilisation_multiplier"), "spend_per_year_oku_yen": e.get("spend_per_year_oku_yen")}
                        for e in r["engines"] if e["type"] in ("737", "767", "787")}}


def diff(a: dict, b: dict) -> dict:
    """b - a for the aircraft side."""
    return {"aircraft_used_avg": {t: round(b["aircraft_used_avg"].get(t, 0) - a["aircraft_used_avg"].get(t, 0), 1) for t in b["aircraft_used_avg"]},
            "lease_aircraft_months": b["lease_aircraft_months"] - a["lease_aircraft_months"],
            "block_h": {t: b["block_h_by_type"].get(t, 0) - a["block_h_by_type"].get(t, 0) for t in b["block_h_by_type"]},
            "engines": {t: {"utilisation_multiplier": round((b["engines"][t]["utilisation_multiplier"] or 0) - (a["engines"][t]["utilisation_multiplier"] or 0), 3),
                            "spend_oku": round((b["engines"][t]["spend_per_year_oku_yen"] or 0) - (a["engines"][t]["spend_per_year_oku_yen"] or 0), 1)} for t in b["engines"]},
            "co2_kt": round(b["co2_kt"] - a["co2_kt"], 1)}


def build(cid: str = "jal", out: Path | None = None, years_ahead: int = 3, steps: int = 5, rival_cid: str = "ana", log=print) -> dict:
    """Both large companies solved with their own fleets; the other carriers move only their
    frequencies. A market step: +2 round trips a day to each large company on the route, and the
    other carriers enough to keep the two companies' combined share."""
    t0 = time.time()
    cids = (cid, rival_cid)
    SS = {c: cs.setup(c) for c in cids}
    S = ap.load()
    K = cb.load()
    unit = inv.unit_costs(inv.load())
    mid = {k: (sum(v) / 2 if v and v[0] is not None else None) for k, v in unit.items()}
    cur = {c: ap.current_freq(S, c) for c in cids}
    oth = ap.others_freq(S)
    big = {r: cur[cid][r] + cur[rival_cid][r] for r in oth}
    s_ab = {r: big[r] / (big[r] + oth[r]) for r in oth}                    # the two companies' combined share today
    o_add = {r: MARKET_STEP * 2 * oth[r] / big[r] for r in oth}             # the other carriers' round trips per market step
    other_of = {cid: rival_cid, rival_cid: cid}

    def both(world, extra, others, lock, ov=None):
        """extra: {company: {airport: round trips}}; others: {route: round trips} for the other carriers.
        Each company sees the other's added round trips and the other carriers' as the competition."""
        out = {}
        for c in cids:
            rv = dict(others)
            for code, n in extra.get(other_of[c], {}).items():
                rv[ROUTE[code]] = rv.get(ROUTE[code], 0) + n
            out[c] = solve(SS[c], S, world[c], extra.get(c, {}), rv, years_ahead, K, lock[c], (ov or {}).get(c))
        return out

    def gain(x, y):
        return {c: {"pax_k": round(y[c]["carried_pax_k"] - x[c]["carried_pax_k"], 1), "margin_oku": round(y[c]["margin_oku"] - x[c]["margin_oku"], 1)} for c in cids}

    res = {}
    for wname in ("before", "after_66_rule"):
        world = {c: world_of(S, c, wname) for c in cids}
        base = {c: solve(SS[c], S, world[c], {}, {}, years_ahead, K) for c in cids}
        lock = {c: {r: base[c]["round_trips"][r] for r in ap.HUB_ROUTES} for c in cids}
        one = []
        for code in GROW + (("ITM",) if wname == "before" else ()):
            r = ROUTE[code]
            m = both(world, {c: {code: MARKET_STEP} for c in cids}, {r: o_add[r]}, lock)
            a = both(world, {cid: {code: AIRLINE_STEP}}, {}, lock)
            g, ga = gain(base, m), gain(base, a)
            trips = 2 * MARKET_STEP + o_add[r]
            cost = None if mid.get(code) is None else round(trips * (mid["HND"] + mid[code]), 1)
            pax = round((g[cid]["pax_k"] + g[rival_cid]["pax_k"]) / s_ab[r], 1)
            one.append({"airport": code, "route": r, "share_two_companies": round(s_ab[r], 3), "market_round_trips_added": round(trips, 1), "airport_cost_oku": cost,
                        "market": {"new_pax_k": pax, "pax_per_oku": round(pax / cost, 2) if cost else None, "by_company": g,
                                   "aircraft": {c: diff(base[c], m[c]) for c in cids}, "round_trips": {c: m[c]["round_trips"] for c in cids}},
                        "airline": {"to": cid, "by_company": ga, "pax_net_two_k": round(ga[cid]["pax_k"] + ga[rival_cid]["pax_k"], 1),
                                    "aircraft": {c: diff(base[c], a[c]) for c in cids}}})
            log(f"  [{time.time() - t0:4.0f}s] {wname} {code}: market +{pax} k pax, cost {cost}; A {g[cid]['margin_oku']} B {g[rival_cid]['margin_oku']}; to A alone: A {ga[cid]['margin_oku']} B {ga[rival_cid]['margin_oku']}")
        path, extra, others, prev = [], {c: {} for c in cids}, {}, base
        for i in range(steps):
            cands = []
            for code in GROW:
                r = ROUTE[code]
                e = {c: {**extra[c], code: extra[c].get(code, 0) + MARKET_STEP} for c in cids}
                ot = {**others, r: others.get(r, 0) + o_add[r]}
                x = both(world, e, ot, lock)
                cost = (2 * MARKET_STEP + o_add[r]) * (mid["HND"] + mid[code])
                gg = gain(prev, x)
                pax = (gg[cid]["pax_k"] + gg[rival_cid]["pax_k"]) / s_ab[r]
                cands.append((pax / cost, code, e, ot, x, cost, pax, gg))
            best = max(cands, key=lambda c: c[0])
            if best[6] <= 0:
                path.append({"step": i + 1, "stop": True, "candidates": {c[1]: {"new_pax_k": round(c[6], 1), "pax_per_oku": round(c[0], 2)} for c in cands}})
                log(f"  [{time.time() - t0:4.0f}s] {wname} path {i + 1}: stop")
                break
            _, code, extra, others, x, cost, pax, gg = best
            path.append({"step": i + 1, "airport": code, "new_pax_k": round(pax, 1), "airport_cost_oku": round(cost, 1), "pax_per_oku": round(best[0], 2),
                         "by_company": gg, "extra": {c: dict(extra[c]) for c in cids},
                         "candidates": {c[1]: {"new_pax_k": round(c[6], 1), "pax_per_oku": round(c[0], 2)} for c in cands},
                         "round_trips": {c: x[c]["round_trips"] for c in cids}, "aircraft_total": {c: diff(base[c], x[c]) for c in cids},
                         "state": x})
            log(f"  [{time.time() - t0:4.0f}s] {wname} path {i + 1}: {code} +{pax:.0f} k pax / {cost:.0f} oku; A {gg[cid]['margin_oku']} B {gg[rival_cid]['margin_oku']}")
            prev = x
        # at the end of the path, more widebodies for company A
        fleet = []
        for n in (0, 2, 4):
            ov = {cid: {"A350": {"trunk_aircraft": 13 + n}}} if n else None
            x = both(world, extra, others, lock, ov)
            own = n * cs.WIDEBODY_K_PER_AIRCRAFT_MONTH * 12 * cs.USD_JPY / 1e5
            g = gain(base, x)
            fleet.append({"a350_added": n, "by_company": g, "a_margin_change_net_oku": round(g[cid]["margin_oku"] - own, 1), "ownership_oku": round(own, 1),
                          "aircraft": {c: diff(base[c], x[c]) for c in cids}})
            log(f"  [{time.time() - t0:4.0f}s] {wname} end +A350 {n}: A carried {g[cid]['pax_k']}, A net {fleet[-1]['a_margin_change_net_oku']}")
        res[wname] = {"base": base, "one_step": one, "path": path, "end_extra": extra, "end_others": others, "end_fleet": fleet}
    out_d = {"companies": {"a": cid, "b": rival_cid}, "fiscal_year": cs.fy_after(SS[cid]["fy"], years_ahead), "share_two_companies_today": {r: round(v, 3) for r, v in s_ab.items()},
             "others_round_trips_per_market_step": {r: round(v, 2) for r, v in o_add.items()}, "airport_cost_mid_oku_per_round_trip_day": mid, "worlds": res,
             "how": "両社（会社 A・B）をそれぞれの機材で解く（他の航空会社は便数だけ動く）。1 歩 ＝ 羽田と対向空港の両方に容量を足す。market：両社に 2 往復ずつ、他の航空会社には両社の合計の取り分を保つ分。市場として新しく運べる旅客 ≈（会社 A ＋ 会社 B の増えた旅客、全路線）÷ 両社の合計の取り分。airline：会社 A だけに 4 往復（会社 B は相手の便が増えた分だけ取り分を失う）。各社は相手の足した往復と他の航空会社の分を競争相手の便として見る。羽田の他の路線の便数は各社の基準の世界の値に固定し、足した路線は足した分だけ増える。空港の費用は市場の往復 ×（羽田 ＋ 対向空港）の 1 日 1 往復あたりの費用（中央値）。path は market の歩を最大 5 回、毎回 1 億円あたりの新しい旅客が最も多い路線を選び、どの路線でも増えなくなったら止める。end_fleet は path の終わりで会社 A の A350 を 0・2・4 機足したとき（1 機 月 1,100 千ドルの所有費、no_source）。伊丹は 1 歩の参考だけ。リニアの後は航空に 66% 残り、両社とも空いた伊丹の枠を他の幹線に移さない世界",
             "caveat": "他の航空会社の機材は解いていない（便数だけ）。会社 B の運航費は 2024 年の搭乗率に合わせきれていない（RMSE 0.13）。会社 B のエンジン整備費は 767 だけ。両社の解は同時の均衡ではなく、相手の便数を与えたときのそれぞれの最適。乗れなかった旅客の振り替えは入れていない。費用は空港側だけ",
             "elapsed_s": round(time.time() - t0, 1)}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(out_d, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"wrote {out}")
    return out_d


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("company", nargs="?", default="jal")
    a.add_argument("--out", type=Path, default=None)
    a.add_argument("--fares", choices=("distance", "fitted"), default="distance", help="fitted: the route fare levels fitted to both companies' 2024 load factors")
    args = a.parse_args(argv)
    import route_fleet as rf
    rf.FARE_MODE = args.fares
    tag = "" if args.fares == "distance" else "_fitted"
    build(args.company, args.out or HERE / "fleet" / f"route_growth_{args.company}{tag}.json", rival_cid="ana" if args.company == "jal" else "jal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
