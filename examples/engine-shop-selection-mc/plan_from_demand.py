#!/usr/bin/env python3
"""Turn past demand into the plan's operations assumptions, and show what that does to
the engine plan (過去の需要から計画の前提に直す).

From the demand layer (data/demand.json) three assumptions are derived:
  flight_index            the seasonal shape of demand (market RPK by month / mean) in
                          place of the fixed index the engine model assumed;
  demand_growth_per_year  the trend of demand (CAGR of the market's fiscal-year RPK over
                          the post-COVID years) -> the positions the schedule needs grow
                          through the window;
  utilisation_multiplier  how much more each aircraft must fly so supply catches demand
                          at the load-factor threshold (ASK needed / ASK now), capped.

The same 20-year simulation is rebuilt with those assumptions (company.fleet_for) and the
result is compared with the current input: engines due inside the window, their windows
(earliest / limit), the norms (visits and spend per year), the positions required per
month. Then the plan is re-solved on the derived input and compared with the frozen
plan of record (cost, visits, AOG risk).

  python plan_from_demand.py jal --out demand/jal-plan.json [--no-solve]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import baseline
import company
import demand
import lifecycle

HERE = Path(__file__).resolve().parent
UTIL_CAP = 1.10          # an aircraft cannot fly more than +10 % per year of what it flies now (assumption)
GROWTH_YEARS = ("FY2023", "FY2025")


def derive(D: dict, cid: str) -> dict:
    mv = demand.market_view(D)
    fi = {c["month"]: c["demand_index"] for c in mv["seasonal"]}
    fy = {f["fy"]: f for f in D["market"]["fiscal_years"]}
    a, b = fy[GROWTH_YEARS[0]], fy[GROWTH_YEARS[1]]
    n = int(GROWTH_YEARS[1][2:]) - int(GROWTH_YEARS[0][2:])
    g = (b["rpk"] / a["rpk"]) ** (1 / n) - 1
    th = D["assumptions"]["lf_capacity_threshold"]
    C = D["companies"][cid]
    known = [x for x in C["months"] if x["ask"] and x["rpk"]]
    lf_now = sum(x["rpk"] for x in known) / sum(x["ask"] for x in known) if known else b["lf"] / 100
    ask_ratio = lf_now * (1 + g) / th          # ASK next year / ASK now to hold L/F at the threshold with demand grown
    util = min(UTIL_CAP, max(1.0, ask_ratio))
    return {"flight_index": fi, "demand_growth_per_year": round(g, 4), "utilisation_multiplier": round(util, 4),
            "how": {"flight_index": "市場の月次 RPK ÷ 平均（航空輸送統計速報 13 か月）",
                    "growth": f"{GROWTH_YEARS[0]}→{GROWTH_YEARS[1]} の市場 RPK の年率（{a['rpk']:,} → {b['rpk']:,} 百万人キロ）",
                    "utilisation": f"利用率 {lf_now:.1%} を閾値 {th:.0%} に戻しつつ需要 +{g:.1%} を運ぶのに要る供給の比 {ask_ratio:.3f}、上限 {UTIL_CAP}",
                    "lf_now": round(lf_now, 4), "ask_ratio": round(ask_ratio, 4)}}


def build_fleet(cid: str, overrides: dict) -> tuple[dict, dict]:
    """The same history (20-year simulation, current assumptions, same seed) up to today;
    from today the derived operations: the windows of the same engines re-derived under
    the new utilisation and seasonal shape, the positions the schedule needs with the
    demand trend. The past is not rewritten -- only the future assumptions change."""
    conf = json.loads(company.CONFIG.read_text(encoding="utf-8"))
    cfg, common = company.fleet_cfg(conf, cid, None)
    base_cfg = {**cfg, "contract": {**cfg["contract"], "quotes": {w: q for w, q in common["quotes"].items() if w != "source"}}}
    lifecycle.configure(base_cfg)
    seed = cfg["lifecycle_seed"]
    visits, shelf, short, state, T = lifecycle.simulate(seed, years=lifecycle.YEARS)
    n = lifecycle.norms(visits, shelf, short, T)
    # from today: the derived operations
    lifecycle.configure({**base_cfg, **{k: overrides[k] for k in ("flight_index", "utilisation_multiplier")}})
    rows = lifecycle.window(state, T)
    cur = json.loads((HERE / "data" / cid / "fleet.json").read_text(encoding="utf-8"))
    H = cur["horizon_months"]
    g = float(overrides.get("demand_growth_per_year", 0.0))
    cap = 2 * cfg["aircraft"]["total"]
    required = [min(cap, int(math.ceil(lifecycle.needed_positions(t) * (1 + g) ** (t / 12)))) for t in range(H)]
    u = float(overrides["utilisation_multiplier"])
    new = json.loads(json.dumps(cur))
    new["engines"] = [{k: r[k] for k in ("esn", "operator", "window", "allowed_workscopes", "watch", "hazard", "driver", "egt_margin", "llp_remaining")} for r in rows]
    new["required_positions"] = required
    new["terminal_engines"] = max(required) + cur["buffer_spares"][0]
    new["budget"]["by_fiscal_year"] = {fy: round(v * u, -2) for fy, v in cur["budget"]["by_fiscal_year"].items()}
    new["unscheduled_removals"]["background_engines"] = cfg["engines"]["owned"] - len(rows)
    new["meta"]["derivation"]["flight_index"] = lifecycle.FLIGHT_INDEX
    new["meta"]["derivation"]["subfleets"] = [{**x, "cycles_per_year": round(x["cycles_per_year"] * u)} for x in cur["meta"]["derivation"]["subfleets"]]
    new["meta"]["description"] = cur["meta"]["description"] + f" 需要の層から導いた前提（稼働 x{u:.3f}、需要の伸び {g:+.1%}/年、季節の形は市場の実績）で窓を引き直したもの。"
    new["engine_state"] = {"note": cur.get("engine_state", {}).get("note", ""), "engines": lifecycle.snapshot(state, T)}
    # the norms scale with utilisation (visits and spend per year are per engine-cycle)
    n_new = {**n, "visits_per_year": n["visits_per_year"] * u, "spend_per_year_k": n["spend_per_year_k"] * u}
    lifecycle.configure(base_cfg)
    return new, n_new


def compare_inputs(cur: dict, new: dict) -> dict:
    a = {e["esn"]: e for e in cur["engines"]}
    b = {e["esn"]: e for e in new["engines"]}
    shifts = []
    for esn in sorted(set(a) | set(b)):
        if esn in a and esn in b:
            d = b[esn]["window"][1] - a[esn]["window"][1]
            if d or a[esn]["allowed_workscopes"] != b[esn]["allowed_workscopes"]:
                shifts.append({"esn": esn, "limit_shift": d, "window_now": a[esn]["window"], "window_new": b[esn]["window"],
                               "ws_now": a[esn]["allowed_workscopes"][0], "ws_new": b[esn]["allowed_workscopes"][0]})
        elif esn in b:
            shifts.append({"esn": esn, "limit_shift": None, "window_now": None, "window_new": b[esn]["window"], "ws_now": None, "ws_new": b[esn]["allowed_workscopes"][0], "newly_due": True})
        else:
            shifts.append({"esn": esn, "limit_shift": None, "window_now": a[esn]["window"], "window_new": None, "ws_now": a[esn]["allowed_workscopes"][0], "ws_new": None, "no_longer_due": True})
    req_diff = [nb - na for na, nb in zip(cur["required_positions"], new["required_positions"])]
    return {"due_now": len(a), "due_new": len(b), "newly_due": sum(1 for s in shifts if s.get("newly_due")), "no_longer_due": sum(1 for s in shifts if s.get("no_longer_due")),
            "earlier": sum(1 for s in shifts if s["limit_shift"] is not None and s["limit_shift"] < 0), "later": sum(1 for s in shifts if s["limit_shift"] is not None and s["limit_shift"] > 0),
            "mean_shift_months": round(sum(s["limit_shift"] for s in shifts if s["limit_shift"] is not None) / max(1, sum(1 for s in shifts if s["limit_shift"] is not None)), 2),
            "shifts": shifts, "required_now": cur["required_positions"], "required_new": new["required_positions"], "required_diff": req_diff,
            "buffer_now": cur["buffer_spares"][0], "buffer_new": new["buffer_spares"][0],
            "budget_now": cur["budget"]["by_fiscal_year"], "budget_new": new["budget"]["by_fiscal_year"]}


def solve(fleet_path: Path, shops_path: Path, scenarios: int, seed: int, time_limit: int) -> dict | None:
    _a, _c, summ, rows = baseline.solve_summary(((), "base", str(fleet_path), str(shops_path), scenarios, seed, 800, time_limit, ("budget",)))
    if summ is None:
        return None
    return {"total_cost": summ["total_cost"], "aog_prob": summ["aog_prob"], "visits": len(rows), "p90": summ.get("p90"), "relaxed": summ.get("relaxed", []),
            "by_ws": {ws: sum(1 for r in rows if r["workscope"] == ws) for ws in ("PR", "CORE", "FULL")}}


def build(cid: str, do_solve: bool = True, scenarios: int = 40, seed: int = 42, time_limit: int = 90) -> dict:
    D = demand.load()
    ov = derive(D, cid)
    cur = json.loads((HERE / "data" / cid / "fleet.json").read_text(encoding="utf-8"))
    cur_norms = cur["meta"]["derivation"]["norms_by_subfleet"]
    new, n_new = build_fleet(cid, {k: ov[k] for k in ("flight_index", "demand_growth_per_year", "utilisation_multiplier")})
    b = json.loads((HERE / "baselines" / f"{cid}-2026-10.json").read_text(encoding="utf-8"))
    out = {"company": cid, "derived": ov, "current": {"flight_index": cur["meta"]["derivation"]["flight_index"], "subfleets": cur["meta"]["derivation"]["subfleets"]},
           "inputs": compare_inputs(cur, new),
           "norms": {"now": {k: b["norms"][k] for k in ("visits_per_year", "spend_per_year_k", "usd_per_efh", "mean_run_months")},
                     "new": {k: n_new[k] for k in ("visits_per_year", "spend_per_year_k", "usd_per_efh", "mean_run_months")},
                     "note": "導いた前提の平年値は、稼働の倍率で按分（入場も費用もエンジン・サイクルあたり）"},
           "plan": {"now": {"total_cost": b["plan_of_record"]["total_cost"], "aog_prob": b["plan_of_record"]["aog_prob"], "visits": b["plan_of_record"]["shop_visits"], "p90": b["plan_of_record"].get("p90")}},
           "note": ("過去の需要から導いた前提（季節の形・伸び・稼働）で同じ 20 年シミュレーションを回し直し、今の入力と比べる。"
                    "稼働が上がれば寿命部品と EGT の限界が早まり入場の窓が前に動く。季節の形が変われば繁忙期と必要エンジン数が変わる。伸びれば必要な位置が増え予備と退役のペースが変わる")}
    out_fleet = HERE / "data" / cid / "fleet_demand.json"
    out_fleet.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if do_solve:
        shops = HERE / "data" / cid / "shops.json"
        out["plan"]["new"] = solve(out_fleet, shops, scenarios, seed, time_limit)
        if out["plan"]["new"]:
            out["plan"]["delta"] = {k: out["plan"]["new"][k] - out["plan"]["now"][k] for k in ("total_cost", "aog_prob", "visits") if out["plan"]["now"].get(k) is not None}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-solve", action="store_true")
    ap.add_argument("--scenarios", type=int, default=40)
    ap.add_argument("--time-limit", type=int, default=90)
    a = ap.parse_args(argv)
    out = build(a.company, do_solve=not a.no_solve, scenarios=a.scenarios, time_limit=a.time_limit)
    p = a.out or HERE / "demand" / f"{a.company}-plan.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    d, i, n = out["derived"], out["inputs"], out["norms"]
    print(f"{a.company}: growth {d['demand_growth_per_year']:+.1%}/yr, utilisation x{d['utilisation_multiplier']}, due {i['due_now']} -> {i['due_new']} "
          f"(new {i['newly_due']}, gone {i['no_longer_due']}, earlier {i['earlier']}, later {i['later']}, mean shift {i['mean_shift_months']:+.1f} mo); "
          f"norms {n['now']['visits_per_year']:.1f} -> {n['new']['visits_per_year']:.1f} visits/yr, {n['now']['spend_per_year_k']:,.0f} -> {n['new']['spend_per_year_k']:,.0f} k$/yr")
    if out["plan"].get("new"):
        pn, pw = out["plan"]["now"], out["plan"]["new"]
        print(f"  plan: cost {pn['total_cost']:,.0f} -> {pw['total_cost']:,.0f} k$, visits {pn['visits']} -> {pw['visits']}, AOG {pn['aog_prob']:.1%} -> {pw['aog_prob']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
