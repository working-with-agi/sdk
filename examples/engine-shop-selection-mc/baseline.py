#!/usr/bin/env python3
"""Use case 1 -- the annual baseline (the figures everyone implicitly agrees on) -- and the
other use cases answered as deltas against it.

  freeze   solve the plan of record for the 2-year window with every company requirement,
           and one candidate plan per assumed world (congestion, LLP crunch, stress),
           add the normal-state norms from the 20-year life-cycle simulation, and save it
           as a versioned baseline (inputs are fingerprinted so a later run can tell
           whether it still compares like with like)
  compare  answer the questions of use cases 2-5 in parallel and report each one as
           "what changes against the baseline": cost, AOG probability, visits and spend by
           fiscal year, spares, part-outs, mid-life swaps, early removals, shop mix

  python baseline.py freeze  --company jal --out baselines/jal-2026-10.json
  python baseline.py freeze  --out baselines/2026-10.json          # the old group-wide sample
  python baseline.py compare --baseline baselines/2026-10.json --md-out deltas.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pulp

from shop_mc import Requirements, sample, solve_saa
from shop_mc.model import InfeasibleError
from shop_mc.summary import diff, summarize
from shop_mc.urgency import lead_times

import actions
import company
import lifecycle

HERE = Path(__file__).resolve().parent
DEFAULT_FLEET = HERE / "data" / "fleet_visits_lifecycle.json"
DEFAULT_SHOPS = HERE / "data" / "shop_quotes.json"

# Candidate plans frozen with the baseline: the best plan for each assumed world. As the
# months pass, track.py reads the actuals and tells which world we seem to be in, which
# plan we are actually following, and whether switching now would pay.
CANDIDATES = {
    "base": ("基準計画", "入力どおりの前提で立てた計画（これが基準）"),
    "backlog": ("混雑対応計画", "外部工場の TAT が 1 か月延びる前提で立てた計画"),
    "crunch": ("逼迫対応計画", "LLP キットの納期 12 か月・手持ち半減の前提で立てた計画"),
    "stress": ("複合ストレス対応計画", "混雑＋逼迫＋故障率 1.5 倍の前提で立てた計画"),
}

# The questions each use case asks, as (use case, question, actions applied, case).
QUESTIONS = [
    ("② 月次の入場判断", "外部工場の TAT が 1 か月延びたら（再計画）", (), "backlog"),
    ("③ 工場・契約", "アジア独立系を固定価格にしたら", ("fixed",), "base"),
    ("③ 工場・契約", "工場の枠を 2 つ事前確保したら", ("slots",), "base"),
    ("③ 工場・契約", "エンジン・プール契約を結んだら", ("pool",), "base"),
    ("④ 資産戦略", "グリーンタイム・エンジンを最大 8 基使えたら", ("midlife",), "base"),
    ("④ 資産戦略", "予備エンジンを 2 基増やしたら", ("spares",), "base"),
    ("④ 資産戦略", "整備せず部品取りで打ち切れるなら", ("partout",), "base"),
    ("④ 資産戦略", "737-8 の受領が進む中で部品取りを使うなら", ("partout",), "transition"),
    ("⑤ リスク対応", "LLP キットが逼迫したら", (), "crunch"),
    ("⑤ リスク対応", "LLP 逼迫にキット先行発注で備えたら", ("kits_ahead",), "crunch"),
    ("⑤ リスク対応", "複合ストレス（混雑＋逼迫＋故障増）", (), "stress"),
]


def fingerprint(*paths: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in paths}


def solve_summary(args):
    acts, case, fleet, shops, n, seed, n_eval, time_limit = args[:8]
    relax = args[8] if len(args) > 8 else ()
    try:
        p = actions.build(fleet, shops, acts, case)
    except actions.NotApplicable:
        return acts, case, None, None
    plan, relaxed = None, []
    # every requirement first; then give up the ones in `relax`, in order, until a plan exists
    for k in range(len(relax) + 1):
        try:
            req = {**actions.REQ, **{r: False for r in relax[:k]}}
            plan = solve_saa(p, sample(p, n, seed), req=Requirements(**req), time_limit=time_limit, threads=1)
            relaxed = list(relax[:k])
            break
        except InfeasibleError:
            continue
    if plan is None:
        return acts, case, None, None
    sc = sample(p, n_eval, seed + 999)
    rows = []
    leads = lead_times(p, [sc.options[i] for i in plan.chosen])
    for i in sorted(plan.chosen, key=lambda i: sc.options[i].month):
        o = sc.options[i]
        reason, lead = max(leads[o.visit.esn], key=lambda r: r[1])
        rows.append({
            "esn": o.visit.esn, "shop": o.shop.id, "workscope": o.workscope, "month": p.month_label(o.month),
            "t": o.month, "fy": p.fiscal_year(o.month), "rush": o.rush, "watch": o.visit.watch,
            "limit": p.month_label(o.visit.latest), "earliest": p.month_label(o.visit.earliest),
            "exp_cost": round(float(sc.cost[:, i].mean())), "off_wing": round(float(sc.down[:, i].mean()), 1),
            "quoted_off_wing": o.shop.transport_months + o.tat(),
            # the decision must be made this many months before induction (slot booking,
            # or LLP kit order when the kits on hand are already committed)
            "deadline_t": o.month - lead, "deadline_reason": f"{reason} {lead} か月前",
        })
    summ = summarize(p, plan, sc)
    summ["relaxed"] = relaxed
    return acts, case, summ, rows


def freeze(args) -> int:
    t0 = time.perf_counter()
    # the budget is the one requirement the baseline may give up: in practice it is built
    # up from the removal forecast, and the gap to the normal-state spend is the finding
    jobs = [((), c, str(args.fleet), str(args.shops), args.scenarios, args.seed, args.eval_scenarios, args.time_limit, ("budget",))
            for c in CANDIDATES]
    with ProcessPoolExecutor(max_workers=min(len(jobs), os.cpu_count() or 1)) as pool:
        solved = {c: (summ, rows) for (_a, c, summ, rows) in pool.map(solve_summary, jobs)}
    summ, rows = solved["base"]
    if summ is None:
        print("no plan meets every requirement in the base case; relax one before freezing")
        return 1
    # norms from the same life-cycle simulation that produced the company's fleet
    lc_seed = company.configure_for_fleet(args.fleet) or args.seed
    visits, shelf, short, _state, T = lifecycle.simulate(lc_seed)
    p = actions.build(str(args.fleet), str(args.shops), (), "base")
    monthly = {
        "labels": [p.month_label(t) for t in range(p.horizon)],
        "fy": [p.fiscal_year(t) for t in range(p.horizon)],
        "peak": [p.is_peak(t) for t in range(p.horizon)],
        "required": p.required_positions, "buffer": p.buffer,
        # engines available on the plan's quoted schedule (no delays): the planning view
        "serviceable": [p.owned_engines - sum(1 for r in rows if r["t"] <= t < r["t"] + r["quoted_off_wing"])
                        for t in range(p.horizon)],
    }
    # the seasonal norm for each window month: what a normal year does in that calendar
    # month (removals and spend follow the flight index), next to what the plan does
    sea = lifecycle.norms(visits, shelf, short, T)["seasonal"]
    cal = [p.calendar(t)[1] for t in range(p.horizon)]
    monthly["flight_index"] = [sea[m]["flight_index"] for m in cal]
    monthly["aog_multiplier"] = [p.season(t) for t in range(p.horizon)]
    monthly["lease_cap"] = [p.lease_cap_at(t) for t in range(p.horizon)]
    monthly["norm_visits"] = [round(sea[m]["visits"], 2) for m in cal]
    monthly["norm_visits_range"] = [sea[m]["sim_visits_p10_p90"] for m in cal]
    monthly["norm_spend"] = [round(sea[m]["spend_k"]) for m in cal]
    monthly["plan_visits"] = [sum(1 for r in rows if r["t"] == t) for t in range(p.horizon)]
    monthly["plan_spend"] = [sum(r["exp_cost"] for r in rows if r["t"] == t) for t in range(p.horizon)]
    outlook = {}
    for name, aging in (("stationary", 0.0), ("aging_2pct", 0.02)):
        # same seed: the first YEARS reproduce the history that led to today; the 10 years
        # after that are the outlook (year 0 = the 12 months from the window start)
        v, sh, st, _s, TT = lifecycle.simulate(lc_seed, years=lifecycle.YEARS + 10, aging=aging)
        years = []
        for y in range(lifecycle.YEARS - 5, lifecycle.YEARS + 10):
            vs = [x for x in v if y * 12 <= x["t"] < (y + 1) * 12]
            years.append({"year": y - lifecycle.YEARS, "visits": len(vs),
                          "by_ws": {w: sum(1 for x in vs if x["ws"] == w) for w in lifecycle.COST},
                          "spend": sum(lifecycle.COST[x["ws"]] for x in vs)})
        outlook[name] = years
    meta = json.loads(args.fleet.read_text(encoding="utf-8")).get("meta", {})
    shops_meta = json.loads(args.shops.read_text(encoding="utf-8")).get("meta", {})
    base = {
        "version": dt.date.today().isoformat(),
        "company": {"id": meta.get("company"), "name": meta.get("name", "737-800 フリート"),
                    "contract": {k: shops_meta.get(k) for k in ("description", "contract_type", "renewal", "source")},
                    "sources": meta.get("sources", {})},
        "paths": {"fleet": os.path.relpath(args.fleet, HERE), "shops": os.path.relpath(args.shops, HERE)},
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": fingerprint(args.fleet, args.shops),
        "settings": {"scenarios": args.scenarios, "eval_scenarios": args.eval_scenarios, "seed": args.seed,
                     "requirements": actions.REQ, "solver": f"HiGHS via PuLP {pulp.__version__}"},
        "norms": lifecycle.norms(visits, shelf, short, T),
        "plan_of_record": summ,
        "plan": rows,
        "monthly": monthly,
        "budgets": p.budget_by_fy,
        "outlook": outlook,
        "candidates": {c: {"label": CANDIDATES[c][0], "world": c, "what": CANDIDATES[c][1],
                           "feasible": solved[c][0] is not None, "summary": solved[c][0], "rows": solved[c][1]}
                       for c in CANDIDATES},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
    n = base["norms"]
    print(f"baseline frozen in {time.perf_counter() - t0:.0f}s -> {args.out}")
    print(f"  norms: {n['visits_per_year']:.1f} visits/yr, {n['spend_per_year_k']:,.0f} k$/yr, {n['usd_per_efh']:.0f} $/EFH")
    if summ["relaxed"]:
        print(f"  relaxed: {summ['relaxed']} (no plan fits the normal-state budget)")
    print(f"  plan of record: cost {summ['total_cost']:,.0f} k$, AOG {summ['aog_prob']:.1%}, "
          + ", ".join(f"{fy} {v['visits']} visits / {v['spend']:,.0f} k$" for fy, v in summ["by_fiscal_year"].items()))
    return 0


def compare(args) -> int:
    base = json.loads(args.baseline.read_text(encoding="utf-8"))
    now = fingerprint(args.fleet, args.shops)
    stale = [k for k in now if base["inputs"].get(k) != now[k]]
    s = base["settings"]
    questions = []
    for q in QUESTIONS:  # skip what does not exist for this company (e.g. a shop it has no contract with)
        try:
            actions.build(str(args.fleet), str(args.shops), q[2], q[3])
            questions.append(q)
        except actions.NotApplicable:
            pass
    # give up the budget only if the baseline itself had to
    relax = tuple(ref_relaxed) if (ref_relaxed := base["plan_of_record"].get("relaxed")) else ()
    jobs = [(acts, case, str(args.fleet), str(args.shops), s["scenarios"], s["seed"], s["eval_scenarios"], args.time_limit, relax)
            for _uc, _q, acts, case in questions]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        res = list(pool.map(solve_summary, jobs))
    wall = time.perf_counter() - t0
    ref = base["plan_of_record"]
    out = []
    for (uc, q, acts, case), (_a, _c, summ, _rows) in zip(questions, res):
        out.append({"use_case": uc, "question": q, "actions": list(acts), "case": case,
                    "feasible": summ is not None, "summary": summ, "delta": None if summ is None else diff(ref, summ)})
    result = {"baseline": {"version": base["version"], "inputs": base["inputs"], "plan_of_record": ref},
              "inputs_changed": stale, "wall_seconds": round(wall, 1), "answers": out}
    args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    md = to_markdown(result)
    if args.md_out:
        args.md_out.write_text(md, encoding="utf-8")
    print(md)
    return 0


def to_markdown(r: dict) -> str:
    ref = r["baseline"]["plan_of_record"]
    fys = list(ref["by_fiscal_year"])
    lines = [
        f"# 基準（{r['baseline']['version']} 版）からの増減",
        "",
        f"基準：期待総コスト {ref['total_cost']:,.0f} k$、欠航確率 {ref['aog_prob']:.1%}、入場 {ref['shop_visits']} 件"
        + "（" + "、".join(f"{fy} {v['visits']} 件・{v['spend']:,.0f} k$" for fy, v in ref["by_fiscal_year"].items()) + "）",
        "",
    ]
    if r["inputs_changed"]:
        lines += [f"> 注意：基準を固定した後に入力が変わっています（{', '.join(r['inputs_changed'])}）。基準の固定し直しを検討してください。", ""]
    head = "| ユースケース | 問い | 総コスト | 欠航確率 | 入場件数 | " + " | ".join(f"{fy} 支出" for fy in fys) + " | 予備 | 部品取り | グリーンタイム | 前倒し(月) |"
    lines += [head, "|" + "---|" * (9 + len(fys))]
    for a in r["answers"]:
        if not a["feasible"]:
            lines.append(f"| {a['use_case']} | {a['question']} | 実行可能な計画なし |" + " |" * (7 + len(fys)))
            continue
        d = a["delta"]
        sg = lambda v, f="{:+,.0f}": f.format(v) if abs(v) > 1e-9 else "±0"  # noqa: E731
        lines.append(
            f"| {a['use_case']} | {a['question']} | {sg(d['total_cost'])} | {d['aog_prob'] * 100:+.1f}pt | {sg(d['shop_visits'])} | "
            + " | ".join(sg(d["by_fiscal_year"].get(fy, {}).get("spend", 0)) for fy in fys)
            + f" | {sg(d['long_spares'])} | {sg(d['partouts'])} | {sg(d['midlife_swaps'])} | {sg(d['early_months'])} |"
        )
    lines += ["", "金額は k$（期待値）。差は「その問いの条件で計画し直した結果 − 基準」。合成データ。"]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("freeze", "compare"):
        sp = sub.add_parser(name)
        sp.add_argument("--company", help="jal / ana: use data/<company>/ inputs (company.py builds them)")
        sp.add_argument("--fleet", type=Path)
        sp.add_argument("--shops", type=Path)
        sp.add_argument("--time-limit", type=int, default=120)
        if name == "freeze":
            sp.add_argument("--out", type=Path, default=HERE / "baselines" / "baseline.json")
            sp.add_argument("--scenarios", type=int, default=60)
            sp.add_argument("--eval-scenarios", type=int, default=2000)
            sp.add_argument("--seed", type=int, default=42)
        else:
            sp.add_argument("--baseline", type=Path, default=HERE / "baselines" / "baseline.json")
            sp.add_argument("--workers", type=int, default=os.cpu_count())
            sp.add_argument("--json-out", type=Path, default=Path("deltas.json"))
            sp.add_argument("--md-out", type=Path)
    args = ap.parse_args(argv)
    if args.company:
        args.fleet = args.fleet or HERE / "data" / args.company / "fleet.json"
        args.shops = args.shops or HERE / "data" / args.company / "shops.json"
    if args.cmd == "compare" and (args.fleet is None or args.shops is None):
        paths = json.loads(args.baseline.read_text(encoding="utf-8")).get("paths", {})
        args.fleet = args.fleet or (HERE / paths["fleet"] if "fleet" in paths else DEFAULT_FLEET)
        args.shops = args.shops or (HERE / paths["shops"] if "shops" in paths else DEFAULT_SHOPS)
    args.fleet, args.shops = args.fleet or DEFAULT_FLEET, args.shops or DEFAULT_SHOPS
    return freeze(args) if args.cmd == "freeze" else compare(args)


if __name__ == "__main__":
    sys.exit(main())
