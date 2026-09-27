#!/usr/bin/env python3
"""The plan for adding flights (足す計画), built on the flight schedule and bounded by
demand on one side and engines on the other.

Inputs
  flight schedule   data/<company>/flights_plan.json when present ({"YYYY-MM": flights per
                    day for the 737-800 fleet}); otherwise derived from the base schedule
                    (aircraft x sectors per day x the demand layer's seasonal index)
  demand headroom   the demand layer: in months where the carrier's load factor is at or
                    above the threshold, the seats it could not sell (spilled RPK) are the
                    demand that extra flights would carry
  engine headroom   the run-out's operations side: spare serviceable engines / 2 = aircraft
                    that could fly

Per month: aircraft that can be added = min(demand headroom in aircraft, engine headroom),
extra flights per day, extra ASK, revenue at the yield; and what that asks of the engine
plan: extra cycles -> the utilisation multiplier -> engines whose limit moves earlier
(re-derived with plan_from_demand.build_fleet) and the extra visits and cost at the norms.

  python growth_plan.py jal --demand demand/jal.json --runout runout/jal.json --out growth/jal.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import plan_from_demand as pfd

HERE = Path(__file__).resolve().parent
LOOKAHEAD = 24        # months of the window
DAYS = 30.4


def base_schedule(cfg: dict, D: dict, labels: list[str]) -> dict:
    """Flights per day for the 737-800 fleet by month: aircraft x sectors/day x seasonal index."""
    subs = cfg.get("subfleets") or []
    ac = sum(x["aircraft"] for x in subs) or cfg["aircraft"]["total"]
    sectors = (sum(x["aircraft"] * x["cycles_per_year"] for x in subs) / ac / 365) if subs else 5.3
    seas = {c["month"]: c["demand_index"] for c in D["market"]["seasonal"]}
    return {l: round(ac * sectors * seas.get(int(l[5:]), 1.0), 1) for l in labels}


def build(cid: str, demand_path: Path, runout_path: Path) -> dict:
    D = json.loads(demand_path.read_text(encoding="utf-8"))
    R = json.loads(runout_path.read_text(encoding="utf-8"))
    conf = json.loads((HERE / "data" / "companies.json").read_text(encoding="utf-8"))
    cfg = conf["companies"][cid]
    P = D["engines"]["params"]; A = D["assumptions"]
    seats, stage, yld, th = P["seats"], P["stage_km"], P["yield_yen_per_rpk"], A["lf_capacity_threshold"]
    cpm = P["cycles_per_aircraft_month"]
    ops = R["ops"][:LOOKAHEAD]
    labels = [o["label"] for o in ops]
    fp = HERE / "data" / cid / "flights_plan.json"
    sched = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else base_schedule(cfg, D, labels)
    sched_src = "data/%s/flights_plan.json（便の計画）" % cid if fp.exists() else "基準の便数（機数 × 1 日の便数 × 需要の季節指数）から導出"
    # demand headroom by calendar month: spilled RPK of the carrier (all types) x the 737-800 share -> aircraft-months
    by_m = {}
    for r in D["carrier"]["months"]:
        by_m.setdefault(int(r["m"][5:]), []).append(r)
    ask_ac = cpm * seats * stage / 1e6                 # million seat-km an aircraft flies in a month
    rows = []
    for o in ops:
        m = int(o["label"][5:])
        rs = by_m.get(m, [])
        spilled = sum((r["spilled_rpk"] or 0) for r in rs) / max(1, len(rs)) if rs else 0.0
        lf = sum(r["lf"] for r in rs if r["lf"] is not None) / max(1, sum(1 for r in rs if r["lf"] is not None)) / 100 if rs else None
        demand_ac = spilled * P["share_737_800"] / th / ask_ac if spilled else 0.0     # aircraft-months the unmet demand would fill at the threshold L/F
        engine_ac = max(0, o["margin"]) // 2
        add_ac = int(min(demand_ac, engine_ac))
        fpd = sched.get(o["label"], 0.0)
        add_fpd = add_ac * cpm / DAYS
        ask_add = add_ac * ask_ac
        rev = ask_add * th * yld * 1e6 / 1e8                 # 億円 at the threshold L/F
        rows.append({"t": o["t"], "label": o["label"], "flights_per_day": fpd, "lf_month": round(lf, 3) if lf else None, "spilled_rpk": round(spilled, 1),
                     "demand_headroom_ac": round(demand_ac, 1), "engine_headroom_ac": int(engine_ac), "add_aircraft": add_ac, "add_flights_per_day": round(add_fpd, 1),
                     "add_ask": round(ask_add, 1), "revenue_oku_yen": round(rev, 2), "binding": "需要" if demand_ac <= engine_ac else "エンジン",
                     "share_of_schedule": round(add_fpd / fpd, 3) if fpd else None})
    ac_months = sum(r["add_aircraft"] for r in rows)
    extra_cycles = ac_months * cpm * 2                     # two engines per aircraft
    b = json.loads((HERE / "baselines" / f"{cid}-2026-10.json").read_text(encoding="utf-8"))
    norms = b["norms"]
    run_cycles = norms["mean_run_months"] * cpm
    extra_visits = extra_cycles / run_cycles
    cost_per_visit = norms["spend_per_year_k"] / norms["visits_per_year"]
    extra_cost_k = extra_visits * cost_per_visit
    # what it does to the windows: the fleet flies more -> utilisation multiplier over the window
    fleet = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))
    base_ac_months = LOOKAHEAD * (sum(x["aircraft"] for x in cfg.get("subfleets", [])) or cfg["aircraft"]["total"])
    util = 1 + ac_months / base_ac_months
    seas = {c["month"]: c["demand_index"] for c in D["market"]["seasonal"]}
    new, _n = pfd.build_fleet(cid, {"flight_index": seas, "demand_growth_per_year": 0.0, "utilisation_multiplier": util})
    cmp = pfd.compare_inputs(fleet, new)
    rev_total = sum(r["revenue_oku_yen"] for r in rows)
    usd = 150.0                                            # yen per USD for the net line (assumption)
    net = rev_total - extra_cost_k * usd / 1e5             # k$ -> 億円
    return {"company": cid, "schedule_source": sched_src, "months": rows,
            "totals": {"aircraft_months": ac_months, "add_ask": round(sum(r["add_ask"] for r in rows), 1), "revenue_oku_yen": round(rev_total, 1),
                       "extra_cycles": round(extra_cycles), "extra_visits": round(extra_visits, 1), "extra_maintenance_k": round(extra_cost_k), "extra_maintenance_oku_yen": round(extra_cost_k * usd / 1e5, 1),
                       "net_oku_yen": round(net, 1), "binding_months": {"需要": sum(1 for r in rows if r["add_aircraft"] and r["binding"] == "需要"), "エンジン": sum(1 for r in rows if r["add_aircraft"] and r["binding"] == "エンジン")},
                       "months_with_adds": sum(1 for r in rows if r["add_aircraft"])},
            "engine_side": {"utilisation_multiplier": round(util, 4), "due_now": cmp["due_now"], "due_new": cmp["due_new"], "earlier": cmp["earlier"], "newly_due": cmp["newly_due"],
                            "mean_shift_months": cmp["mean_shift_months"], "shifts": [s for s in cmp["shifts"] if s["limit_shift"] or s.get("newly_due")][:20],
                            "note": "足した分だけ機隊全体の稼働が上がるとして、今日の状態から窓を引き直したもの。期限が早まる機は判断期限も早まる"},
            "params": {"seats": seats, "stage_km": stage, "yield_yen_per_rpk": yld, "lf_threshold": th, "share_737_800": P["share_737_800"], "cycles_per_aircraft_month": cpm, "usd_jpy": usd,
                       "cost_per_visit_k": round(cost_per_visit), "run_cycles": round(run_cycles)},
            "note": ("足す計画：月ごとに、需要の余地（満たせなかった需要 × 737-800 の割合 ÷ 閾値の利用率）とエンジンの余力（稼働可能 − 必要 − 予備）÷ 2 の小さい方だけ機を足す。"
                     "売上は閾値の利用率 × 単価。整備費は平年の 1 入場あたり費用 × 増えるサイクル ÷ 1 回の翼上寿命。単価・割合・閾値・為替は仮定（C）。乗務員・燃料・空港の費用は含まない")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--demand", type=Path)
    ap.add_argument("--runout", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = build(a.company, a.demand or HERE / "demand" / f"{a.company}.json", a.runout or HERE / "runout" / f"{a.company}.json")
    p = a.out or HERE / "growth" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    T, E = out["totals"], out["engine_side"]
    print(f"{a.company}: {T['months_with_adds']} months with adds, {T['aircraft_months']} aircraft-months, +{T['add_ask']} M seat-km, revenue {T['revenue_oku_yen']} 億円, "
          f"extra visits {T['extra_visits']} ({T['extra_maintenance_oku_yen']} 億円), net {T['net_oku_yen']} 億円; binding {T['binding_months']}; "
          f"engine side: utilisation x{E['utilisation_multiplier']}, due {E['due_now']} -> {E['due_new']}, earlier {E['earlier']}, newly {E['newly_due']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
