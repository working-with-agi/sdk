#!/usr/bin/env python3
"""Which routes the airports should grow, and how that comes back to the aircraft.

The top-down reading of the story: management and politics set the premises (slot rule, carbon
as trading, the Linear), the airports decide where capacity goes, and the fleet and its engines
take the consequence. One fiscal year (p50), company A's fleet assignment re-solved.

  step      capacity added on one trunk route at both ends: Haneda and the airport at the other
            end (New Chitose, Fukuoka, Naha; Itami only as a one-step reference -- its cap is a
            noise agreement). Two ways to hand it out:
              market   the airport's view: the route grows by 2 round trips a day for company A and
                       the other carriers grow in proportion, so the shares stay; the passengers the
                       market newly carries are company A's added passengers / its share
              airline  company A alone gets +4 round trips (part of its gain is taken from the others)
  path      the airport's order: five market steps, each time the route that carries the most new
            passengers per 100 million yen of airport capacity (Haneda + the other end, the cost per
            round trip a day from data/airport_investment.json, mid value)
  aircraft  at every step: the aircraft used by type, the wet-lease months, each engine type's
            utilisation and shop spend, the block hours and the CO2
  worlds    before the Linear, and after it (the air keeps 66 % of Haneda-Itami, neither company
            moves its freed Itami slots to the other trunk routes: the slot rule's world)

  python route_growth.py jal --out fleet/route_growth_jal.json
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


def build(cid: str, out: Path | None = None, years_ahead: int = 3, steps: int = 5, log=print) -> dict:
    t0 = time.time()
    s = cs.setup(cid)
    S = ap.load()
    K = cb.load()
    unit = inv.unit_costs(inv.load())
    mid = {k: (sum(v) / 2 if v and v[0] is not None else None) for k, v in unit.items()}
    cur = ap.current_freq(S, cid)
    sh = ap.share(S, cid, cur)
    res = {}
    for wname in ("before", "after_66_rule"):
        world = world_of(S, cid, wname)
        base = solve(s, S, world, {}, {}, years_ahead, K)
        lock = {r: base["round_trips"][r] for r in ap.HUB_ROUTES}
        # one step from today, both ways of handing it out
        one = []
        for code in GROW + (("ITM",) if wname == "before" else ()):
            r = ROUTE[code]
            m = solve(s, S, world, {code: MARKET_STEP}, {r: MARKET_STEP * (1 - sh[r]) / sh[r]}, years_ahead, K, lock)
            a = solve(s, S, world, {code: AIRLINE_STEP}, {}, years_ahead, K, lock)
            mkt_trips = MARKET_STEP / sh[r]
            cost = None if mid.get(code) is None else round(mkt_trips * (mid["HND"] + mid[code]), 1)
            own = round(m["carried_by_route_pax_k"][r] - base["carried_by_route_pax_k"][r], 1)                    # company A on the grown route
            other = round((m["carried_pax_k"] - m["carried_by_route_pax_k"][r]) - (base["carried_pax_k"] - base["carried_by_route_pax_k"][r]), 1)   # A elsewhere: its aircraft move
            pax = round((m["carried_pax_k"] - base["carried_pax_k"]) / sh[r], 1)                                   # the market: the others respond like A, in proportion
            one.append({"airport": code, "route": r, "share_a": round(sh[r], 3), "market_round_trips_added": round(mkt_trips, 1), "airport_cost_oku": cost,
                        "market": {"new_pax_k": pax, "a_on_route_pax_k": own, "a_other_routes_pax_k": other, "pax_per_oku": round(pax / cost, 2) if cost else None, "a_margin_oku": round(m["margin_oku"] - base["margin_oku"], 1),
                                   "aircraft": diff(base, m), "round_trips": m["round_trips"]},
                        "airline": {"a_pax_k": round(a["carried_pax_k"] - base["carried_pax_k"], 1), "a_margin_oku": round(a["margin_oku"] - base["margin_oku"], 1),
                                    "aircraft": diff(base, a), "round_trips": a["round_trips"]}})
            log(f"  [{time.time() - t0:4.0f}s] {wname} {code}: market +{pax} k pax, cost {cost}; airline {one[-1]['airline']['a_margin_oku']}")
        # the airport's order: market steps, best new passengers per cost first
        path, extra, rival, prev = [], {}, {}, base
        for i in range(steps):
            cands = []
            for code in GROW:
                r = ROUTE[code]
                e = {**extra, code: extra.get(code, 0) + MARKET_STEP}
                rv = {**rival, r: rival.get(r, 0) + MARKET_STEP * (1 - sh[r]) / sh[r]}
                x = solve(s, S, world, e, rv, years_ahead, K, lock)
                cost = MARKET_STEP / sh[r] * (mid["HND"] + mid[code])
                pax = (x["carried_pax_k"] - prev["carried_pax_k"]) / sh[r]
                cands.append((pax / cost, code, e, rv, x, cost, pax))
            best = max(cands, key=lambda c: c[0])
            if best[6] <= 0:                                                       # no route carries more people any more: the airport stops
                path.append({"step": i + 1, "stop": True, "candidates": {c[1]: {"new_pax_k": round(c[6], 1), "pax_per_oku": round(c[0], 2)} for c in cands}})
                log(f"  [{time.time() - t0:4.0f}s] {wname} path {i + 1}: stop")
                break
            _, code, extra, rival, x, cost, pax = best
            other = (x["carried_pax_k"] - x["carried_by_route_pax_k"][ROUTE[code]]) - (prev["carried_pax_k"] - prev["carried_by_route_pax_k"][ROUTE[code]])
            path.append({"step": i + 1, "airport": code, "new_pax_k": round(pax, 1), "a_other_routes_pax_k": round(other, 1), "airport_cost_oku": round(cost, 1), "pax_per_oku": round(best[0], 2),
                         "a_margin_change_oku": round(x["margin_oku"] - prev["margin_oku"], 1), "a_extra_round_trips": dict(extra),
                         "candidates": {c[1]: {"new_pax_k": round(c[6], 1), "pax_per_oku": round(c[0], 2)} for c in cands},
                         "round_trips": x["round_trips"], "aircraft_step": diff(prev, x), "aircraft_total": diff(base, x), "state": x})
            log(f"  [{time.time() - t0:4.0f}s] {wname} path {i + 1}: {code} +{pax:.0f} k pax / {cost:.0f} oku")
            prev = x
        # at the end of the path, more widebodies: does the passenger count come back, net of owning them?
        fleet = []
        for n in (0, 2, 4):
            ov = {"A350": {"trunk_aircraft": 13 + n}} if n else None
            x = solve(s, S, world, extra, rival, years_ahead, K, lock, ov)
            own = n * cs.WIDEBODY_K_PER_AIRCRAFT_MONTH * 12 * cs.USD_JPY / 1e5
            fleet.append({"a350_added": n, "a_carried_change_pax_k": round(x["carried_pax_k"] - base["carried_pax_k"], 1),                           "a_margin_change_net_oku": round(x["margin_oku"] - own - base["margin_oku"], 1), "ownership_oku": round(own, 1), "aircraft": diff(base, x)})
            log(f"  [{time.time() - t0:4.0f}s] {wname} end +A350 {n}: carried {fleet[-1]['a_carried_change_pax_k']}, net {fleet[-1]['a_margin_change_net_oku']}")
        res[wname] = {"base": base, "one_step": one, "path": path, "end_extra": extra, "end_fleet": fleet}
    out_d = {"company": cid, "fiscal_year": cs.fy_after(s["fy"], years_ahead), "share_a_today": {r: round(v, 3) for r, v in sh.items()}, "airport_cost_mid_oku_per_round_trip_day": mid,
             "worlds": res,
             "how": "1 歩 ＝ 羽田と対向空港の両方に容量を足す。market：会社 A に 2 往復、他社にはいまの取り分を保つ分（2×(1−s)/s 往復）、市場として新しく運べる旅客 ≈ 会社 A の増えた旅客（全路線）÷ その路線の取り分（他社も会社 A と同じように、取り分に応じて機材を動かして応じるとした近似。会社 A の伸ばした路線と他の路線の内訳も出す。路線を増やすと機材が他の路線に動くので、伸ばした路線だけの増減は小さく、ときに減る）。羽田の他の路線の便数は基準の世界の値に固定し、足した容量はその路線だけに行く。airline：会社 A だけに 4 往復（増えた旅客の一部は他社からの取り分）。空港の費用は市場の往復 ×（羽田 ＋ 対向空港）の 1 日 1 往復あたりの費用（中央値）。path は market の歩を最大 5 回、毎回 1 億円あたりの新しい旅客が最も多い路線を選び、どの路線でも旅客が増えなくなったら止める。end_fleet は path の終わりで A350 を幹線に 0・2・4 機足したとき（1 機 月 1,100 千ドルの所有費、no_source）。伊丹は騒音の取り決めの上限があるので 1 歩の参考だけ。リニアの後は航空に 66% 残り、両社とも空いた伊丹の枠を他の幹線に移さない世界（配分の規則の世界）",
             "caveat": "他社の機材・費用は解いていない（他社は便数だけ動く）。市場の新しい旅客は会社 A の値を取り分で割った近似。乗れなかった旅客の振り替えは入れていない。費用は空港側だけ（機体の所有費は入れていない）",
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
    args = a.parse_args(argv)
    build(args.company, args.out or HERE / "fleet" / f"route_growth_{args.company}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
