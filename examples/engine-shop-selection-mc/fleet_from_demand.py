#!/usr/bin/env python3
"""From demand to fleet: how many aircraft, and how many engines, the demand needs.

The layer between the demand (demand.py, plan_from_demand.py) and the engine plan:

  1. aircraft the months need      seats needed = demand (RPK, p10/p50/p90) / target load
                                   factor; seats one aircraft offers = seats x sectors per
                                   day x stage x days x utilisation; aircraft needed = ratio
                                   + aircraft down for airframe checks; against the fleet.
                                   A 24-month window month by month, and a 20-year long view
                                   year by year (with the fleet's retirements from runout).
  2. engines the fleet needs       installed = 2 x aircraft flying; spares = the buffer the
                                   engine plan carries + the short-term lease the shortage
                                   watch asked for; how the engines fly (cycles) under this
                                   demand, handed to plan_from_demand.build_fleet so the shop
                                   visit windows move with it.
  3. levers when short or long     fly each aircraft more (up to UTIL_CAP), wet-lease
                                   aircraft, keep aircraft past their exit, or spill the
                                   demand -- each with its cost and what it does to the
                                   engines (extra cycles, visits pulled forward, spares).
  4. the planning-season numbers   the figures a planner fixes in April: this and next
                                   fiscal year's aircraft needed vs owned, the months short,
                                   the maintenance spend the demand growth adds, and the
                                   peak month (October) in load factor, engines and the
                                   economics of adding flights.

Everything is synthetic; assumptions without a source are flagged no_source in the output.

  python fleet_from_demand.py jal --out fleet/jal.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import company
import demand as demand_mod
import plan_from_demand as pfd
import route_fleet as rf

HERE = Path(__file__).resolve().parent
DAYS = 365 / 12
USD_JPY = 157.0                       # the series converts k$ to 億円 at this rate (assumption, no_source)
WET_LEASE_K_PER_AC_MONTH = 850.0      # 737-800 wet lease incl. crew (k$/aircraft-month; no_source, order of magnitude)
DRY_LEASE_K_PER_AC_MONTH = 250.0      # dry lease of an aircraft kept past its exit (k$/aircraft-month; no_source)
BAND = {"p10": -1.0, "p50": 0.0, "p90": 1.0}


def _fy(label: str, fy_start: int = 4) -> str:
    y, m = int(label[:4]), int(label[5:7])
    return f"FY{y if m >= fy_start else y - 1}"


def _label(start: str, t: int) -> str:
    y0, m0 = map(int, start.split("-"))
    return f"{y0 + (m0 - 1 + t) // 12}-{(m0 - 1 + t) % 12 + 1:02d}"


def demand_rpk(D: dict, cid: str, derived: dict, start: str, months: int, rule: str = "mixed") -> list[dict]:
    """The company's 737-800 RPK by month with a 10-90 % band.
    Level: the company's share of the market's last fiscal year, times the 737-800 share;
    shape: the market's seasonal index; trend: plan_from_demand's growth by horizon;
    band: the spread of the company's known months around the seasonal shape, widened with
    the horizon (assumption)."""
    C = D["companies"][cid]
    mv = demand_mod.market_view(D)
    idx = {c["month"]: c["demand_index"] for c in mv["seasonal"]}
    fy = D["market"]["fiscal_years"][-1]
    known = [x for x in C["months"] if x.get("share_rpk")]
    share = sum(x["share_rpk"] for x in known) / len(known) if known else 0.25
    share737 = C["share_737_800_of_domestic_ask"]
    level = fy["rpk"] / 12 * share * share737                     # million RPK per average month, 737-800 part
    # the band: residuals of the known months around level x seasonal index
    res = []
    for x in known:
        m = int(x["m"][5:]); pred = fy["rpk"] / 12 * share * idx[m]
        if x.get("rpk"):
            res.append(x["rpk"] / pred - 1)
    sd = (sum(r * r for r in res) / len(res)) ** 0.5 if res else 0.04
    g, gl = derived["demand_growth_per_year"], derived["demand_growth_long_run"]
    out = []
    for t in range(months):
        lab = _label(start, t); m = int(lab[5:])
        trend = (1 + (g if rule == "recent" else pfd.growth_at(t, g, gl))) ** (t / 12)   # "recent": the last 2 years' growth only; "mixed": blended with the long run
        p50 = level * idx[m] * trend
        width = 1.2816 * (sd + 0.02 * (t / 12) ** 0.5)           # 10-90 %: z x (month noise + trend uncertainty growing with sqrt(horizon))
        out.append({"t": t, "label": lab, "fy": _fy(lab), "p10": round(p50 * (1 - width), 1), "p50": round(p50, 1), "p90": round(p50 * (1 + width), 1), "trend": round(trend, 4)})
    return out


def aircraft_needed(D: dict, cid: str, cfg: dict, rpk: list[dict], derived: dict) -> dict:
    C = D["companies"][cid]
    A = D["assumptions"]
    seats, stage, lf_t = C["seats_737_800"], A["stage_length_km"], A["lf_capacity_threshold"]
    subs = cfg.get("subfleets") or []
    n_ac = sum(x["aircraft"] for x in subs) or cfg["aircraft"]["total"]
    sectors_day = (sum(x["aircraft"] * x["cycles_per_year"] for x in subs) / n_ac / 365) if subs else 5.3
    u = derived["utilisation_multiplier"]
    ask_ac_month = seats * sectors_day * min(pfd.UTIL_CAP, u) * stage * DAYS / 1e6      # million seat-km one aircraft offers in a month
    ask_ac_cap = seats * sectors_day * pfd.UTIL_CAP * stage * DAYS / 1e6
    checks = {int(k): v for k, v in cfg["aircraft"]["airframe_checks"].items()}
    total = cfg["aircraft"]["total"]
    rows = []
    for r in rpk:
        m = int(r["label"][5:])
        need = {}
        for q in ("p10", "p50", "p90"):
            flying = r[q] / lf_t / ask_ac_month
            need[q] = round(flying + checks[m], 2)
        rows.append({**{k: r[k] for k in ("t", "label", "fy")}, "rpk_p50": r["p50"], "flying_p50": round(r["p50"] / lf_t / ask_ac_month, 2),
                     "in_checks": checks[m], "need_p10": need["p10"], "need_p50": need["p50"], "need_p90": need["p90"],
                     "owned": total, "gap_p50": round(total - need["p50"], 2), "gap_p90": round(total - need["p90"], 2),
                     "short_p90": bool(need["p90"] > total), "lf_if_all_fly": round(r["p50"] / ((total - checks[m]) * ask_ac_month), 3)})
    return {"rows": rows, "params": {"seats": seats, "stage_km": stage, "lf_target": lf_t, "sectors_per_day": round(sectors_day, 2),
                                     "utilisation_multiplier": u, "ask_per_aircraft_month": round(ask_ac_month, 2), "ask_per_aircraft_month_at_cap": round(ask_ac_cap, 2),
                                     "airframe_checks_by_month": checks, "aircraft_total": total},
            "how": "要る機数 ＝ 需要（RPK）÷ 目標の搭乗率 ÷ 1 機が 1 か月に出せる座席キロ（座席 × 1 日の便数 × 稼働倍率 × 区間距離 × 日数）＋ 機体整備で止まる機"}


def long_view(D: dict, cid: str, cfg: dict, derived: dict, runout: dict | None, years: int = 20) -> list[dict]:
    """Year by year: aircraft needed at the long-run growth vs the fleet with its exits."""
    C = D["companies"][cid]; A = D["assumptions"]
    fy = D["market"]["fiscal_years"][-1]
    known = [x for x in C["months"] if x.get("share_rpk")]
    share = sum(x["share_rpk"] for x in known) / len(known) if known else 0.25
    subs = cfg.get("subfleets") or []
    n_ac = sum(x["aircraft"] for x in subs) or cfg["aircraft"]["total"]
    sectors_day = (sum(x["aircraft"] * x["cycles_per_year"] for x in subs) / n_ac / 365) if subs else 5.3
    ask_ac_year = C["seats_737_800"] * sectors_day * A["stage_length_km"] * 365 / 1e6
    checks_avg = sum(cfg["aircraft"]["airframe_checks"].values()) / 12
    g, gl = derived["demand_growth_per_year"], derived["demand_growth_long_run"]
    # exits by year from the run-out (engines retired / 2 ~ aircraft leaving)
    exits = {}
    if runout:
        for y in runout.get("by_year", []):
            exits[int(str(y["year"])[:4])] = y.get("retired", 0)
    y0 = int(fy["fy"][2:]) + 1
    owned = cfg["aircraft"]["total"]; gone = 0
    out = []
    for k in range(years):
        yr = y0 + k
        gone += exits.get(yr, 0) / 2
        trend = (1 + pfd.growth_at(12 * k, g, gl)) ** k
        rpk_y = fy["rpk"] * share * C["share_737_800_of_domestic_ask"] * trend
        need = rpk_y / A["lf_capacity_threshold"] / ask_ac_year + checks_avg
        fleet = max(0.0, owned - gone)
        out.append({"fy": f"FY{yr}", "rpk_737_p50": round(rpk_y), "need_p50": round(need, 1), "fleet_after_exits": round(fleet, 1), "gap": round(fleet - need, 1),
                    "note": "退役後の機数は退役までの入場列（runout）の退役エンジン数 ÷ 2。置き換え機は含まない" if exits else "退役の情報なし（機数は一定）"})
    return out


def engines_needed(cfg: dict, cur_fleet: dict, ac: dict, shortage: dict | None) -> dict:
    buffer = cur_fleet["buffer_spares"][0]
    extra = (shortage or {}).get("fix", {}).get("short_lease_engines", 0)
    owned = cfg["engines"]["owned"]
    rows = []
    for r in ac["rows"]:
        flying = r["flying_p50"]; flying90 = r["need_p90"] - r["in_checks"]
        inst = 2 * math.ceil(min(flying, cfg["aircraft"]["total"]))
        inst90 = 2 * math.ceil(min(flying90, cfg["aircraft"]["total"]))
        rows.append({"t": r["t"], "label": r["label"], "installed_p50": inst, "installed_p90": inst90, "spares_buffer": buffer, "spares_short_lease": extra,
                     "need_total_p50": inst + buffer + extra, "owned": owned, "headroom_p50": owned - (inst + buffer + extra), "headroom_p90": owned - (inst90 + buffer + extra),
                     "required_positions_in_plan": cur_fleet["required_positions"][r["t"]] if r["t"] < len(cur_fleet["required_positions"]) else None})
    worst = min(rows, key=lambda x: x["headroom_p90"])
    return {"rows": rows, "owned": owned, "installed_now": cfg["engines"]["installed"], "spares_buffer": buffer, "spares_short_lease": extra,
            "worst": {"label": worst["label"], "headroom_p90": worst["headroom_p90"], "headroom_p50": worst["headroom_p50"]},
            "how": "要るエンジン ＝ 飛ぶ機数 × 2 ＋ 予備（計画の緩衝 ＋ 不足の見張りが求めた短期リース）。持っているのは所有エンジン数。計画側の必要基数（required_positions）を横に並べて突き合わせる"}


def levers(D: dict, cid: str, cfg: dict, ac: dict, norms: dict, growth: dict | None, runout: dict | None = None) -> dict:
    """What to do in a short month, and what an idle aircraft costs in a long month."""
    C = D["companies"][cid]; A = D["assumptions"]
    P = ac["params"]
    yld = C["yield_yen_per_rpk"]; lf_t = A["lf_capacity_threshold"]
    cycles_ac_month = P["sectors_per_day"] * DAYS
    run_cycles = (growth or {}).get("params", {}).get("run_cycles", 11753)
    cost_visit = (growth or {}).get("params", {}).get("cost_per_visit_k", 8067)
    mx_k_per_cycle = 2 * cost_visit / run_cycles                       # maintenance a cycle consumes, both engines (k$)
    rev_k_per_ac_month = P["ask_per_aircraft_month"] * lf_t * yld * 1e6 / 1e3 / USD_JPY   # revenue an aircraft-month carries at the target L/F (k$)
    retiring = {int(str(y["year"])[:4]): y.get("retired", 0) / 2 for y in (runout or {}).get("by_year", [])}   # aircraft leaving that calendar year
    rows = []
    for r in ac["rows"]:
        short = max(0.0, r["need_p90"] - r["owned"])
        if short <= 0:
            continue
        delay_cover = min(short, retiring.get(int(r["label"][:4]), 0.0)) if runout else short
        # 1. fly each aircraft more: headroom to UTIL_CAP
        u_room = pfd.UTIL_CAP / P["utilisation_multiplier"] - 1
        ac_from_util = (r["owned"] - r["in_checks"]) * u_room
        util_cover = min(short, ac_from_util)
        util_cycles = util_cover * cycles_ac_month
        # 2. wet lease the rest
        wet = max(0.0, short - util_cover)
        # 4. spill instead
        spill_rev = short * rev_k_per_ac_month
        rows.append({"label": r["label"], "short_aircraft_p90": round(short, 2), "levers": [
            {"lever": "1 機あたりの飛び方を増やす", "aircraft": round(util_cover, 2), "cost_k": round(util_cycles * mx_k_per_cycle), "engine_effect": f"エンジン・サイクル +{util_cycles:,.0f}（入場の前倒し {util_cycles / run_cycles:.2f} 件分）", "limit": f"稼働の上限 ×{pfd.UTIL_CAP}"},
            {"lever": "機体を短期で借りる（ウェットリース）", "aircraft": round(wet, 2), "cost_k": round(wet * WET_LEASE_K_PER_AC_MONTH), "engine_effect": "自社エンジンに影響なし（借りた機のエンジンは貸し手）", "limit": "no_source: 850 k$/機・月"},
            {"lever": "退役を遅らせる", "aircraft": round(delay_cover, 2), "cost_k": round(delay_cover * (DRY_LEASE_K_PER_AC_MONTH + cycles_ac_month * mx_k_per_cycle)), "engine_effect": "晩年のエンジンの入場が 1 回増える可能性（型式の時計）", "limit": "その年に退役する機（runout の退役エンジン ÷ 2）まで" if runout else "退役の情報なし（上限は不足分）"},
            {"lever": "見送る（乗せられない需要）", "aircraft": round(short, 2), "cost_k": round(spill_rev), "engine_effect": "なし", "limit": f"失う売上 ＝ 機数 × 1 機の月の座席キロ × 搭乗率 {lf_t} × 単価 {yld} 円"}]})
    idle = [{"label": r["label"], "idle_aircraft_p50": round(r["gap_p50"], 2), "carrying_cost_k": round(r["gap_p50"] * DRY_LEASE_K_PER_AC_MONTH)} for r in ac["rows"] if r["gap_p50"] > 1]
    return {"short_months": rows, "long_months": idle, "params": {"usd_jpy": USD_JPY, "wet_lease_k_per_ac_month": WET_LEASE_K_PER_AC_MONTH, "dry_lease_k_per_ac_month": DRY_LEASE_K_PER_AC_MONTH,
                                                                     "maintenance_k_per_cycle_both_engines": round(mx_k_per_cycle, 3), "revenue_k_per_aircraft_month": round(rev_k_per_ac_month), "run_cycles": run_cycles, "cost_per_visit_k": cost_visit},
            "note": "足りない月（p90）の打ち手を、費用（k$）とエンジン側への影響で同じ表に。余る月は遊ぶ機の維持費。単価は仮定（no_source）"}


def planning_season(D: dict, cid: str, ac: dict, eng: dict, lv: dict, norms: dict, derived: dict, growth: dict | None) -> dict:
    """The numbers the series uses in April: this and next fiscal year, the peak month."""
    rows = ac["rows"]
    fys = sorted({r["fy"] for r in rows})
    by_fy = {}
    for fy in fys:
        rr = [r for r in rows if r["fy"] == fy]
        by_fy[fy] = {"months": len(rr), "need_p50_max": max(r["need_p50"] for r in rr), "need_p90_max": max(r["need_p90"] for r in rr), "owned": rr[0]["owned"],
                     "short_months_p90": [r["label"] for r in rr if r["short_p90"]], "avg_gap_p50": round(sum(r["gap_p50"] for r in rr) / len(rr), 2)}
    g = derived["demand_growth_per_year"]
    spend_year_k = norms["spend_per_year_k"]
    added_k = spend_year_k * g                                  # visits and spend scale with cycles flown (plan_from_demand's norm scaling)
    peak = max(rows[:12], key=lambda r: r["need_p50"])
    e = next(x for x in eng["rows"] if x["t"] == peak["t"])
    add = None
    if growth:
        gm = next((m for m in growth["months"] if m["label"] == peak["label"]), None)
        if gm:
            add = {"add_aircraft": gm["add_aircraft"], "revenue_oku_yen": gm["revenue_oku_yen"], "binding": gm["binding"]}
    peak_levers = next((x for x in lv["short_months"] if x["label"] == peak["label"]), None)
    return {"as_of": "4 月（年度の始まり）に需要の見込みから計画を固める時点の数字", "fiscal_years": by_fy,
            "maintenance": {"spend_per_year_k": round(spend_year_k), "spend_per_year_oku_yen": round(spend_year_k * USD_JPY / 1e5, 1), "demand_growth": g,
                            "added_by_growth_k": round(added_k), "added_by_growth_oku_yen": round(added_k * USD_JPY / 1e5, 1),
                            "how": "平年の整備費 × 需要の伸び（入場も費用もエンジン・サイクルに比例、plan_from_demand の按分）"},
            "peak_month": {"label": peak["label"], "lf_if_all_fly": peak["lf_if_all_fly"], "need_p50": peak["need_p50"], "need_p90": peak["need_p90"], "owned": peak["owned"],
                           "engines_headroom_p50": e["headroom_p50"], "engines_headroom_p90": e["headroom_p90"], "engines_short_p90": max(0, -e["headroom_p90"]),
                           "adding_flights": add, "levers": peak_levers},
            "note": "外で使う数字（逼迫月の搭乗率・エンジンの不足・増便の損得）は peak_month と突き合わせる"}


def consistency(D: dict, cid: str, ac: dict) -> dict:
    """Does the 737 share (no_source) fit the fleet? If every aircraft flying still needs more than the
    target L/F at the peak, the share is too high for this fleet; report the share that would fit."""
    C = D["companies"][cid]; lf_t = D["assumptions"]["lf_capacity_threshold"]
    peak = max(ac["rows"], key=lambda r: r["lf_if_all_fly"])
    share = C["share_737_800_of_domestic_ask"]
    implied = round(share * lf_t / peak["lf_if_all_fly"], 3)
    ok = peak["lf_if_all_fly"] <= lf_t + 0.05
    return {"share_737_800": share, "share_source": C.get("share_source", "no_source"), "peak_lf_if_all_fly": peak["lf_if_all_fly"], "peak_label": peak["label"],
            "fits_fleet": ok, "share_that_fits": implied,
            "verdict": ("整合：全機が飛べば目標の搭乗率で運べる" if ok else
                        f"不整合：全機が飛んでも搭乗率 {peak['lf_if_all_fly']:.0%} が要る。737 のシェア {share} は機材 {peak['owned']} 機に対して大きすぎる。目標搭乗率で整合するシェアは {implied}。シェアは仮定として明示し、こちらの値を検討")}


def month_table(start: str, months: int) -> list[dict]:
    """Model t (start = t 0) against the series' fiscal-year month (April = month 1)."""
    out = []
    for t in range(months):
        lab = _label(start, t); m = int(lab[5:])
        out.append({"t": t, "label": lab, "fy": _fy(lab), "fy_month": (m - 4) % 12 + 1})
    return out


