#!/usr/bin/env python3
"""Build the monthly report: what the engine meeting needs at the end of each month.

For every month of the actuals it answers, in the order the readers ask:
  1. the conclusion in three lines (on plan? has the world moved? what to decide)
  2. what changed since last month
  3. actuals against the plan (this month and so far)
  4. decisions due this month and in the next two
  5. exceptions (new ones first)
  6. spare engines and margin for the next three months
  7. fiscal-year landing against budget, and its change since last month
  8. unscheduled removals against what was assumed

  python build_monthly.py --html-out monthly.html
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import track
import usecases

HERE = Path(__file__).resolve().parent
MATERIAL = 300


def month_reports(b: dict, t: dict, act: dict, u: dict) -> list[dict]:
    C, W = t["candidates"], t["worlds"]
    M = b["monthly"]
    labels = t["months"]
    lease = 0.13
    out = []
    for i, T in enumerate(t["timeline"]):
        k = T["k"]                       # months elapsed; the report is for month k-1
        prev = t["timeline"][i - 1] if i else None
        rows = C[T["executed"]]["rows"]
        now = k - 1
        ind_m = [x for x in act["inductions"] if x["t"] == now]
        ret_m = [x for x in act["returns"] if x["t"] == now]
        plan_m = [r for r in rows if r["t"] == now]
        cum_plan = [sum(1 for r in rows if r["t"] <= m) for m in range(len(labels))]
        cum_act = [sum(1 for x in act["inductions"] if x["t"] <= m) for m in range(k)]
        # world
        top = max(T["posterior"], key=T["posterior"].get)
        ptop = prev and max(prev["posterior"], key=prev["posterior"].get)
        # exceptions: new ones are those not in last month's list
        key = lambda e: (e["esn"], e["kind"])  # noqa: E731
        old = {key(e) for e in prev["exceptions"]} if prev else set()
        exc = [e | {"new": key(e) not in old} for e in T["exceptions"]]
        exc.sort(key=lambda e: (not e["new"], e["severity"] != "crit"))
        # decisions: plan inductions whose deadline falls this month or in the next two
        inducted = {x["esn"] for x in act["inductions"] if x["t"] < k}
        dec = [{"esn": r["esn"], "month": r["month"], "workscope": r["workscope"], "due": labels[r["deadline_t"]] if r["deadline_t"] < len(labels) else r["month"],
                "reason": r["deadline_reason"], "watch": r["watch"], "this_month": r["deadline_t"] == k}
               for r in rows if k <= r["deadline_t"] <= k + 2 and r["esn"] not in inducted]
        sw = max(T["switch"].items(), key=lambda x: x[1]["saving"]) if T["switch"] else None
        switch = None
        if sw and sw[1]["saving"] > MATERIAL:
            switch = {"to": C[sw[0]]["label"], "saving": sw[1]["saving"], "aog": sw[1]["aog_delta"],
                      "changes": len(sw[1]["changes"]), "decide_by": sw[1]["decide_by"]}
        # margin for the next three months: the baseline margin, less engines late back from the shop
        late = sum(1 for e in T["exceptions"] if e["kind"] == "戻り遅れ")
        margin = []
        for m in range(k, min(k + 3, len(labels))):
            base = M["serviceable"][m] - M["required"][m] - M["buffer"][m]
            margin.append({"month": labels[m], "base": base, "now": base - late, "peak": M["peak"][m]})
        # landing
        land = [{"fy": fy, **v} for fy, v in sorted(T["forecast"].items())]
        land_prev = {fy: v["total"] for fy, v in (prev["forecast"].items() if prev else [])}
        for r in land:
            r["change"] = r["total"] - land_prev.get(r["fy"], r["total"])
        # unscheduled: forced inductions this month and so far, against the assumed rate
        forced_m = sum(1 for x in ind_m if x["reason"] == "failure")
        forced_ytd = sum(1 for x in act["inductions"] if x["t"] < k and x["reason"] == "failure")
        exp_ytd = T["expected"].get(top, {}).get("forced", 0.0)
        # approvals for the meeting
        approvals = []
        if switch:
            approvals.append(f"計画の乗り換え：{switch['to']}（期待 {switch['saving'] / 1000:+.1f} 百万ドル、変わるのは {switch['changes']} 基、判断期限 {switch['decide_by'] or '—'}）")
        n_this = sum(1 for d in dec if d["this_month"])
        if n_this:
            approvals.append(f"今月が判断期限の入場 {n_this} 件（枠の予約・部品の発注）")
        crit = [e for e in exc if e["severity"] == "crit"]
        if crit:
            approvals.append(f"要対応の外れ {len(crit)} 件（戻り遅れなど）：短期リースで埋めるかの判断")
        # only fiscal years still open this month can be acted on
        y, mth = map(int, T["as_of"].split("-"))
        fy_now = f"FY{y if mth >= 4 else y - 1}"
        for r in land:
            r["closed"] = r["fy"] < fy_now
        over = [r for r in land if not r["closed"] and r["budget"] and r["total"] > r["budget"] * 1.05]
        for r in over:
            approvals.append(f"{r['fy']} の着地が予算を {r['total'] / r['budget'] - 1:.0%} 超える見込み：予算の見直しか入場の組み替え")
        if not approvals:
            approvals.append("今月、会議で決めることはありません")
        # the three lines
        on_plan = T["follow"][T["executed"]]
        l1 = (f"{C[T['executed']]['label']}どおりに進行（入場の一致 {on_plan:.0%}）。今月は入場 {len(ind_m)} 件（予定 {len(plan_m)}）・戻り {len(ret_m)} 件"
              + (f"、新しい外れ {sum(1 for e in exc if e['new'])} 件" if any(e["new"] for e in exc) else ""))
        l2 = (f"前提は{W[top]['label']}に近い（{T['posterior'][top]:.0%}）" + ("" if not prev or ptop == top else f"。先月の見立て（{W[ptop]['label']}）から変わった"))
        l3 = approvals[0]
        out.append({
            "k": k, "month": T["as_of"], "lines": [l1, l2, l3],
            "changes": {
                "world_from": W[ptop]["label"] if prev else None, "world_to": W[top]["label"],
                "posterior": {W[w]["label"]: p for w, p in T["posterior"].items()},
                "posterior_prev": {W[w]["label"]: p for w, p in prev["posterior"].items()} if prev else None,
                "new_exceptions": sum(1 for e in exc if e["new"]),
                "landing_change": sum(r["change"] for r in land),
            },
            "actuals": {"inductions": ind_m, "returns": ret_m, "planned": [r["esn"] for r in plan_m],
                        "cum_plan": cum_plan, "cum_act": cum_act, "planned_by_now": T["planned_by_now"], "inducted": T["inducted"]},
            "decisions": dec, "switch": switch, "exceptions": exc, "margin": margin, "late": late,
            "landing": land, "unsched": {"month": forced_m, "ytd": forced_ytd, "expected_ytd": exp_ytd},
            "approvals": approvals,
        })
    return out


def company(cid: str, actuals: str) -> dict:
    bpath = HERE / "baselines" / f"{cid}-2026-10.json"
    b = json.loads(bpath.read_text(encoding="utf-8"))
    apath = HERE / "data" / cid / f"actuals_{actuals}.json"
    act = json.loads(apath.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "t.json"
        track.main(["status", "--baseline", str(bpath), "--actuals", str(apath), "--json-out", str(out)])
        t = json.loads(out.read_text(encoding="utf-8"))
    u = usecases.build(b)
    sp = u["spares"]
    return {"id": cid, "name": b["company"]["name"], "labels": t["months"], "demo": act["meta"].get("synthetic", False),
            "spares": {"have": sp["have"], "best_now": sp["cost"]["今の工期"]["best"], "p_now": sp["curves"]["今の工期"][sp["have"]]},
            "reports": month_reports(b, t, act, u)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", nargs="+", default=["jal", "ana"])
    ap.add_argument("--actuals", default="backlog")
    ap.add_argument("--html-out", type=Path, default=Path("monthly.html"))
    args = ap.parse_args(argv)
    data = [company(c, args.actuals) for c in args.companies]
    html = (HERE / "monthly_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=float))
    args.html_out.write_text(html, encoding="utf-8")
    print(f"{len(data)} companies, {len(data[0]['reports'])} months -> {args.html_out} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
