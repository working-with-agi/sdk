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
# Default priority when requirements conflict (highest first). Airworthiness (hard limits,
# watch-list engines) is above all of these and is never relaxed. Override with
# "requirement_priority" in the fleet file -- the order is the company's call.
DEFAULT_PRIORITY = ["service", "buffer", "volume", "budget", "kits_on_hand_only", "no_new_spares"]

ALL_HARD = dict(budget=True, buffer=True, volume=True, kits_on_hand_only=True, no_new_spares=True, service=False)

ALTERNATIVES = {
    "A": ("全要望遵守", "base", dict(ALL_HARD)),
    "B": ("予算を年度間で融通", "base", {**ALL_HARD, "budget": False}),
    "C": ("逼迫に備える", "stress", {**ALL_HARD, "kits_on_hand_only": False, "no_new_spares": False}),
    "D": ("混雑時も欠航目標を守る", "backlog", {**ALL_HARD, "service": True, "no_new_spares": False}),
}


def case_problem(p, case: str):
    """The world a plan is made for. A case may carry a level after '@': 'backlog@1.6' is
    congestion of 1.6 months (default 1), 'crunch@14' a kit lead of 14 months (default 12),
    so a world can be built from what the leading indicators actually showed."""
    level = None
    if "@" in case:
        case, lv = case.split("@", 1)
        level = float(lv)
    if case in ("backlog", "stress"):
        extra = 1 if level is None or case == "stress" else level
        shops = []
        for k in p.shops:
            if k.transport_months > 0:  # external shops only
                k = dataclasses.replace(
                    k, quotes={w: dataclasses.replace(q, tat=q.tat + extra) for w, q in k.quotes.items()}
                )
            shops.append(k)
        p = dataclasses.replace(p, shops=shops)
    if case in ("crunch", "stress"):
        lead = 12 if level is None or case == "stress" else int(round(level))
        p = dataclasses.replace(p, llp_kit_lead_months=lead, llp_kits_on_hand=max(1, p.llp_kits_on_hand // 2))
    if case == "stress":
        p = dataclasses.replace(
            p,
            unsched_rate=p.unsched_rate * 1.5,
            visits=[dataclasses.replace(v, hazard=min(0.5, v.hazard * 1.5)) for v in p.visits],
        )
    return p


def priority_of(fleet_path) -> list[str]:
    raw = json.loads(Path(fleet_path).read_text(encoding="utf-8"))
    return raw.get("requirement_priority", DEFAULT_PRIORITY)


def ladder_job(args):
    """Worker: enforce every requirement, then relax the lowest-priority one at a time
    until a plan exists. Returns the steps taken."""
    case, priority, fleet, shops, n, seed, time_limit = args
    p = case_problem(load(fleet, shops), case)
    sc = sample(p, n, seed)
    req = {k: True for k in priority}
    steps = []
    for drop in [None] + priority[::-1]:
        if drop:
            req[drop] = False
        try:
            plan = solve_saa(p, sc, req=Requirements(**req), time_limit=time_limit, threads=1)
            steps.append({"relaxed": drop, "feasible": True})
            return case, steps, plan
        except InfeasibleError:
            steps.append({"relaxed": drop, "feasible": False})
    return case, steps, None


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
    ap.add_argument("--levers", type=Path, default=Path("levers.json"), help="output of levers.py (optional)")
    ap.add_argument("--explore", type=Path, default=Path("explore.json"), help="output of explore.py (optional)")
    ap.add_argument("--actions", type=Path, default=Path("actions.json"), help="output of actions.py (optional)")
    ap.add_argument("--sensitivity", type=Path, default=Path("sensitivity.json"), help="output of sensitivity.py (optional)")
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

    priority = priority_of(args.fleet)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        ladders_f = pool.map(ladder_job, [(c, priority, *common) for c in CASES])
        solved = {tag: (plan, secs) for tag, plan, secs in pool.map(solve_job, jobs)}
        ladders = {c: (steps, plan) for c, steps, plan in ladders_f}
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

    def lexi(a):
        # requirements in priority order, each counted as met only if it holds in the
        # base case and under MRO backlog; then cost
        met = tuple(0 if (a["cases"]["base"]["met"][r] and a["cases"]["backlog"]["met"][r]) else 1 for r in priority)
        return met + (a["weighted_mean"],)

    for a in feas:
        a["met_in_priority"] = [
            {"req": r, "met": bool(a["cases"]["base"]["met"][r] and a["cases"]["backlog"]["met"][r])} for r in priority
        ]
    rec = min(feas, key=lexi)
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

    analysis = load_analysis(args)
    conclusion = build_conclusion(base, rec, cheapest, alts, req_table, urg, exc, approvals, analysis,
                                  priority=priority, ladders=ladders)

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
        "priority": priority,
        "ladders": {
            c: {"steps": steps, "mean": (evaluate(probs[c], plan, evals[c]).mean if plan else None),
                "aog": (evaluate(probs[c], plan, evals[c]).aog_prob if plan else None)}
            for c, (steps, plan) in ladders.items()
        },
        "alternatives": alts,
        "recommended": rec["key"],
        "plan": rows, "shop_mix": shop_mix,
        "urgency": urg, "exceptions": exc, "approvals": approvals,
        "conclusion": conclusion,
        "analysis": analysis,
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


def load_analysis(args) -> dict:
    out = {}
    if args.levers.exists():
        out["levers"] = json.loads(args.levers.read_text(encoding="utf-8"))["levers"]
    if args.explore.exists():
        e = json.loads(args.explore.read_text(encoding="utf-8"))
        out["explore"] = {k: e[k] for k in ("factors", "labels", "patterns", "rules", "rule_fit", "effects", "wall_seconds")}
        out["explore"]["n"] = len(e["runs"])
    if args.actions.exists():
        out["actions"] = json.loads(args.actions.read_text(encoding="utf-8"))
    if args.sensitivity.exists():
        runs = json.loads(args.sensitivity.read_text(encoding="utf-8"))["runs"]
        be = sorted((r for r in runs if r["kind"] == "breakeven" and r["feasible"]), key=lambda r: r["f"]["midlife"])
        out["breakeven"] = [{"price": r["f"]["midlife"], "swaps": r["swaps"], "mean": r["mean"], "aog": r["aog_prob"]} for r in be]
        out["coupling"] = [
            {"owned": r["owned"], "value": r["f"]["value"], "substitute": r["f"]["substitute"],
             "mean": r.get("mean"), "aog": r.get("aog_prob"), "early": r.get("early_months")}
            for r in runs if r["kind"] == "coupling"
        ]
    return out


def build_conclusion(p, rec, cheapest, alts, req_table, urg, exc, approvals, analysis=None,
                     priority=None, ladders=None):
    analysis = analysis or {}
    priority = priority or DEFAULT_PRIORITY
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
        given = []
        for c, (steps, _plan) in (ladders or {}).items():
            dropped = [REQS[s["relaxed"]][0] for s in steps if s["relaxed"]]
            if dropped:
                given.append(f"{CASES[c][0]}では「{'」「'.join(dropped)}」")
        points.append(
            f"全要望を同時に満たせないケース: {'、'.join(conflicts)}。優先順位の低い要望から諦めると、"
            + "、".join(given) + " を緩めれば残りは守れる。"
        )
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
        broken = [REQS[m["req"]][0] for m in cheapest["met_in_priority"] if not m["met"]]
        points.append(
            f"最安は案{cheapest['key']}（加重平均 {cheapest['weighted_mean']:,.0f} k$）だが、"
            f"{'・'.join(broken[:2])}（優先順位が上）を基準・MRO 混雑の両方では守れないため、"
            f"{d:,.0f} k$ の上乗せで案{rec['key']}を選ぶ。"
        )
    act = analysis.get("actions")
    if act and len(act["bundle"]) > 1:
        first, last = act["bundle"][0], act["bundle"][-1]
        names = [act["catalogue"][a]["label"] for a in last["actions"]]
        w = act["weights"]
        wm = lambda step: sum(w[c] * step[c]["mean"] for c in w if step.get(c))  # noqa: E731
        points.insert(0,
            f"取れる手を効果の大きい順に重ねると「{'」→「'.join(names)}」。加重期待総コストは "
            f"{wm(first):,.0f} → {wm(last):,.0f} k$（{wm(last) - wm(first):+,.0f}）、MRO 混雑時の欠航確率は "
            f"{first['backlog']['aog_prob']:.1%} → {last['backlog']['aog_prob']:.1%}。"
        )
    be = analysis.get("breakeven")
    if be:
        many = [r["price"] for r in be if r["swaps"] >= len(p.visits) // 3]
        none = [r["price"] for r in be if r["swaps"] == 0]
        if many and none:
            points.append(
                f"判断を最も大きく分けるのは中寿命エンジンの正味価格。{max(many):,} k$ 以下なら入場の 3 分の 1 以上を"
                f"中古エンジンとの入れ替えに置き換えるのが得、{min(none):,} k$ 以上なら工場整備のみ。"
            )
    cp = analysis.get("coupling")
    if cp:
        def aog(owned, sub):
            xs = [c["aog"] for c in cp if c["owned"] == owned and c["substitute"] == sub and c["aog"] is not None]
            return max(xs) if xs else None
        lo = min(c["owned"] for c in cp)
        a0, a1 = aog(lo, 0), aog(lo, 1)
        if a0 is not None and a1 is not None:
            points.append(
                f"機材割当（別の最適化問題）との接点で効くのは「他機種が月に何機肩代わりできるか」。予備が薄い場合（{lo} 基）、"
                f"代替なしの欠航確率 最大 {a0:.0%} が代替ありで {a1:.0%} に下がる。1機の価値の設定はほぼ計画を変えない。"
            )
    decisions = []
    if now:
        decisions.append(f"今月中に入場先・ワークスコープを確定: {'、'.join(now)}")
    if soon:
        decisions.append(f"3 か月以内に確定: {'、'.join(soon)}")
    kits = rec["cases"]["base"]["emergency_kits"]
    if act and len(act["bundle"]) > 1:
        decisions.append("打ち手の実行を決める: " + "、".join(act["catalogue"][a]["label"] for a in act["bundle"][-1]["actions"]))
    if be:
        decisions.append("中寿命エンジン（CFM56-7B）の市場見積もりを取得：正味価格が判断の分岐点")
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
