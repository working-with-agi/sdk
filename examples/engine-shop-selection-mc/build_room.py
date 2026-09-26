#!/usr/bin/env python3
"""Build the decision room: the decisions due, each with approve / hold / return shared
through the artifact database, and an AI side panel that answers questions from the
analysis results (report, actions, explore) through page tools.

  python build_room.py --report report.json --actions actions.json --explore explore.json \\
                       --html-out room.html

The page is published as an Artifact with capabilities {db, user (profile), sample}.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def decisions(report: dict, actions: dict | None) -> list[dict]:
    items = []
    plan = {r["esn"]: r for r in report["plan"]}
    exc = {e["esn"]: e for e in report["exceptions"]}
    for e in sorted(report["urgency"]["engines"], key=lambda e: e["deadline"]):
        if e["status"] == "can_wait":
            continue
        p = plan.get(e["esn"], {})
        items.append({
            "id": "eng-" + e["esn"],
            "kind": "engine",
            "status_hint": e["status"],
            "title": f"{e['esn']} を {e['planned_label']} に {e['planned_choice'].replace('@', ' で ')}",
            "deadline": e["deadline_label"],
            "why": f"{e['binding_lead']['reason']} {e['binding_lead']['months']} か月前が期限。取卸し期限 {e['window_labels'][1]}"
                   + ("・要監視エンジン" if p.get("watch") else "")
                   + (f"・期限前に {exc[e['esn']]['months_early']} か月前倒し" if e["esn"] in exc else ""),
        })
    if actions and len(actions["bundle"]) > 1:
        for a in actions["bundle"][-1]["actions"]:
            row = next(r for r in actions["singles"] if r["key"] == a)
            b = row["cases"]["base"]
            items.append({
                "id": "act-" + a,
                "kind": "action",
                "status_hint": "soon",
                "title": row["label"],
                "deadline": "",
                "why": f"基準ケースで {b['delta']:+,.0f} k$、欠航確率 {100 * b['aog_prob']:.1f}%"
                       + (f"（部品取り {b['partouts']} 基）" if b.get("partouts") else ""),
            })
    items.append({"id": "info-midlife-quote", "kind": "info", "status_hint": "now",
                  "title": "中寿命エンジン（CFM56-7B）の市場見積もりを取得", "deadline": "",
                  "why": "正味価格 約 6,250 k$ を境に最適な打ち手が入れ替わる"})
    return items


def compact(report, actions, explore) -> dict:
    alts = [{
        "key": a["key"], "label": a["label"], "feasible": a["feasible"],
        "weighted_mean": round(a.get("weighted_mean", 0)),
        "cases": {c: {"mean": round(v["mean"]), "aog": round(v["aog_prob"], 4)} for c, v in a.get("cases", {}).items()},
        "requirements_met": [{"req": m["req"], "met": m["met"]} for m in a.get("met_in_priority", [])],
    } for a in report["alternatives"]]
    engines = {}
    plan = {r["esn"]: r for r in report["plan"]}
    exc = {e["esn"]: e for e in report["exceptions"]}
    for e in report["urgency"]["engines"]:
        p = plan.get(e["esn"], {})
        engines[e["esn"]] = {
            "plan": e["planned_choice"], "month": e["planned_label"], "window": e["window_labels"],
            "deadline": e["deadline_label"], "status": e["status"], "lead": e["binding_lead"],
            "hurry_cost": round(e["hurry_cost"]), "wait_cost": round(e["wait_cost"]),
            "watch": p.get("watch", False), "expected_off_wing_months": round(p.get("exp_off_wing", 0), 1),
            "curve": [{"month": c["label"], "cost": None if c["mean"] is None else round(c["mean"]),
                       "blocked_by": c["blocked_by"]} for c in e["curve"]],
            "early_removal": exc.get(e["esn"]),
        }
    act = None
    if actions:
        act = [{"key": r["key"], "category": r["category"], "label": r["label"],
                "cases": {c: None if v is None else {"delta": round(v["delta"]), "aog": round(v["aog_prob"], 4),
                                                     "partouts": v.get("partouts", 0), "swaps": v.get("swaps", 0)}
                          for c, v in r["cases"].items()}} for r in actions["singles"]]
    exp = None
    if explore:
        exp = {"labels": explore["labels"], "factors": explore["factors"], "rules": explore["rules"],
               "runs": [{"f": r["f"], "pattern": r["pattern"], "mean": round(r.get("mean", 0)),
                         "aog": round(r.get("aog_prob", 0), 4), "swaps": r.get("swaps"), "kits": r.get("kits"),
                         "spares": r.get("spares")} for r in explore["runs"]]}
    return {
        "meta": {k: report["meta"][k] for k in ("fleet", "owned_engines", "visits", "start", "horizon", "service_target", "budgets")},
        "conclusion": report["conclusion"],
        "priority": [report["requirements"][r]["label"] for r in report["priority"]],
        "cases": report["cases"], "alternatives": alts, "recommended": report["recommended"],
        "engines": engines, "actions": act, "explore": exp,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", type=Path, default=Path("report.json"))
    ap.add_argument("--actions", type=Path, default=Path("actions.json"))
    ap.add_argument("--explore", type=Path, default=Path("explore.json"))
    ap.add_argument("--html-out", type=Path, default=Path("room.html"))
    args = ap.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    actions = json.loads(args.actions.read_text(encoding="utf-8")) if args.actions.exists() else None
    explore = json.loads(args.explore.read_text(encoding="utf-8")) if args.explore.exists() else None
    data = {"decisions": decisions(report, actions), "analysis": compact(report, actions, explore)}
    html = (HERE / "room_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    args.html_out.write_text(html, encoding="utf-8")
    print(f"{len(data['decisions'])} decisions, {len(json.dumps(data)) // 1024} KiB of data -> {args.html_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