SLOT_SCENARIOS = (-9, -5, -3, 0, 3, 5)    # hub trunk round trips a day added/removed by the 2028 re-allocation (about 5 % of the allocation is ±9)


def route_layer(D: dict, cid: str, cfg: dict, cur: dict, rpk: list[dict], ac: dict, eng: dict, growth: dict | None, derived: dict, norms: dict,
                scenarios: tuple = SLOT_SCENARIOS, routes: bool = True) -> dict:
    """The trunk routes inside the hub's slots (airport layer) with every aircraft type that flies them
    (airline layer, fleet assignment by month), the 737's regional network by seat-km, the two
    reconciled with the seat-km whole, the cycles each type flies handed to build_fleet, the busy-month
    decision (lease or spill), and the 2028 slot re-allocation scenarios."""
    conf = json.loads(company.CONFIG.read_text(encoding="utf-8"))
    fleets = {f["type"]: f for f in conf["companies"][cid].get("fleets", [])}
    total = cfg["aircraft"]["total"]
    checks737 = {int(k): v for k, v in cfg["aircraft"]["airframe_checks"].items()}
    R = rf.load()
    types = rf.types_of(R, cid)
    P = ac["params"]; lf_t = P["lf_target"]
    wait = {e["t"]: math.ceil(max(0, -e["headroom_p90"]) / 2) for e in eng["rows"]}
    avg737 = sum(b["p50"] for b in rpk[:12]) / 12
    g = derived["demand_growth_per_year"]
    to_start = (1 + g) ** 2.25                                                       # 2024 (mid-year) -> 2026-10
    state = {}
    def set_trunk(v):
        state["share"] = min(1.0, v / avg737)
        return round(state["share"], 3)
    def regional_need(t):
        return rpk[t]["p50"] * (1 - state["share"]) / lf_t / P["ask_per_aircraft_month"]
    ctx = {"checks_rate": {m: n / total for m, n in checks737.items()}, "fleet_737": total, "engine_wait": wait,
           "set_trunk_737_rpk": set_trunk, "regional_need": regional_need, "to_start": to_start}
    trunk = rf.build(cid, D, rpk, ctx)
    base_share = state["share"]
    # regional network and the reconciliation with the seat-km whole (737 only)
    others, recon = [], []
    for r, b, a in zip(trunk["rows"], rpk, ac["rows"]):
        m = int(b["label"][5:])
        reg = regional_need(r["t"])
        used = r["used_p50"]["737"]
        others.append({"t": r["t"], "label": r["label"], "rpk_regional_p50": round(b["p50"] * (1 - base_share), 1), "need_p50": round(reg, 1),
                       "trunk_737_used_p50": used, "trunk_737_available": r["available"]["737"], "slack_p50": round(r["available"]["737"] - used, 1)})
        recon.append({"t": r["t"], "label": r["label"], "trunk_737_p50": used, "regional_p50": round(reg, 1), "in_checks": checks737[m], "lease_p50": r["lease_p50"],
                      "sum_p50": round(used + reg + checks737[m], 1), "whole_by_seat_km_p50": a["need_p50"], "fleet": total})
    sectors_day = P["sectors_per_day"]
    fy_next = sorted({r["fy"] for r in trunk["rows"]})[1]

    def engine_rows(tr, with_windows=True):
        months = [r for r in tr["rows"] if r["fy"] == fy_next] or tr["rows"][:12]
        out = []
        for ty in types:
            k = ty["type"]
            used = sum(r["used_p50"][k] for r in months) / 12
            cyc = sum(r["cycles_per_day_p50"][k] for r in months) / 12
            per_ac = cyc / used if used else 0.0
            if k == "737":
                fleet_n, base_day = total, sectors_day
            elif k in fleets:
                f = fleets[k]; fleet_n = f["aircraft"]["total"]
                base_day = sum(x["aircraft"] * x["cycles_per_year"] for x in f["subfleets"]) / fleet_n / 365
            else:
                fleet_n, base_day = None, None
            row = {"type": k, "name": ty["name"], "engine": ty["engine"], "trunk_aircraft_used_avg": round(used, 1), "trunk_cycles_per_aircraft_day": round(per_ac, 2),
                   "fleet_aircraft": fleet_n, "fleet_cycles_per_aircraft_day_now": round(base_day, 2) if base_day else None, "trunk_engines_installed_avg": round(2 * used, 1)}
            if fleet_n and used:
                blended = (used * per_ac + (fleet_n - used) * base_day) / fleet_n
                u = round(min(pfd.UTIL_CAP, max(1.0, blended / base_day)), 4)
                row.update({"blended_cycles_per_aircraft_day": round(blended, 2), "utilisation_multiplier": u})
                if with_windows:
                    new_fleet, n_new = pfd.build_fleet(cid, {**derived, "utilisation_multiplier": u}, None if k == "737" else k)
                    cur_k = cur if k == "737" else json.loads((HERE / "data" / cid / k / "fleet.json").read_text(encoding="utf-8"))
                    shift = pfd.compare_inputs(cur_k, new_fleet)
                    row.update({"windows": {x: shift[x] for x in ("due_now", "due_new", "earlier", "newly_due", "mean_shift_months") if x in shift},
                                "spend_per_year_k": round(n_new["spend_per_year_k"]), "spend_per_year_oku_yen": round(n_new["spend_per_year_k"] * USD_JPY / 1e5, 1)})
            elif not fleet_n:
                row["note"] = "エンジン計画のデータがない機種（companies.json に未登録）。サイクルだけ出す"
            out.append(row)
        return out

    eng_types = engine_rows(trunk)
    ver = trunk["version"]["by_type"]
    levers_ = []
    for r in trunk["rows"]:
        if not r.get("short_p90") and all(r["used_p90"][k] <= ver[k] for k in ver):
            continue
        items = []
        for ty in types:
            k = ty["type"]; d = r["used_p90"][k] - ver[k]
            if d > 0:
                items.append({"lever": "地方路線から 737 を回す" if k == "737" else f"{ty['name']} を版より多く入れる", "aircraft": d,
                              "engine_effect": f"{ty['engine']} のサイクルが増える（パターンの便数ぶん）", "limit": f"使える機数 {r['available'][k]}"})
        if r["lease_p90"]:
            items.append({"lever": "737 を借りる（ウェットリース）", "aircraft": r["lease_p90"], "cost_k": r["lease_p90"] * R["lease"]["k_per_aircraft_month"], "engine_effect": "自社エンジンに影響なし", "limit": R["lease"]["note"]})
        if r["spill_p90_pax_k"] > 0.5:
            items.append({"lever": "見送る（乗せられない旅客）", "pax_k": r["spill_p90_pax_k"], "by_route": {k: v for k, v in r["spill_by_route_p90"].items() if v > 0.5}, "engine_effect": "なし", "limit": "失う売上は下限"})
        levers_.append({"label": r["label"], "levers": items})
    fy_next = sorted({r["fy"] for r in trunk["rows"]})[1]
    dec = []
    for r in trunk["rows"]:
        if r["fy"] != fy_next:
            continue
        cost = r["lease_p50"] * R["lease"]["k_per_aircraft_month"] * USD_JPY / 1e5
        rec = (r["no_lease_p50"]["lost_revenue_k"] - r["cost_k_p50"]["lost_revenue"]) * USD_JPY / 1e5
        dec.append({"label": r["label"], "lease_aircraft": r["lease_p50"], "lease_cost_oku": round(cost, 2), "revenue_recovered_oku": round(rec, 2),
                    "net_oku": round(rec - cost, 2), "lost_if_not_oku": round(r["no_lease_p50"]["lost_revenue_k"] * USD_JPY / 1e5, 2),
                    "lost_after_oku": round(r["cost_k_p50"]["lost_revenue"] * USD_JPY / 1e5, 2), "used": r["used_p50"], "decision": "借りる" if r["lease_p50"] else "借りない"})
    tally = {"aircraft_months_leased": sum(x["lease_aircraft"] for x in dec), "lease_cost_oku": round(sum(x["lease_cost_oku"] for x in dec), 2),
             "revenue_recovered_oku": round(sum(x["revenue_recovered_oku"] for x in dec), 2), "net_oku": round(sum(x["net_oku"] for x in dec), 2),
             "lost_revenue_after_oku": round(sum(x["lost_after_oku"] for x in dec), 2), "lost_if_never_lease_oku": round(sum(x["lost_if_not_oku"] for x in dec), 2),
             "months_leased": [x["label"] for x in dec if x["lease_aircraft"]]}
    peak = max((r for r in trunk["rows"] if r["fy"] == fy_next), key=lambda r: r["pax_k_p50"])

    # 2028 slot re-allocation scenarios: the hub trunk round trips ±n, demand share follows the frequencies
    scen = []
    for dlt in scenarios:
        if dlt == 0:
            tr = trunk
        else:
            ctx_s = {**ctx, "set_trunk_737_rpk": None}
            tr = rf.build(cid, D, rpk, ctx_s, delta=dlt, quantiles=("p50",), detail=False, fiscal_years={fy_next})
        fy_rows = [r for r in tr["rows"] if r["fy"] == fy_next]
        e737 = next(e for e in engine_rows(tr, with_windows=(dlt in (min(scenarios), 0, max(scenarios)))) if e["type"] == "737")
        scen.append({"delta_round_trips": dlt, "budget": tr["airport"]["budget"], "version_round_trips": tr["version"]["round_trips"], "share": tr["version"]["share"],
                     "pax_k": round(sum(r["carried_p50_pax_k"] for r in fy_rows), 1), "revenue_oku": round(sum(r["revenue_carried_oku_p50"] for r in fy_rows), 1),
                     "lost_revenue_oku": round(sum(r["cost_k_p50"]["lost_revenue"] for r in fy_rows) * USD_JPY / 1e5, 2),
                     "operating_cost_oku": round(sum(r["cost_k_p50"]["operating"] for r in fy_rows) * USD_JPY / 1e5, 1),
                     "lease_aircraft_months": sum(r["lease_p50"] for r in fy_rows),
                     "aircraft_used_avg": {t["type"]: round(sum(r["used_p50"][t["type"]] for r in fy_rows) / len(fy_rows), 1) for t in types},
                     "engine_737": {k: e737.get(k) for k in ("trunk_aircraft_used_avg", "trunk_cycles_per_aircraft_day", "blended_cycles_per_aircraft_day", "utilisation_multiplier", "windows", "spend_per_year_oku_yen")}})
    base = next(x for x in scen if x["delta_round_trips"] == 0)
    for x in scen:
        x["vs_base"] = {"pax_k": round(x["pax_k"] - base["pax_k"], 1), "revenue_oku": round(x["revenue_oku"] - base["revenue_oku"], 1),
                        "operating_cost_oku": round(x["operating_cost_oku"] - base["operating_cost_oku"], 1),
                        "margin_oku": round((x["revenue_oku"] - x["operating_cost_oku"]) - (base["revenue_oku"] - base["operating_cost_oku"]), 1)}
    return {**trunk, "others": others,
            "reconciliation": {"rows": recon, "note": "737 ＝ 幹線の 737（機材割当）＋ 地方路線（会社の 737 の需要 × 幹線以外の割合、座席キロ）＋ 機体整備。座席キロ一本の全体と比べる"},
            "engine_flying": eng_types, "levers": levers_,
            "decisions": {"fiscal_year": fy_next, "peak_month": peak["label"], "months": dec, "year_end": tally,
                          "note": "借りるかどうかは機材割当の中で決まる（リース費 ＜ 取り戻す売上 のときだけ借りる）。借りた機体も羽田の枠がなければ飛べない",
                          "rules_note": "伸びの規則は 2 年先までは直近の値を使う（plan_from_demand.growth_at）ので、24 か月の窓では混ぜる規則と直近の規則は一致する"},
            "slot_scenarios": {"fiscal_year": fy_next, "rows": scen,
                               "how": "2028 年の再配分で、羽田の幹線の往復便数が ±n になった場合。変化はすべて幹線に寄せる（上限の見積もり）。他社の便数は据え置き。自社の需要は便数の比率で動く。年度の数字は p50",
                               "reference": "前回（2019）は 19 枠回収・16 枠再配分。配分の 5% は約 9 枠"},
            "month_table": month_table(cur["start"], cur["horizon_months"])}


