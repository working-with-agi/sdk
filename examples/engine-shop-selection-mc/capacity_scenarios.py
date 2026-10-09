#!/usr/bin/env python3
"""What the hub's capacity cap does, and what happens if it lifts.

Three questions on top of the airport and airline layers (airport_slots.py, route_fleet.py,
fleet_from_demand.py), each answered by re-solving the monthly fleet assignment for one fiscal
year (p50) and re-deriving the engine shop visit windows per aircraft type:

  1. years      demand keeps growing, the hub slots do not: year by year (FY+0 .. FY+n), the
                passengers left behind, the revenue lost, and how far each type's engines move
                (utilisation multiplier, windows pulled earlier, maintenance spend) -- against the
                same years with the trunk frequencies following demand (hub cap lifted), with
                and without the destination airports' caps.
  2. widebody   more large aircraft instead of more flights: extra A350s on the trunk (each one
                charged an ownership/lease cost, no_source), or the 737 taken off the trunk;
                revenue, operating cost and margin net of the added aircraft, and the engines.
  3. dest       the hub cap lifted by +n round trips: does the airport at the other end take
                them? The destination caps (data/destination_airports.json) laid over the
                per-route bounds; slots that cannot be flown, and which airport binds.

Everything is synthetic or flagged no_source.

  python capacity_scenarios.py jal --out fleet/capacity_jal.json
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import airport_slots as ap
import company
import demand as demand_mod
import fleet_from_demand as ffd
import plan_from_demand as pfd
import route_fleet as rf

HERE = Path(__file__).resolve().parent
USD_JPY = ffd.USD_JPY
WIDEBODY_K_PER_AIRCRAFT_MONTH = 1100.0   # no_source: ownership or lease of one more A350-900 (k$/month), crew and overhead inside the block-hour cost
YEARS = (0, 1, 2, 3, 4, 5)
WIDEBODY = (
    {"id": "base", "label": "今の機材（A350 は幹線に 13 機まで）", "overrides": {}, "added": 0},
    {"id": "a350+2", "label": "A350 を 2 機足す（15 機）", "overrides": {"A350": {"trunk_aircraft": 15}}, "added": 2},
    {"id": "a350+4", "label": "A350 を 4 機足す（17 機）", "overrides": {"A350": {"trunk_aircraft": 17}}, "added": 4},
    {"id": "a350+4_no737", "label": "A350 を 4 機足し、737 を幹線から外す", "overrides": {"A350": {"trunk_aircraft": 17}, "737": {"trunk_aircraft": 0}}, "added": 4},
)
EXPANSION = (10, 20, 30, 45)


def setup(cid: str) -> dict:
    D = demand_mod.load()
    conf = json.loads(company.CONFIG.read_text(encoding="utf-8"))
    cfg, _ = company.fleet_cfg(conf, cid, None)
    cur = json.loads((HERE / "data" / cid / "fleet.json").read_text(encoding="utf-8"))
    derived = pfd.derive(D, cid, cur["start"])
    rpk = ffd.demand_rpk(D, cid, derived, cur["start"], cur["horizon_months"])
    ac = ffd.aircraft_needed(D, cid, cfg, rpk, derived)
    eng = ffd.engines_needed(cfg, cur, ac, None)
    types = rf.types_of(rf.load(), cid)
    fleets = {f["type"]: f for f in conf["companies"][cid].get("fleets", [])}
    ectx = {"cid": cid, "types": types, "fleets": fleets, "total": cfg["aircraft"]["total"], "sectors_day": ac["params"]["sectors_per_day"],
            "derived": derived, "cur": cur}
    fy = sorted({b["fy"] for b in rpk})[1]                                             # the first full fiscal year
    return {"cid": cid, "D": D, "cfg": cfg, "rpk": rpk, "ac": ac, "eng": eng, "derived": derived, "ectx": ectx, "fy": fy, "types": types}


def run(s: dict, years_ahead: float = 0.0, delta: float = 0.0, overrides: dict | None = None, dest: bool = False, windows: bool = True,
        fares: dict | None = None, corridor: dict | None = None) -> dict:
    """One fiscal year (p50) under one setting: the trunk's economics and each type's engines.
    fares: {"elasticity": e} sets each month's fares by route (route_fleet.price)."""
    ctx, _ = ffd.trunk_context(s["cid"], s["cfg"], s["rpk"], s["ac"], s["eng"], s["derived"], years_ahead)
    tr = rf.build(s["cid"], s["D"], s["rpk"], ctx, delta=delta, quantiles=("p50",), detail=False, fiscal_years={s["fy"]}, overrides=overrides, dest=dest, fares=fares, corridor=corridor)
    rows = tr["rows"]
    types = [t["type"] for t in tr["types"]]
    ectx = {**s["ectx"], "types": tr["types"]}
    engines = ffd.engine_rows_of(tr, ectx, s["fy"], windows, util_cap=None)          # the trunk flies these cycles: no planning cap
    oku = USD_JPY / 1e5
    revenue = sum(r["revenue_carried_oku_p50"] for r in rows)
    operating = sum(r["cost_k_p50"]["operating"] for r in rows) * oku
    lease = sum(r["cost_k_p50"].get("lease", 0) for r in rows) * oku
    caps = tr["airport"]["destination_caps"] or {}
    vrt = tr["version"]["round_trips"]
    routes = list(rows[0]["fare_mult_p50"])
    peak = sorted(rows, key=lambda r: r["pax_k_p50"])
    fare = {"by_route": {r: round(sum(x["fare_mult_p50"][r] * x["carried_by_route_p50"][r] for x in rows) / max(1e-9, sum(x["carried_by_route_p50"][r] for x in rows)), 3) for r in routes},
            "busiest_3_months": {r: round(sum(x["fare_mult_p50"][r] for x in peak[-3:]) / 3, 3) for r in routes},
            "quietest_3_months": {r: round(sum(x["fare_mult_p50"][r] for x in peak[:3]) / 3, 3) for r in routes},
            "by_month": {x["label"]: x["fare_mult_p50"] for x in rows},
            "demand_after_fare_pax_k": round(sum(sum(x["pax_after_fare_k_p50"].values()) for x in rows), 1)} if fares else None
    return {"years_ahead": years_ahead, "fares": fares, "fare": fare, "fiscal_year": fy_after(s["fy"], years_ahead), "delta_round_trips": delta, "dest_caps": dest,
            "hub_budget": tr["airport"]["hub_budget"], "flyable_budget": tr["airport"]["budget"], "unusable_round_trips": tr["airport"]["unusable_round_trips"],
            "version_round_trips": vrt, "version_by_type": tr["version"]["by_type"],
            "destination_at_cap": [r for r, c in caps.items() if vrt.get(r, 0) >= c - 1e-6 and c < ap.bounds(ap.load(), s["cid"], delta)[r][1]],
            "demand_pax_k": round(sum(r["pax_k_p50"] for r in rows), 1) if all("pax_k_p50" in r for r in rows) else None,
            "carried_pax_k": round(sum(r["carried_p50_pax_k"] for r in rows), 1), "spill_pax_k": round(sum(r["spill_p50_pax_k"] for r in rows), 1),
            "revenue_oku": round(revenue, 1), "lost_revenue_oku": round(sum(r["cost_k_p50"]["lost_revenue"] for r in rows) * oku, 1),
            "operating_cost_oku": round(operating, 1), "lease_cost_oku": round(lease, 1), "lease_aircraft_months": sum(r["lease_p50"] for r in rows),
            "margin_oku": round(revenue - operating - lease, 1),
            "block_h_by_type": {t: round(sum(r["block_h_by_type_p50"].get(t, 0) for r in rows)) for t in types},
            "carried_by_route_pax_k": {k: round(sum(r["carried_by_route_p50"][k] for r in rows), 1) for k in routes},
            "recaptured_pax_k": round(sum(sum(r.get("recaptured_by_route_p50", {}).values()) for r in rows), 1),
            "by_month": [{"label": r["label"], "spill_pax_k": r["spill_p50_pax_k"], "lost_revenue_oku": round(r["cost_k_p50"]["lost_revenue"] * oku, 2),
                          "recaptured_pax_k": round(sum(r.get("recaptured_by_route_p50", {}).values()), 1), "spill_by_route_pax_k": r["spill_by_route_p50"],
                          "lf": r["lf_p50"], "legs_by_type": r["legs_by_type_p50"], "used": r["used_p50"]} for r in rows],
            "legs_share_by_type": {t: round(sum(r["legs_by_type_p50"].get(t, 0) for r in rows) / max(1, sum(sum(r["legs_by_type_p50"].values()) for r in rows)), 3) for t in types},
            "aircraft_used_avg": {t: round(sum(r["used_p50"][t] for r in rows) / len(rows), 1) for t in types},
            "lf_avg": {k: round(sum((r["lf_p50"][k] or 0) for r in rows) / len(rows), 3) for k in rows[0]["lf_p50"]},
            "engines": [{k: e.get(k) for k in ("type", "engine", "trunk_aircraft_used_avg", "trunk_cycles_per_aircraft_day", "blended_cycles_per_aircraft_day",
                                                 "utilisation_multiplier", "utilisation_uncapped", "at_util_cap", "windows", "spend_per_year_oku_yen")} for e in engines]}


