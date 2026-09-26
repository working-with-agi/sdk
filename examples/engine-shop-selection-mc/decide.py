#!/usr/bin/env python3
"""Decision report: the company's requirements cannot always all be met, so build a few
alternatives, test each against several states of the world, price every requirement,
and conclude with a recommendation, what must be decided now, and who must approve what.

  1. cases          base / MRO backlog / LLP-kit crunch / combined stress
  2. requirements   in every case: can all be met? what does relaxing each one save?
  3. alternatives   A all requirements (base)   B budget flexed across years
                    C prepared for stress        D explicit service target
  4. cross-check    every alternative evaluated by Monte Carlo in every case
  5. conclusion     recommended alternative, decisions due this month, approvals,
                    early-removal exceptions with reasons, triggers to revisit

  python decide.py                      # writes report.json and report.html
  python decide.py --workers 8 --scenarios 100
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from shop_mc import Requirements, evaluate, load, sample, solve_saa
from shop_mc.model import InfeasibleError
from shop_mc.urgency import analyse, exceptions

HERE = Path(__file__).resolve().parent

CASES = {
    "base": ("基準", 0.50, "入力どおり"),
    "backlog": ("MRO 混雑", 0.25, "外部工場の TAT が 1 か月延びる（2025〜26 年のエンジン MRO 逼迫）"),
    "crunch": ("LLP 逼迫", 0.15, "LLP キットの調達が 12 か月、手持ち半減"),
    "stress": ("複合ストレス", 0.10, "MRO 混雑 ＋ LLP 逼迫 ＋ 故障率 1.5 倍"),
}

REQS = {
    "budget": ("年度予算を守る", "財務"),
    "buffer": ("予備バッファを割らない", "整備計画"),
    "volume": ("OEM 契約の最低発注量", "調達"),
    "kits_on_hand_only": ("LLP キットは手持ちで回す", "調達"),
    "no_new_spares": ("予備エンジンを増やさない", "経営企画"),
    "service": ("欠航確率 5% 以下", "運航"),
}
ALL_HARD = dict(budget=True, buffer=True, volume=True, kits_on_hand_only=True, no_new_spares=True, service=False)

ALTERNATIVES = {
    "A": ("全要望遵守", "base", dict(ALL_HARD)),
    "B": ("予算を年度間で融通", "base", {**ALL_HARD, "budget": False}),
    "C": ("逼迫に備える", "stress", {**ALL_HARD, "kits_on_hand_only": False, "no_new_spares": False}),
    "D": ("混雑時も欠航目標を守る", "backlog", {**ALL_HARD, "service": True, "no_new_spares": False}),
}


def case_problem(p, case: str):
    if case in ("backlog", "stress"):
        shops = []
        for k in p.shops:
            if k.transport_months > 0:  # external shops only
                k = dataclasses.replace(
                    k, quotes={w: dataclasses.replace(q, tat=q.tat + 1) for w, q in k.quotes.items()}
                )
            shops.append(k)
        p = dataclasses.replace(p, shops=shops)
    if case in ("crunch", "stress"):
        p = dataclasses.replace(p, llp_kit_lead_months=12, llp_kits_on_hand=max(1, p.llp_kits_on_hand // 2))
    if case == "stress":
        p = dataclasses.replace(
            p,
            unsched_rate=p.unsched_rate * 1.5,
            visits=[dataclasses.replace(v, hazard=min(0.5, v.hazard * 1.5)) for v in p.visits],
        )
    return p


def solve_job(args):
    """Worker: solve one (case, requirements) problem."""
    tag, case, req, fleet, shops, n, seed, time_limit = args
    p = case_problem(load(fleet, shops), case)
    t0 = time.perf_counter()
    try:
        plan = solve_saa(p, sample(p, n, seed), req=Requirements(**req), time_limit=time_limit, threads=1)
    except InfeasibleError:
        plan = None
    return tag, plan, time.perf_counter() - t0


def assess(p, plan, sc, budget_check=True):
    """Evaluate a fixed plan in one case: money, service, and every requirement."""
    chosen = [sc.options[i] for i in plan.chosen]
    early_llp = sum(1 for o in chosen if o.workscope in p.llp_workscopes and o.month < p.llp_kit_lead_months)
    # kits are re-planned per case: only what this case's stock and lead time cannot cover
    kits = max(0, early_llp - p.llp_kits_on_hand)
    plan = dataclasses.replace(plan, emergency_kits=kits)
    ev = evaluate(p, plan, sc)
    exp = sc.cost.mean(axis=0)
    over = {}
    for fy, b in p.budget_by_fy.items():
        spend = sum(float(exp[i]) for i in plan.chosen if p.fiscal_year(sc.options[i].month) == fy)
        over[fy] = spend - b
    buffer_breaks = 0
    serviceable = []
    for t in range(p.horizon):
        off = sum(1 for o in chosen if o.month <= t < o.month + o.shop.transport_months + o.tat())
        serviceable.append(p.owned_engines - off + plan.long_spares)
        if serviceable[-1] < p.required_positions[t] + p.buffer[t]:
            buffer_breaks += 1
    vol = [{"shop": k.id, "min": k.min_visits, "planned": sum(1 for o in chosen if o.shop is k)} for k in p.shops if k.min_visits]
    met = {
        "budget": all(v <= 0.01 * p.budget_by_fy[fy] for fy, v in over.items()),  # 1 % sampling tolerance
        "buffer": buffer_breaks == 0,
        "volume": all(v["planned"] >= v["min"] for v in vol),
        "kits_on_hand_only": kits == 0,
        "no_new_spares": plan.long_spares == 0,
        "service": ev.aog_prob <= (p.max_aog_prob or 1.0),
    }
    return {
        "mean": ev.mean, "p90": ev.p90, "cvar90": ev.cvar90, "aog_prob": ev.aog_prob,
        "aog_engine_months": ev.aog_engine_months, "lease_engine_months": ev.lease_engine_months,
        "budget_over": over, "buffer_breaks": buffer_breaks, "emergency_kits": kits,
        "long_spares": plan.long_spares, "volume": vol, "met": met, "serviceable": serviceable,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fleet", type=Path, default=HERE / "data" / "fleet_visits.json")
    ap.add_argument("--shops", type=Path, default=HERE / "data" / "shop_quotes.json")
    ap.add_argument("--scenarios", type=int, default=60, help="in-sample scenarios per solve")
    ap.add_argument("--eval-scenarios", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=int, default=180)
    ap.add_argument("--json-out", type=Path, default=Path("report.json"))
    ap.add_argument("--html-out", type=Path, default=Path("report.html"))
    ap.add_argument("--fragment", action="store_true")
    args = ap.parse_args(argv)

    base = load(args.fleet, args.shops)
    common = (str(args.fleet), str(args.shops), args.scenarios, args.seed, args.time_limit)

    # --- jobs: requirement prices per case + the alternatives -----------------------
    jobs = []
    for case in CASES:
        jobs.append((f"req:{case}:all", case, ALL_HARD, *common))
        for r in ("budget", "buffer", "volume", "kits_on_hand_only", "no_new_spares"):
            jobs.append((f"req:{case}:-{r}", case, {**ALL_HARD, r: False}, *common))
    for key, (_label, case, req) in ALTERNATIVES.items():
        jobs.append((f"alt:{key}", case, req, *common))

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        solved = {tag: (plan, secs) for tag, plan, secs in pool.map(solve_job, jobs)}
    wall = time.perf_counter() - t0

    probs = {c: case_problem(base, c) for c in CASES}
    evals = {c: sample(probs[c], args.eval_scenarios, args.seed + 999) for c in CASES}

    # --- requirement prices ----------------------------------------------------------
    req_table = []
    for case in CASES:
        allp = solved[f"req:{case}:all"][0]
        ev_all = evaluate(probs[case], allp, evals[case]) if allp else None
        all_mean = ev_all.mean if ev_all else None
        # differences smaller than two standard errors are Monte Carlo noise
        noise = 2 * ev_all.stderr if ev_all else None
        row = {"case": case, "all_feasible": allp is not None, "all_mean": all_mean, "noise": noise, "relax": {}}
        for r in ("budget", "buffer", "volume", "kits_on_hand_only", "no_new_spares"):
            pl = solved[f"req:{case}:-{r}"][0]
            if pl is None:
                row["relax"][r] = {"feasible": False}
                continue
            m = evaluate(probs[case], pl, evals[case]).mean
            saving = None if all_mean is None else all_mean - m
            row["relax"][r] = {
                "feasible": True, "mean": m, "saving": saving,
                "binding": saving is not None and saving > noise,
            }
        req_table.append(row)

    # --- alternatives x cases ----------------------------------------------------------
    alts = []
    for key, (label, solved_in, req) in ALTERNATIVES.items():
        plan, secs = solved[f"alt:{key}"]
        if plan is None:
            alts.append({"key": key, "label": label, "solved_in": solved_in, "feasible": False, "relaxed": [r for r, v in req.items() if not v and r != "service"]})
            continue
        by_case = {c: assess(probs[c], plan, evals[c]) for c in CASES}
        weighted = sum(CASES[c][1] * by_case[c]["mean"] for c in CASES)
        alts.append({
            "key": key, "label": label, "solved_in": solved_in, "feasible": True,
            "relaxed": [r for r, v in req.items() if not v and r != "service"],
            "enforced_service": req.get("service", False),
            "status": plan.status, "solve_seconds": round(secs, 1),
            "weighted_mean": weighted, "cases": by_case, "_plan": plan,
        })

    # --- recommendation ---------------------------------------------------------------
    feas = [a for a in alts if a["feasible"]]
    target = base.max_aog_prob or 1.0
    ok = [a for a in feas if a["cases"]["base"]["aog_prob"] <= target and a["cases"]["backlog"]["aog_prob"] <= target]
    pool_ = ok or feas
    rec = min(pool_, key=lambda a: a["weighted_mean"])
    cheapest = min(feas, key=lambda a: a["weighted_mean"])
    plan = rec["_plan"]
    sc_base = evals["base"]
    urg = analyse(base, plan, sample(base, 1500, args.seed + 999))
    exc = exceptions(base, plan, sample(base, 1500, args.seed + 999))

    approvals = []
    rb = rec["cases"]["base"]
    for fy, v in rb["budget_over"].items():
        if v > 0.01 * base.budget_by_fy[fy]:
            approvals.append({"owner": "財務", "what": f"{fy} 予算超過 {v:,.0f} k$ の承認"})
    if rb["long_spares"]:
        approvals.append({"owner": "経営企画", "what": f"長期リース予備エンジン {rb['long_spares']} 基の追加"})
    if rb["emergency_kits"]:
        approvals.append({"owner": "調達", "what": f"LLP キット {rb['emergency_kits']} セットの緊急調達"})
    for v in rb["volume"]:
        if v["planned"] < v["min"]:
            approvals.append({"owner": "調達", "what": f"{v['shop']} 最低発注量の不足 {v['min'] - v['planned']} 件（違約金）"})

    rows = []
    for i in sorted(plan.chosen, key=lambda i: sc_base.options[i].month):
        o = sc_base.options[i]
        rows.append({
            "esn": o.visit.esn, "operator": o.visit.operator, "watch": o.visit.watch,
            "shop": o.shop.id, "workscope": o.workscope, "rush": o.rush,
            "month": o.month, "month_label": base.month_label(o.month),
            "limit_label": base.month_label(o.visit.latest),
            "exp_off_wing": float(sc_base.down[:, i].mean()),
        })
    shop_mix = {}
    for r in rows:
        shop_mix[r["shop"]] = shop_mix.get(r["shop"], 0) + 1

    conclusion = build_conclusion(base, rec, cheapest, alts, req_table, urg, exc, approvals)

    for a in alts:
        a.pop("_plan", None)
    out = {
        "meta": {
            "fleet": "737-800 x 76（本体 62 ＋ 地域子会社 14）", "positions_max": max(base.required_positions),
            "owned_engines": base.owned_engines, "visits": len(base.visits), "start": base.start, "horizon": base.horizon,
            "month_labels": [base.month_label(t) for t in range(base.horizon)],
            "peak_months": [t for t in range(base.horizon) if base.is_peak(t)],
            "required_positions": base.required_positions, "buffer": base.buffer,
            "budgets": base.budget_by_fy, "service_target": base.max_aog_prob,
            "scenarios": args.scenarios, "eval_scenarios": args.eval_scenarios,
            "workers": args.workers, "solves": len(jobs), "wall_seconds": round(wall, 1),
            "shops": [{"id": k.id, "name": k.name, "slots": k.slots} for k in base.shops],
            "watch": sum(v.watch for v in base.visits),
        },
        "cases": {c: {"label": v[0], "weight": v[1], "what": v[2]} for c, v in CASES.items()},
        "requirements": {r: {"label": v[0], "owner": v[1]} for r, v in REQS.items()},
        "requirement_prices": req_table,
        "alternatives": alts,
        "recommended": rec["key"],
        "plan": rows, "shop_mix": shop_mix,
        "urgency": urg, "exceptions": exc, "approvals": approvals,
        "conclusion": conclusion,
    }
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    html = (HERE / "report_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(out, ensure_ascii=False, default=float)
    )
    if not args.fragment:
        html = (
            '<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            "</head><body>\n" + html + "\n</body></html>\n"
        )
    args.html_out.write_text(html, encoding="utf-8")

    print(f"{len(jobs)} solves on {args.workers} workers: {wall:.0f}s")
    def fmt_relax(v):
        if not v["feasible"]:
            return "infeasible"
        return "ok" if v.get("saving") is None else f"{v['saving']:+,.0f}"

    for row in req_table:
        rel = ", ".join(f"-{r}:{fmt_relax(v)}" for r, v in row["relax"].items())
        print(f"  {CASES[row['case']][0]:<8} all={'ok' if row['all_feasible'] else 'INFEASIBLE'}  {rel}")
    for a in alts:
        if not a["feasible"]:
            print(f"  {a['key']} {a['label']}: infeasible")
            continue
        cs = "  ".join(f"{CASES[c][0]} {a['cases'][c]['mean']:,.0f}/{a['cases'][c]['aog_prob']:.1%}" for c in CASES)
        print(f"  {a['key']} {a['label']:<12} weighted {a['weighted_mean']:,.0f}  {cs}")
    print("recommended:", rec["key"], rec["label"])
    print(conclusion["headline"])
    return 0


def build_conclusion(p, rec, cheapest, alts, req_table, urg, exc, approvals):
    base_row = next(r for r in req_table if r["case"] == "base")
    conflicts = [CASES[r["case"]][0] for r in req_table if not r["all_feasible"]]
    now = [e["esn"] for e in urg["engines"] if e["status"] == "now"]
    soon = [e["esn"] for e in urg["engines"] if e["status"] == "soon"]
    rb = rec["cases"]["base"]
    headline = (
        f"推奨は案{rec['key']}「{rec['label']}」。基準ケースで期待総コスト {rb['mean']:,.0f} k$、"
        f"欠航確率 {rb['aog_prob']:.1%}。"
    )
    points = []
    if conflicts:
        points.append(f"全要望を同時に満たせないケース: {'、'.join(conflicts)}。どの要望を緩めるかの判断が必要です。")
    else:
        points.append("どのケースでも全要望を同時に満たす計画は存在します。差は費用とリスクの配分です。")
    prices = [
        (REQS[r][0], v["saving"]) for r, v in base_row["relax"].items() if v.get("feasible") and v.get("saving") is not None
    ]
    prices = sorted([x for x in prices if x[1] > (base_row["noise"] or 0)], key=lambda x: -x[1])
    if prices:
        points.append("基準ケースで要望を1つ緩めた場合の節約: " + "、".join(f"{n} {s:,.0f} k$" for n, s in prices[:3]) + "。")
    if rec is not cheapest:
        d = rec["weighted_mean"] - cheapest["weighted_mean"]
        points.append(
            f"最安は案{cheapest['key']}（加重平均 {cheapest['weighted_mean']:,.0f} k$）だが、"
            f"MRO 混雑時の欠航確率 {cheapest['cases']['backlog']['aog_prob']:.1%} が目標 {p.max_aog_prob:.0%} を超えるため、"
            f"{d:,.0f} k$ の上乗せで案{rec['key']}を選ぶ。"
        )
    decisions = []
    if now:
        decisions.append(f"今月中に入場先・ワークスコープを確定: {'、'.join(now)}")
    if soon:
        decisions.append(f"3 か月以内に確定: {'、'.join(soon)}")
    kits = rec["cases"]["base"]["emergency_kits"]
    decisions.append(f"LLP キットの発注計画（手持ち {p.llp_kits_on_hand} セット、調達 {p.llp_kit_lead_months} か月）" + (f"、緊急調達 {kits} セット" if kits else ""))
    early = [e for e in exc if e["months_early"] > 0]
    exc_line = f"期限前の取卸しは {len(early)} 基。理由は要監視（故障リスク）、工場枠、予算年度、繁忙期回避のいずれかで、エンジンごとに付録に記載。"
    triggers = [
        "外部工場の TAT が見積もりより 1 か月以上延び始めたら（MRO 混雑ケースへ移行）",
        "LLP キットの納期が 12 か月を超えたら（LLP 逼迫ケースへ移行）",
        "要監視エンジンの EGT 劣化が加速したら（期限を前倒しして再計算）",
        "為替が見積もり時から ±10% 以上動いたら",
    ]
    return {"headline": headline, "points": points, "decisions": decisions, "exceptions": exc_line,
            "approvals": approvals, "triggers": triggers}


if __name__ == "__main__":
    sys.exit(main())