def build(cid: str, out: Path | None = None, runout_path: Path | None = None, shortage_path: Path | None = None, growth_path: Path | None = None, solve: bool = False,
          scenarios: tuple = SLOT_SCENARIOS, routes: bool = True) -> dict:
    D = demand_mod.load()
    conf = json.loads(company.CONFIG.read_text(encoding="utf-8"))
    cfg, common = company.fleet_cfg(conf, cid, None)
    cur = json.loads((HERE / "data" / cid / "fleet.json").read_text(encoding="utf-8"))
    derived = pfd.derive(D, cid, cur["start"])
    runout = json.loads(runout_path.read_text(encoding="utf-8")) if runout_path and runout_path.exists() else None
    shortage = json.loads(shortage_path.read_text(encoding="utf-8")) if shortage_path and shortage_path.exists() else None
    growth = json.loads(growth_path.read_text(encoding="utf-8")) if growth_path and growth_path.exists() else None
    rpk = demand_rpk(D, cid, derived, cur["start"], cur["horizon_months"])
    ac = aircraft_needed(D, cid, cfg, rpk, derived)
    lv_long = long_view(D, cid, cfg, derived, runout)
    eng = engines_needed(cfg, cur, ac, shortage)
    # how the engines fly under this demand: the windows re-derived with the same utilisation and shape
    new_fleet, n_new = pfd.build_fleet(cid, derived)
    shift = pfd.compare_inputs(cur, new_fleet)
    norms = {"spend_per_year_k": n_new["spend_per_year_k"], "visits_per_year": n_new["visits_per_year"]}
    lv = levers(D, cid, cfg, ac, norms, growth, runout)
    cons = consistency(D, cid, ac)
    trunk = route_layer(D, cid, cfg, cur, rpk, ac, eng, growth, derived, norms, scenarios) if routes else None
    season = planning_season(D, cid, ac, eng, lv, norms, derived, growth)
    result = {"company": cid, "name": cfg["name"], "start": cur["start"], "horizon_months": cur["horizon_months"],
              "demand_rpk_737": rpk, "aircraft": ac, "long_view": lv_long, "engines": eng,
              "engine_flying": {"cycles_per_aircraft_month": round(ac["params"]["sectors_per_day"] * DAYS * ac["params"]["utilisation_multiplier"], 1), "utilisation_multiplier": derived["utilisation_multiplier"],
                                "windows": {k: shift[k] for k in ("due_now", "due_new", "earlier", "newly_due", "mean_shift_months") if k in shift}, "norms": {k: round(v, 2) for k, v in norms.items()}},
              "levers": lv, "planning_season": season, "consistency": cons, "trunk": trunk, "derived": {k: derived[k] for k in ("demand_growth_per_year", "demand_growth_long_run", "utilisation_multiplier")},
              "assumptions": {"lf_target": D["assumptions"]["lf_threshold_source"], "share_737_800": D["companies"][cid].get("share_source", "no_source"), "band": "no_source: 10〜90% の幅は既知月の残差の標準偏差 ＋ 年 2% × √(年数) を z=1.28 倍",
                              "wet_lease": "no_source: 850 k$/機・月", "dry_lease": "no_source: 250 k$/機・月", "usd_jpy": f"{USD_JPY}",
                              "missing_months": "既知でない月（JAL 2025-09〜12）は市場の季節指数 × シェアで補う"},
              "note": "需要 → 何機 → 何基。要る機数は p10/p50/p90、機数の判定は p90、費用は p50。数値はすべて合成データ"}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--runout", type=Path, help="runout/<company>.json (exits for the long view)")
    ap.add_argument("--shortage", type=Path, help="shortage/<company>.json (short-term lease engines the watch asked for)")
    ap.add_argument("--growth", type=Path, help="growth/<company>.json (adding flights at the peak month)")
    a = ap.parse_args(argv)
    r = build(a.company, a.out, a.runout or HERE / "runout" / f"{a.company}.json", a.shortage or HERE / "shortage" / f"{a.company}.json", a.growth or HERE / "growth" / f"{a.company}.json")
    s = r["planning_season"]; p = s["peak_month"]
    print(f"{r['name']}: aircraft {r['aircraft']['params']['aircraft_total']}, sectors/day {r['aircraft']['params']['sectors_per_day']}, ASK/ac-month {r['aircraft']['params']['ask_per_aircraft_month']} M")
    for fy, v in s["fiscal_years"].items():
        print(f"  {fy}: need p50 max {v['need_p50_max']}, p90 max {v['need_p90_max']}, owned {v['owned']}, short months (p90) {v['short_months_p90']}")
    print(f"  maintenance {s['maintenance']['spend_per_year_oku_yen']} 億円/yr, +{s['maintenance']['added_by_growth_oku_yen']} 億円 from growth {s['maintenance']['demand_growth']:+.1%}")
    print(f"  peak {p['label']}: L/F if all fly {p['lf_if_all_fly']}, need p50 {p['need_p50']} / p90 {p['need_p90']} vs {p['owned']}, engines headroom p50 {p['engines_headroom_p50']} / p90 {p['engines_headroom_p90']}, adding flights {p['adding_flights']}")
    print(f"  engine windows: due {r['engine_flying']['windows']}")
    print(f"  consistency: {r['consistency']['verdict']}")
    tr = r["trunk"]
    print(f"  trunk version by type {tr['version']['by_type']}, round trips {tr['version']['round_trips']}, share {tr['version']['share']}, avg seats {tr['version']['avg_seats']}")
    for x in tr["rows"][6:18]:
        print(f"    {x['label']} used {x['used_p50']} lease {x['lease_p50']}/{x['lease_p90']} spill {x['spill_p50_pax_k']}/{x['spill_p90_pax_k']} lf {x['lf_p50']}")
    for e in tr["engine_flying"]:
        print(f"  {e['name']}: trunk {e['trunk_aircraft_used_avg']} ac, {e['trunk_cycles_per_aircraft_day']} cyc/ac-day, u {e.get('utilisation_multiplier')}, windows {e.get('windows')}, spend {e.get('spend_per_year_oku_yen')}")
    print(f"  year-end {tr['decisions']['year_end']}")
    for x in tr["slot_scenarios"]["rows"]:
        print(f"  slots {x['delta_round_trips']:+d}: pax {x['pax_k']} rev {x['revenue_oku']} lost {x['lost_revenue_oku']} vs {x['vs_base']} 737 {x['engine_737']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