class fx_rate:
    """Run with another yen per dollar (the costs are in k$, the fares in yen)."""
    def __init__(self, v: float):
        self.v = v
    def __enter__(self):
        global USD_JPY
        self.old = (rf.USD_JPY, ffd.USD_JPY, USD_JPY)
        rf.USD_JPY = ffd.USD_JPY = USD_JPY = self.v
    def __exit__(self, *exc):
        global USD_JPY
        rf.USD_JPY, ffd.USD_JPY, USD_JPY = self.old


def sensitivity(s: dict, horizon: int = 5, growth_shift: float = 0.01, fx: tuple = (140.0, 170.0)) -> dict:
    """The two inputs the results lean on most: the demand growth (the last year under the cap, with
    the growth +/- growth_shift a year) and the yen per dollar (the first year)."""
    g = s["derived"]["demand_growth_per_year"]
    rows = []
    for dg in (-growth_shift, 0.0, growth_shift):
        k = horizon * math.log(1 + g + dg) / math.log(1 + g)                 # the same demand as horizon years at g + dg
        r = run(s, k, windows=False)
        rows.append({"growth": round(g + dg, 4), "years_equivalent": round(k, 2), "fiscal_year": fy_after(s["fy"], horizon),
                     **{x: r[x] for x in ("demand_pax_k", "carried_pax_k", "spill_pax_k", "lost_revenue_oku", "revenue_oku", "operating_cost_oku", "margin_oku")}})
    fxr = []
    for v in (fx[0], USD_JPY, fx[1]):
        with fx_rate(v):
            r = run(s, 0, windows=False)
        fxr.append({"usd_jpy": v, **{x: r[x] for x in ("revenue_oku", "operating_cost_oku", "margin_oku", "spill_pax_k", "aircraft_used_avg")}})
    return {"growth": rows, "fx": fxr,
            "how": "伸び率は、最後の年（+5 年）の需要を伸び率 ±1 ポイントで作り直す（同じ需要になる年数で解く）。為替は最初の年。運賃は円、費用は k$ なので、円安は費用だけを増やす"}


