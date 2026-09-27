#!/usr/bin/env python3
"""Build the layered report: one page that starts from the conclusions and drills down.

  level 1  executive summary per company: three lines (money, service, what to decide)
  level 2  one card per use case: annual plan and budget, this month's decisions, plan
           tracking, actions and their effect, new domestic shop, assumptions
  level 3  the detail behind each card: fiscal years, months, engines, actions
  level 4  assumptions and sources, including every value without a source

Inputs per company: the frozen baseline, the deltas of baseline.py compare (run here if
missing), the tracking status of one set of actuals, and optionally invest.py's result.

  python build_report.py --html-out report.html
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import baseline
import track
import usecases

HERE = Path(__file__).resolve().parent
MATERIAL = 300  # k$: below this a switch or an action is not worth the disruption


def fy_rows(b: dict) -> list[dict]:
    M = b["monthly"]
    out = []
    for fy, budget in b["budgets"].items():
        ts = [t for t, f in enumerate(M["fy"]) if f == fy]
        plan = b["plan_of_record"]["by_fiscal_year"].get(fy, {"visits": 0, "spend": 0.0})
        norm = sum(M["norm_spend"][t] for t in ts)
        out.append({"fy": fy, "months": len(ts), "first": M["labels"][ts[0]], "last": M["labels"][ts[-1]],
                    "visits": plan["visits"], "spend": plan["spend"], "budget": budget, "norm": norm,
                    "norm_visits": sum(M["norm_visits"][t] for t in ts),
                    "over": plan["spend"] / budget - 1 if budget else 0.0,
                    "ws": {w: plan.get(w, 0) for w in ("PR", "CORE", "FULL")}})
    return out


def months(b: dict) -> list[dict]:
    M, P = b["monthly"], b["plan"]
    out = []
    for t, label in enumerate(M["labels"]):
        out.append({"t": t, "label": label, "fy": M["fy"][t], "peak": M["peak"][t],
                    "margin": M["serviceable"][t] - M["required"][t] - M["buffer"][t],
                    "load": M.get("shop_load", [0] * len(M["labels"]))[t], "slots": M.get("shop_slots", 0),
                    "inductions": M["plan_visits"][t], "spend": M["plan_spend"][t],
                    "norm_visits": M["norm_visits"][t],
                    "due": sum(1 for r in P if r["deadline_t"] == t)})
    return out


def actions_of(deltas: dict) -> list[dict]:
    out = []
    for a in deltas["answers"]:
        if not a["feasible"]:
            continue
        d = a["delta"]
        out.append({"use_case": a["use_case"], "question": a["question"], "cost": d["total_cost"],
                    "aog": d["aog_prob"], "visits": d["shop_visits"],
                    "premium": d.get("premium"), "payout": d.get("payout"), "recourse_p90": d.get("recourse_p90"),
                    "fy": {fy: v["spend"] for fy, v in d["by_fiscal_year"].items()}})
    return out


def resilience_of(b: dict, deltas: dict) -> dict | None:
    """How cheap recovery is: for every candidate plan the committed cost against the
    recourse (lease, substitution, AOG, emergency kits); for every action the premium it
    costs up front against the payout it returns afterwards."""
    C = b["candidates"]
    if not any((v.get("summary") or {}).get("recourse") is not None for v in C.values()):
        return None
    plans = [{"key": k, "label": v["label"], "committed": v["summary"]["committed"], "recourse": v["summary"]["recourse"],
              "recourse_p90": v["summary"]["recourse_p90"], "parts": v["summary"].get("recourse_parts") or {},
              "total": v["summary"]["total_cost"], "aog": v["summary"]["aog_prob"]}
             for k, v in C.items() if v.get("feasible") and v.get("summary")]
    acts = [{"question": a["question"], "use_case": a["use_case"], "premium": a["delta"]["premium"], "payout": a["delta"]["payout"],
             "net": -a["delta"]["total_cost"], "aog": a["delta"]["aog_prob"], "recourse_p90": a["delta"]["recourse_p90"]}
            for a in deltas["answers"] if a["feasible"] and a["delta"] and a["delta"].get("premium") is not None]
    base = next((p for p in plans if p["key"] == "base"), None)
    return {"plans": plans, "actions": acts, "base": base}


def track_summary(t: dict) -> dict:
    T = t["timeline"][-1]
    C, W = t["candidates"], t["worlds"]
    top = max(T["posterior"], key=T["posterior"].get)
    sw = sorted(T["switch"].items(), key=lambda x: -x[1]["saving"])
    best = sw[0] if sw else None
    rec = ("switch", best[0]) if best and best[1]["saving"] > MATERIAL and T.get("hysteresis_ok", True) else ("keep", None)
    return {"as_of": T["as_of"], "executed": C[T["executed"]]["label"], "follow": T["follow"][T["executed"]],
            "world": W[top]["label"], "world_p": T["posterior"][top], "world_is_base": top == "base",
            "exceptions": len(T["exceptions"]), "planned": T["planned_by_now"], "inducted": T["inducted"],
            "recommend": rec[0], "switch_to": C[rec[1]]["label"] if rec[1] else None,
            "switch_saving": best[1]["saving"] if best else 0, "switch_decide_by": best[1]["decide_by"] if best else None,
            "posterior": {W[w]["label"]: p for w, p in T["posterior"].items()},
            "switch": [{"to": C[c]["label"], "saving": s["saving"], "aog": s["aog_delta"], "changes": len(s["changes"]),
                        "decide_by": s["decide_by"], "overdue": s["overdue"]} for c, s in sw],
            "demo": t["actuals"]["meta"].get("synthetic", False),
            # month by month, for the charts
            "series": [{"as_of": x["as_of"], "posterior": {W[w]["label"]: p for w, p in x["posterior"].items()},
                        "best_saving": max((v["saving"] for v in x["switch"].values()), default=0)} for x in t["timeline"]],
            "world_labels": [W[w]["label"] for w in W],
            "cpd": cpd_summary(t.get("cpd"), t), "ooda": t.get("ooda"), "hysteresis_ok": T.get("hysteresis_ok")}


def cpd_summary(c: dict | None, t: dict) -> dict | None:
    if not c:
        return None
    w = c["weeks_per_month"]
    months = t["months"]
    v = c.get("value") or {}
    return {"state": c["state"], "verdict": c["verdict"], "cpd_as_of": c["cpd_as_of"], "bayes_as_of": c["bayes_as_of"],
            "cpd_month": c["cpd_month"], "bayes_month": c["bayes_month"], "fired_world": c["fired_world"],
            "months_earlier": v.get("months_earlier"), "bayes_never_moved": v.get("bayes_never_moved"),
            "worth": v.get("worth"), "at_cpd": v.get("at_cpd"), "at_bayes": v.get("at_bayes"), "delay_curve": v.get("delay_curve"),
            "first_profitable": None if not v.get("first_profitable_month") else months[v["first_profitable_month"] - 1],
            "truth_week": c.get("change_week_truth"), "weeks_per_month": w,
            "streams": [{"key": n, "label": s["label"], "what": s["what"], "world": s["world"], "ys": c["series"][n],
                         "week": s["week"], "bocpd_week": s["bocpd_week"], "cusum_week": s["cusum_week"],
                         "before": s["level_before"], "after": s["level_after"]} for n, s in c["streams"].items()],
            "agreement": [a["state"] for a in c["agreement"]], "as_of": [a["as_of"] for a in c["agreement"]],
            "uer_arl": c["uer_arl"], "note": c["note"]}


def unsourced(company_id: str) -> list[dict]:
    """Every value in data/companies.json marked no_source, for this company and common."""
    conf = json.loads((HERE / "data" / "companies.json").read_text(encoding="utf-8"))
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and "no_source" in v:
                    out.append({"where": ".".join(path), "what": v.replace("no_source: ", "").replace("no_source", "出典なし")})
                else:
                    walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [str(i)])

    walk(conf["companies"].get(company_id, {}), [company_id])
    walk(conf["common"], ["common"])
    return out


def verdict(c: dict) -> list[dict]:
    fys = c["fiscal_years"]
    worst = max(fys, key=lambda r: r["over"])
    full = [r for r in fys if r["months"] == 12] or fys
    main = full[0]
    money = {"q": "お金", "a": f"{main['fy']} の整備費は {main['spend'] / 1000:.1f} 百万ドル（予算 {main['budget'] / 1000:.1f}、{main['over']:+.0%}）",
             "why": (f"{worst['fy']}（{worst['first']}〜{worst['last']}）は予算を {worst['over']:.0%} 超える見込み。"
                     f"平年並みの予算では、この期間に期限が来るエンジンを回しきれない" if worst["over"] > 0.05 else "どの年度も予算内に収まる見込み")}
    m = c["months"]
    thin = min(m, key=lambda r: r["margin"])
    load = max(m, key=lambda r: r["load"])
    service = {"q": "運航", "a": f"エンジンが足りなくなる確率 {c['aog_prob']:.1%}（2 年で 1 か月でも）",
               "why": f"余力が最も薄いのは {thin['label']}（{thin['margin']:+d} 基）。工場の混み具合は最大 {load['load']}/{load['slots']}（{load['label']}）"}
    acts = c["actions"]
    save = [a for a in acts if a["aog"] <= 0.005 and "部品取り" not in a["question"]]
    best = min(save, key=lambda a: a["cost"]) if save else None
    safer = min([a for a in acts if a["cost"] <= 5000], key=lambda a: a["aog"], default=None)
    # decisions whose deadline fell before the plan starts are assumed already arranged
    # (slots booked, kits ordered): the plan inherits them
    due = sum(1 for r in c["plan"] if r["deadline_t"] == 0)
    pre = sum(1 for r in c["plan"] if r["deadline_t"] < 0)
    parts = [f"今月の判断期限 {due} 件" + (f"（ほかに計画開始前に手配が必要だった {pre} 件は手配済みを前提）" if pre else "")]
    if best and best["cost"] < -MATERIAL:
        parts.append(f"費用を最も下げる打ち手は「{best['question']}」（{best['cost'] / 1000:+.1f} 百万ドル）")
    if safer and safer["aog"] < -0.002:
        parts.append(f"欠航リスクを最も下げるのは「{safer['question']}」（{safer['aog'] * 100:+.1f}pt、{safer['cost'] / 1000:+.1f} 百万ドル）")
    tr = c.get("track")
    if tr:
        parts.append(f"実績（{'デモ' if tr['demo'] else ''}{tr['as_of']} まで）では" +
                     (f"前提は{tr['world']}に近く（{tr['world_p']:.0%}）、" if not tr["world_is_base"] else "前提どおり、") +
                     (f"{tr['switch_to']}への乗り換えを推奨（{tr['switch_saving'] / 1000:+.1f} 百万ドル）" if tr["recommend"] == "switch" else "今の計画を続けてよい"))
    decide = {"q": "決めること", "a": parts[0], "why": "。".join(parts[1:])}
    return [money, service, decide]


def horizons(c: dict, b: dict) -> dict:
    """Meta view: which time horizons the planning covers, and whether each long horizon is
    carried down into the next shorter one (with a measure of how consistent they are)."""
    plan_n = len(c["plan"])
    out2 = sum(y["visits"] for y in b["outlook"]["stationary"] if y["year"] in (0, 1))
    spend2, budget2 = sum(r["spend"] for r in c["fiscal_years"]), sum(r["budget"] for r in c["fiscal_years"])
    h = c.get("history")
    layers = [
        {"id": "life", "label": "ライフサイクル（平年の姿）", "months": 240, "have": True},
        {"id": "invest", "label": "設備投資（国内工場）", "months": 228, "have": bool(c.get("invest"))},
        {"id": "outlook", "label": "10 年の見通し（入場の波）", "months": 120, "have": True},
        {"id": "plan", "label": "2 年の基準計画と計画案", "months": 24, "have": True},
        {"id": "budget", "label": "年度予算", "months": 12, "have": True},
        {"id": "deadline", "label": "判断期限（3 か月先まで）", "months": 3, "have": True},
        {"id": "track", "label": "月次の追跡", "months": 1, "have": bool(c.get("track"))},
    ]
    links = []

    def link(a, b_, status, what, measure=None):
        links.append({"from": a, "to": b_, "status": status, "what": what, "measure": measure})

    link("life", "budget", "ok", "平年値を季節で按分して年度予算に", f"計画は予算の {spend2 / budget2 - 1:+.0%}")
    gap = plan_n / out2 - 1 if out2 else 0
    link("outlook", "plan", "ok" if abs(gap) < 0.15 else "warn", "見通しの最初の 2 年と基準計画の件数",
         f"計画 {plan_n} 件 / 見通し {out2} 件（{gap:+.0%}）")
    tr = c.get("transition_in_plan", False)
    link("outlook", "plan", "warn", "737-8 の受領（機材更新）", "計画案の一つ（部品取りと組み合わせ）にしかなく、基準計画は受領を織り込まない")
    if c.get("invest"):
        link("invest", "deadline", "bad", "国内工場の判断ゲート（段階 1 は FY2027 開始、段階 2 は FY2028 に判断）",
             "今月からの判断期限に載っていない（長期の判断が短期の行動に落ちていない）")
    dl = sum(1 for r in c["plan"] if r["deadline_t"] >= 0)
    link("plan", "deadline", "ok", "計画の入場ごとの判断期限", f"{plan_n} 件すべて（期限前の {plan_n - dl} 件は手配済みを前提）")
    if c.get("roll"):
        r = c["roll"]
        link("track", "plan", "ok", "追跡の結果を次の版に返す",
             f"{r['to_version']} 版：工期・所見・故障率・前提の確率を実績で更新（重み {min(e['weight'] for e in r['learned'].values() if 'weight' in e):.0%}〜）、手配済み {len(r['carried']['fixed'])} 基を固定")
    elif c.get("track"):
        link("track", "plan", "bad", "追跡の結果を次の版に返す", "未実装（乗り換えの判断は出るが、次の計画の前提は直さない）")
    if h:
        fys = [f for v in h["versions"] for f in v["fiscal_years"] if f["months"] >= 6]
        inside = sum(f["inside"] for f in fys)
        link("plan", "plan", "ok" if inside / max(1, len(fys)) >= 0.8 else "warn", "当時のリスクの幅に実績が入ったか",
             f"{inside}/{len(fys)} 年度")
        st = h["stability"]
        kept = sum(x["same"] for x in st) / max(1, sum(x["same"] + x["moved"] + x["moved_far"] + x["dropped"] for x in st))
        link("plan", "plan", "ok" if kept >= 0.6 else "warn", "前の版の 2 年目が今の版の 1 年目にそのまま残ったか", f"{kept:.0%}")
    ok = sum(1 for x in links if x["status"] == "ok")
    return {"layers": layers, "links": links, "score": ok / len(links)}


def company(baseline_path: Path, deltas_path: Path | None, actuals_path: Path | None, invest_path: Path | None,
            history_path: Path | None = None, roll_path: Path | None = None) -> dict:
    b = json.loads(baseline_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        if deltas_path is None or not deltas_path.exists():
            out = Path(tmp) / "deltas.json"
            baseline.main(["compare", "--baseline", str(baseline_path), "--json-out", str(out)])
            deltas_path = out
        deltas = json.loads(deltas_path.read_text(encoding="utf-8"))
        tr = None
        if actuals_path and actuals_path.exists():
            out = Path(tmp) / "track.json"
            track.main(["status", "--baseline", str(baseline_path), "--actuals", str(actuals_path), "--json-out", str(out)])
            tr = track_summary(json.loads(out.read_text(encoding="utf-8")))
    shops = json.loads((HERE / b["paths"]["shops"]).read_text(encoding="utf-8"))
    names = {k["id"]: k["name"] for k in shops["shops"]}
    c = {
        "id": b["company"]["id"], "name": b["company"]["name"], "version": b["version"],
        "contract": b["company"]["contract"], "sources": b["company"]["sources"],
        "norms": {k: b["norms"][k] for k in ("visits_per_year", "spend_per_year_k", "usd_per_efh", "visits_per_year_by_workscope")}
                 | {"by_subfleet": b["norms"].get("by_subfleet", {})},
        "aog_prob": b["plan_of_record"]["aog_prob"], "total_cost": b["plan_of_record"]["total_cost"],
        "relaxed": b["plan_of_record"].get("relaxed", []),
        "fiscal_years": fy_rows(b), "months": months(b),
        "plan": [{k: r[k] for k in ("esn", "month", "t", "fy", "workscope", "shop", "exp_cost", "limit", "watch", "deadline_t", "deadline_reason", "quoted_off_wing")}
                 | {"earliest_t": b["monthly"]["labels"].index(r["earliest"]), "limit_t": b["monthly"]["labels"].index(r["limit"])}
                 | {"shop_name": names.get(r["shop"], r["shop"]),
                    "decide_by": b["monthly"]["labels"][r["deadline_t"]] if r["deadline_t"] >= 0 else "手配済み（前提）"}
                 for r in b["plan"]],
        "actions": actions_of(deltas), "track": tr,
        "outlook": b["outlook"]["stationary"],
        "unsourced": unsourced(b["company"]["id"] or ""),
    }
    if invest_path and invest_path.exists():
        c["invest"] = json.loads(invest_path.read_text(encoding="utf-8"))
        for p in c["invest"]["policies"]:
            p.pop("cum_mean", None)
    if history_path and history_path.exists():
        h = json.loads(history_path.read_text(encoding="utf-8"))
        for v in h["versions"]:
            v.pop("rows", None)
        c["history"] = h
    if roll_path and roll_path.exists():
        c["roll"] = json.loads(roll_path.read_text(encoding="utf-8"))
    mp = HERE / "multi" / f"{c['id']}.json"
    if mp.exists():
        m = json.loads(mp.read_text(encoding="utf-8"))
        c["multi"] = {k: m[k] for k in ("fleets", "fiscal_years", "pot", "landing", "labels", "deadlines_by_fleet", "deadlines_total", "curves", "allocation", "settings", "note")}
    c["resilience"] = resilience_of(b, deltas)
    c["usecases"] = usecases.build(b)
    c["horizons"] = horizons(c, b)
    c["verdict"] = verdict(c)
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", nargs="+", default=["jal", "ana"])
    ap.add_argument("--deltas-dir", type=Path, help="directory with <company>-deltas.json (compare output); run if missing")
    ap.add_argument("--actuals", default="backlog", help="which synthetic actuals to track (data/<company>/actuals_<name>.json)")
    ap.add_argument("--invest", type=Path, help="invest.py output (optional)")
    ap.add_argument("--history-dir", type=Path, help="directory with <company>-history.json (history.py output)")
    ap.add_argument("--roll-dir", type=Path, help="directory with <company>-roll-<version>.json (roll.py output)")
    ap.add_argument("--html-out", type=Path, default=Path("report.html"))
    args = ap.parse_args(argv)
    data = []
    for cid in args.companies:
        d = args.deltas_dir / f"{cid}-deltas.json" if args.deltas_dir else None
        data.append(company(HERE / "baselines" / f"{cid}-2026-10.json", d,
                            HERE / "data" / cid / f"actuals_{args.actuals}.json", args.invest,
                            args.history_dir / f"{cid}-history.json" if args.history_dir else None,
                            next(iter(sorted(args.roll_dir.glob(f"{cid}-roll-*.json"))), None) if args.roll_dir else None))
    html = (HERE / "report_hub_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=float))
    args.html_out.write_text(html, encoding="utf-8")
    print(f"{len(data)} companies -> {args.html_out} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