def fy_after(fy, years: float) -> str:
    """'FY2027' + 2 -> 'FY2029' (the fiscal year whose demand a years_ahead run stands for)."""
    return f"FY{int(str(fy)[2:]) + round(years)}"


def follow_delta(s: dict, years_ahead: float) -> int:
    """Hub round trips the trunk would need to keep its seats per passenger: today's x the growth."""
    g = s["derived"]["demand_growth_per_year"]
    base = ap.trunk_budget(ap.load(), s["cid"])
    return round(base * ((1 + g) ** years_ahead - 1))


def build(cid: str, out: Path | None = None, years: tuple = YEARS, widebody_years: tuple = (0, 3), expansion: tuple = EXPANSION, log=print) -> dict:
    s = setup(cid)
    t0 = time.time()
    def note(msg):
        if log:
            log(f"  [{time.time() - t0:5.0f}s] {msg}")
    # 1. years under the cap vs following demand
    yrs = []
    for k in years:
        capped = run(s, k)
        d = follow_delta(s, k)
        follow = capped if d == 0 else run(s, k, delta=d)
        follow_dest = capped if d == 0 else run(s, k, delta=d, dest=True)
        yrs.append({"years_ahead": k, "fiscal_year": fy_after(s["fy"], k), "follow_delta": d, "capped": capped, "follow": follow, "follow_dest": follow_dest})
        note(f"years +{k}: spill {capped['spill_pax_k']} k, follow +{d}")
    # 2. widebody-centric fleets, under the cap and with the cap lifted
    wb = []
    for k in widebody_years:
        for lift in (0, 20):
            base = None
            for v in WIDEBODY:
                r = run(s, k, delta=lift, overrides=v["overrides"])
                added = v["added"] * WIDEBODY_K_PER_AIRCRAFT_MONTH * 12 * USD_JPY / 1e5
                r.update({"variant": v["id"], "label": v["label"], "added_aircraft": v["added"], "added_aircraft_cost_oku": round(added, 1),
                          "margin_net_oku": round(r["margin_oku"] - added, 1)})
                base = base or r
                r["vs_base"] = {"revenue_oku": round(r["revenue_oku"] - base["revenue_oku"], 1), "operating_cost_oku": round(r["operating_cost_oku"] - base["operating_cost_oku"], 1),
                                "margin_net_oku": round(r["margin_net_oku"] - base["margin_net_oku"], 1), "spill_pax_k": round(r["spill_pax_k"] - base["spill_pax_k"], 1)}
                wb.append({"years_ahead": k, "lift": lift, **r})
                note(f"widebody +{k}y lift {lift} {v['id']}: net {r['vs_base']['margin_net_oku']}")
    # 3. the hub cap lifted: do the destinations take it?
    ex = []
    for k in (0, 3):
        for dl in expansion:
            free = run(s, k, delta=dl)
            capped = run(s, k, delta=dl, dest=True)
            ex.append({"years_ahead": k, "delta_round_trips": dl, "hub_only": free, "with_destinations": capped})
            note(f"expansion +{k}y +{dl}: unusable {capped['unusable_round_trips']}, at cap {capped['destination_at_cap']}")
    sens = sensitivity(s)
    note("sensitivity done")
    dest = ap.load_destinations()
    result = {"company": cid, "sensitivity": sens, "fiscal_year": s["fy"], "demand_growth_per_year": s["derived"]["demand_growth_per_year"],
              "years": yrs, "widebody": wb, "expansion": ex,
              "destinations": {k: {f: v[f] for f in ("name", "routes", "capacity", "binding", "headroom_round_trips", "headroom_source")} for k, v in dest["airports"].items()},
              "assumptions": {"widebody_k_per_aircraft_month": f"no_source: {WIDEBODY_K_PER_AIRCRAFT_MONTH:.0f} k$/機・月（A350-900 を 1 機足す所有またはリースの費用）",
                              "years": "需要は年の伸び率のまま伸ばす（幹線も地方も）。羽田の枠・他社の便数・機材の数は据え置き",
                              "follow": "需要に合わせる場合：羽田の幹線の往復を 今 × (1+伸び)^年 まで増やす（羽田の枠が上がった仮定）",
                              "idle_737": "幹線から外れた 737 は地方路線に回るか止まる。止まった機体を返す節約（ドライリース 250 k$/機・月）は入れていない",
                              "widebody_engines": "A350 のエンジン（Trent XWB）はエンジン計画のデータがないので、サイクルだけ出す",
                              "engines": "エンジンの窓は、幹線の機材割当が実際に飛ばすサイクルで出す（計画の上限 ×1.10 で切らない）",
                              "usd_jpy": USD_JPY},
              "note": "数値はすべて合成データ（路線の旅客・便数・空港の容量は公開値、それ以外は仮定）。p50"}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("company")
    a.add_argument("--out", type=Path)
    args = a.parse_args(argv)
    r = build(args.company, args.out)
    def eng(x, t):
        e = next((e for e in x["engines"] if e["type"] == t), {})
        w = e.get("windows") or {}
        return f"u {e.get('utilisation_multiplier')} ({e.get('utilisation_uncapped')}) earlier {w.get('earlier')} spend {e.get('spend_per_year_oku_yen')}"
    print("years (capped | follow | follow+dest):")
    for y in r["years"]:
        c, f, fd = y["capped"], y["follow"], y["follow_dest"]
        print(f" {y['fiscal_year']}: carried {c['carried_pax_k']} | {f['carried_pax_k']} spill {c['spill_pax_k']} lost {c['lost_revenue_oku']} margin {c['margin_oku']} | +{y['follow_delta']} spill {f['spill_pax_k']} margin {f['margin_oku']} | dest unusable {fd['unusable_round_trips']} margin {fd['margin_oku']}")
        for t in ("737", "767", "787"):
            print(f"    {t}: capped {eng(c, t)} | follow {eng(f, t)}")
    print("widebody:")
    for w in r["widebody"]:
        print(f" +{w['years_ahead']}y lift {w['lift']} {w['variant']}: rt {sum(w['version_round_trips'].values())} used {w['aircraft_used_avg']} spill {w['spill_pax_k']} rev {w['revenue_oku']} op {w['operating_cost_oku']} added {w['added_aircraft_cost_oku']} vs base {w['vs_base']}")
    print("expansion:")
    for x in r["expansion"]:
        h, d = x["hub_only"], x["with_destinations"]
        print(f" +{x['years_ahead']}y +{x['delta_round_trips']}: hub-only rt {h['version_round_trips']} margin {h['margin_oku']} | dest rt {d['version_round_trips']} unusable {d['unusable_round_trips']} at cap {d['destination_at_cap']} margin {d['margin_oku']}")
        for t in ("737", "767", "787"):
            print(f"    {t}: hub-only {eng(h, t)} | dest {eng(d, t)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
