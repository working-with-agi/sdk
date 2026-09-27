#!/usr/bin/env python3
"""Review the engine plan from the PDCA and OODA viewpoints (AI-assisted).

The planning pipeline produces numbers: the frozen plan, the tracker (execution vs plan,
posterior over the worlds, change points), the implicit rules (OODA replay), the roll to
the next version (bridge, learned parameters) and the run-out chain to the fleet's exit.
This module turns those numbers into a *review*: where each stage of the two loops is
weak, what the evidence is, and what to ask at the meeting.

Two layers, so the review is never empty:
  1. rules      a deterministic symptom table (facts -> findings per stage), the same for
                every run; this is what the tests cover;
  2. AI         Claude reads the fact pack and the symptom table and writes the review
                (総評, PDCA の 4 段, OODA の 4 段, 会議で聞く 5 問, 次の版で直す 3 点).
                Uses the official Anthropic SDK; when no credentials are available the
                review is the rule layer alone and says so (mode = "rules").

  python review.py jal --track out/track/jal-track-crunch.json --roll out/roll/jal-roll-2027-10.json \
                       --runout runout/jal.json --out review/jal.json [--no-ai]

Everything reviewed is synthetic; the review says so in its header.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("REVIEW_MODEL", "claude-opus-5")
STAGES = {"PDCA": ["Plan", "Do", "Check", "Act"], "OODA": ["Observe", "Orient", "Decide", "Act"]}
JP = {"Plan": "つくる", "Do": "回す", "Check": "確かめる", "Act": "直す／動く", "Observe": "見る", "Orient": "状況判断", "Decide": "決める"}


# ------------------------------------------------------------------ 1. the fact pack
def facts(b: dict, track: dict | None, roll: dict | None, runout: dict | None, history: dict | None = None, plan_from_demand: dict | None = None, backtest: dict | None = None) -> dict:
    pr = b["plan_of_record"]
    labels = b["monthly"]["labels"]
    fy = {k: {"spend": v.get("spend", 0.0), "budget": b["budgets"].get(k)} for k, v in pr["by_fiscal_year"].items()}
    for k, v in fy.items():
        v["over"] = (v["spend"] / v["budget"] - 1) if v["budget"] else 0.0
    F = {
        "company": b["company"]["name"], "version": b["version"], "horizon_months": len(labels),
        "plan": {"visits": pr["shop_visits"], "total_cost_k": pr["total_cost"], "p90_k": pr.get("p90"), "committed_k": pr.get("committed"),
                 "recourse_k": pr.get("recourse"), "recourse_p90_k": pr.get("recourse_p90"), "aog_prob": pr["aog_prob"], "relaxed": pr.get("relaxed", []),
                 "by_fy": fy, "deadlines_before_start": sum(1 for r in b["plan"] if r["deadline_t"] < 0),
                 "deadlines_next_3m": sum(1 for r in b["plan"] if 0 <= r["deadline_t"] <= 2),
                 "rush": sum(1 for r in b["plan"] if r.get("rush")), "watch": sum(1 for r in b["plan"] if r.get("watch")),
                 "by_ws": {ws: sum(1 for r in b["plan"] if r["workscope"] == ws) for ws in ("PR", "CORE", "FULL")}},
        "norms": {k: b["norms"].get(k) for k in ("visits_per_year", "spend_per_year_k", "unscheduled_share", "mean_run_months")},
    }
    if track:
        tl = track["timeline"]
        last = tl[-1]
        ex = [e for x in tl for e in x["exceptions"]]
        kinds = {}
        for e in ex:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        cpd = track.get("cpd") or {}
        oo = track.get("ooda") or {}
        F["track"] = {"months": track["actuals"]["months"], "as_of": last["as_of"], "follow_base": last["follow"].get("base"),
                      "executed": last["executed"], "posterior": last["posterior"], "exceptions": len(ex), "exceptions_by_kind": kinds,
                      "hysteresis_ok": last.get("hysteresis_ok"), "observed_world": track.get("cpd", {}).get("observed_world"),
                      "switch_best": max(((w, s["saving"]) for w, s in last["switch"].items()), key=lambda x: x[1], default=None),
                      "keep_mean_k": last["keep"]["mean"]}
        F["cpd"] = {k: cpd.get(k) for k in ("cpd_month", "bayes_month", "state", "verdict", "fired_world")} | {
            "value": cpd.get("value"), "streams_alarmed": [s["label"] for s in (cpd.get("streams") or {}).values() if s.get("week") is not None],
            "agreement_last": (cpd.get("agreement") or [{}])[-1].get("state")}
        F["ooda"] = {"unit_value_k": oo.get("unit_value_k"), "feedback": oo.get("feedback"), "loop_time": oo.get("loop_time"),
                     "cases": len(oo.get("cases", [])), "to_meeting": sum(1 for c in oo.get("cases", []) if c["to_meeting"]),
                     "by_rule": oo.get("feedback", {}).get("rule_cases_by_rule")}
    if roll:
        F["roll"] = {"from": roll["from_version"], "to": roll["to_version"], "bridge": roll["bridge"]["steps"],
                     "learned": {k: {kk: v.get(kk) for kk in ("n", "prior", "observed", "updated", "weight")} for k, v in roll["learned"].items() if isinstance(v, dict) and "prior" in v},
                     "cpd_reset": roll["learned"].get("delay", {}).get("cpd_reset"), "world": roll["learned"].get("world", {}).get("posterior"),
                     "carried": {k: (len(v) if isinstance(v, list) else v) for k, v in roll["carried"].items()}}
    if runout:
        T = runout["totals"]
        F["runout"] = {"end": runout["end"], "engines": T["engines"], "visits": T["visits"], "after_window_visits": T["after_window_visits"],
                       "spend_k": T["spend_k"], "residual_value_k": T["residual_value_k"], "green_time_engines": T["green_time_engines"],
                       "heavy_late_engines": T["heavy_late_engines"], "plan_gaps": T["plan_gaps"], "plan_gap_max_months": T.get("plan_gap_max_months", 0), "policies": runout["policies"],
                       "without_runout": runout["without_runout"], "by_year": [{k: y[k] for k in ("year", "visits", "spend_k", "retired", "engines")} for y in runout["by_year"]]}
    F["framework"] = framework_status(b, plan_from_demand, track)
    if backtest:
        F["backtest"] = {"n_versions": backtest["engine"]["n_versions"], "n_fy": backtest["engine"]["n_fy"], "coverage": backtest["engine"]["coverage"],
                         "timing_mean": backtest["engine"]["timing"]["mean"], "unsched_ratio": backtest["engine"]["unsched_ratio"],
                         "verdict": backtest["engine"]["verdict"] + backtest["demand"]["verdict"], "split": backtest["engine"].get("split")}
    if plan_from_demand:
        d = plan_from_demand["derived"]
        F["demand_growth"] = {"short": d["demand_growth_per_year"], "long": d["demand_growth_long_run"], "review": d["review"], "utilisation": d["utilisation_multiplier"]}
    if history:
        fys = [f for v in history["versions"] for f in v["fiscal_years"] if f["months"] >= 6]
        F["history"] = {"fy_inside_range": sum(f["inside"] for f in fys), "fy_scored": len(fys), "stability": history.get("stability")}
    return F


def framework_status(b: dict, plan_from_demand: dict | None, track: dict | None) -> dict | None:
    """Which assumptions are overdue for review and which triggers have fired, from
    data/assumptions_review.json plus the live signals the pipeline already computes."""
    p = HERE / "data" / "assumptions_review.json"
    if not p.exists():
        return None
    FW = json.loads(p.read_text(encoding="utf-8"))
    as_of = b["version"][:7] if b.get("version") else FW["as_of"]
    y, m = (int(v) for v in as_of.split("-"))
    now = y * 12 + m - 1
    overdue, fired = [], []
    cpd = (track or {}).get("cpd") or {}
    fb = ((track or {}).get("ooda") or {}).get("feedback") or {}
    for a in FW["assumptions"]:
        ly, lm = (int(v) for v in a["last_derived"].split("-"))
        age = now - (ly * 12 + lm - 1)
        if age > a["cadence_months"]:
            overdue.append({**a, "months_over": age - a["cadence_months"]})
        ev = None
        if a["key"] == "demand_growth" and plan_from_demand and plan_from_demand["derived"]["review"].get("triggered"):
            r = plan_from_demand["derived"]["review"]; ev = f"市場の前年比 {r['latest_yoy']['yoy']:+.1%}（{r['latest_yoy']['m']}）vs 仮定 {plan_from_demand['derived']['demand_growth_per_year']:+.1%}"
        if a["key"] in ("tat_findings", "kit_lead") and cpd.get("cpd_month") and cpd.get("streams_alarmed", None) is None:
            alarmed = [s["label"] for s in (cpd.get("streams") or {}).values() if s.get("week") is not None]
            if alarmed and (a["key"] == "kit_lead") == any("キット" in x for x in alarmed):
                ev = "変化点検知：" + "、".join(alarmed)
        if a["key"] == "worlds" and fb.get("add_world"):
            ev = f"どの世界にも当てはまらない月 {fb['no_world_fits_months']}"
        if a["key"] == "rules" and fb.get("teardown_review", "").startswith("承認線") and fb.get("teardown_net_k", 0) > 0:
            ev = f"分解の追加作業の純額 {fb['teardown_net_k'] / 1000:+.1f} 百万ドル"
        if a["key"] == "spares" and (track or {}).get("timeline"):
            late = sum(1 for x in track["timeline"] for e in x["exceptions"] if e["kind"] == "戻り遅れ")
            if late >= 3:
                ev = f"戻り遅れ {late} 件"
        if ev:
            fired.append({**a, "evidence": ev})
    return {"as_of": as_of, "n": len(FW["assumptions"]), "overdue": overdue, "fired": fired, "layers": FW["layers"],
            "table": [{k: a[k] for k in ("key", "layer", "name", "source", "cadence_months", "loop", "trigger", "affects", "owner", "last_derived", "auto")}
                      | {"status": "overdue" if any(o["key"] == a["key"] for o in overdue) else "fired" if any(f["key"] == a["key"] for f in fired) else "ok"} for a in FW["assumptions"]]}


# ------------------------------------------------------------------ 2. the rule layer
def symptoms(F: dict) -> list[dict]:
    out = []

    def add(loop, stage, sev, finding, evidence, ask):
        out.append({"loop": loop, "stage": stage, "severity": sev, "finding": finding, "evidence": evidence, "ask": ask})

    P = F["plan"]
    worst = max(P["by_fy"].items(), key=lambda kv: kv[1]["over"])
    if worst[1]["over"] > 0.05:
        add("PDCA", "Plan", "warn", f"{worst[0]} の予算前提が計画と合わない（{worst[1]['over']:+.0%}）",
            f"見込み {worst[1]['spend'] / 1000:,.1f} 百万ドル／予算 {worst[1]['budget'] / 1000:,.1f}", "予算を直すのか、入場を前後の年度へ動かすのか。どちらも決めないまま回す年にしない")
    if P["relaxed"]:
        add("PDCA", "Plan", "crit", "制約を緩めないと解けない計画", "緩めた制約: " + ", ".join(map(str, P["relaxed"])), "緩めた制約はだれの前提か。計画の外で（予備・契約）解くのか")
    if P["deadlines_before_start"]:
        add("PDCA", "Plan", "info", f"計画開始前に手配済みを前提にした判断 {P['deadlines_before_start']} 件", "判断期限が計画開始より前", "手配済みの前提（枠・キット）が本当に済んでいるか、月次の最初に確認する")
    rec = P.get("recourse_k"), P.get("total_cost_k")
    if rec[0] and rec[1] and rec[0] / rec[1] > 0.15:
        add("PDCA", "Plan", "warn", f"立て直し費が全体の {rec[0] / rec[1]:.0%}", f"立て直し {rec[0] / 1000:,.1f}／全体 {rec[1] / 1000:,.1f} 百万ドル（悪い 1 割 {P['recourse_p90_k'] / 1000:,.1f}）",
            "契約形態（固定価格・上限）で先に買うか、予備で受けるか")
    R = F.get("runout")
    if R:
        if R["heavy_late_engines"]:
            add("PDCA", "Plan", "warn", f"退役の 2 年以内に重整備（CORE/FULL）を買う機が {R['heavy_late_engines']} 基", "退役までの入場列", "その機は退役順を前に、または軽い整備範囲で持たせる")
        if R["green_time_engines"]:
            add("PDCA", "Plan", "info", f"寿命を残して退役する機 {R['green_time_engines']} 基（残存価値 {R['residual_value_k'] / 1000:,.0f} 百万ドル）", "退役までの入場列",
                "売却・グリーンタイムリース・他機種への融通を年次で決める。残存価値は税引後の資産側にも載る")
        if R["plan_gaps"]:
            add("PDCA", "Plan", "warn", f"平均の劣化では計画の入場より前に限界が来る機 {R['plan_gaps']} 基（最大 {R.get('plan_gap_max_months', 0)} か月）", "退役までの入場列（gap）",
                "その機は状態監視（EGT・LLP）を月次の最初に見る。窓の定義（earliest/limit）と劣化前提のどちらが違うか")
        pol = R["policies"]
        alt = min((v["spend_k"] for k, v in pol.items() if k != "next_due"), default=None)
        if alt is not None and pol["next_due"]["spend_k"] > alt:
            add("PDCA", "Plan", "info", "退役順の方針を変えると生涯費用が下がる", "、".join(f"{k}: {v['spend_k'] / 1000:,.0f} 百万ドル／入場 {v['visits']}" for k, v in pol.items()), "退役順を計画の変数にする")
    T = F.get("track")
    if T:
        if T["follow_base"] is not None and T["follow_base"] < 0.8:
            add("PDCA", "Do", "warn", f"計画との一致が {T['follow_base']:.0%}", f"{T['months']} か月で例外 {T['exceptions']} 件: " + "、".join(f"{k} {v}" for k, v in T["exceptions_by_kind"].items()),
                "例外の種類で対策が違う。費用超過は契約、戻り遅れは予備、時期のずれは判断の遅れ")
        else:
            add("PDCA", "Do", "ok", f"計画との一致 {T['follow_base']:.0%}", f"例外 {T['exceptions']} 件", "")
        top = max(T["posterior"].items(), key=lambda kv: kv[1])
        add("PDCA", "Check", "warn" if top[0] != "base" else "ok", f"前提のずれ：いちばん確からしい世界は「{top[0]}」（{top[1]:.0%}）",
            "確率: " + "、".join(f"{k} {v:.0%}" for k, v in T["posterior"].items()), "その世界の計画案（乗り換え）は会議に出ているか")
        if T["switch_best"] and T["switch_best"][1] > 300 and not T["hysteresis_ok"]:
            add("PDCA", "Act", "warn", f"乗り換えの価値 ΔV {T['switch_best'][1] / 1000:+.1f} 百万ドル（{T['switch_best'][0]}）だが 2 か月続いていない", "ヒステリシス", "来月も超えたら乗り換える、と今月のうちに決めておく（判断期限つき）")
    C = F.get("cpd")
    if C:
        if C["state"] == "cpd_only":
            add("OODA", "Orient", "crit", "変化点はあるのに、どの世界の確率も動かない", f"検知 {C['cpd_month']} か月目、前提 {C['bayes_month'] or '動かず'}", "前提（世界）の集合に欠けがある。安全スイッチの間、暗黙のルールを止めているか")
        elif C["state"] in ("agree", "both"):
            add("OODA", "Orient", "ok", "変化点と前提の更新が一致", f"検知 {C['cpd_month']} か月目、前提 {C['bayes_month']} か月目", "")
        if C["cpd_month"] and C["bayes_month"] and C["bayes_month"] - C["cpd_month"] >= 2:
            add("OODA", "Observe", "warn", f"先行指標が前提の確率より {C['bayes_month'] - C['cpd_month']} か月早い", "検知の遅れ D", "週次の先行指標を正式な入力にする（尤度の γ を上げるか、観測世界を自動追加）")
        if C["streams_alarmed"]:
            add("OODA", "Observe", "info", "警報の出た先行指標", "、".join(C["streams_alarmed"]), "その指標の出所（工場・サプライヤーの回答ログ）を実データでつなぐ")
        v = C.get("value") or {}
        if v.get("worth") and abs(v["worth"]) >= 100:
            add("OODA", "Orient", "info", f"早く気づく価値 {v['worth'] / 1000:+.1f} 百万ドル（{v.get('months_earlier')} か月早い分）", f"遅れ 1 か月ごとの損失 {[round((x.get('cost_of_delay') if isinstance(x, dict) else x) / 1000, 1) for x in (v.get('delay_curve') or [])][:6]} 百万ドル", "D + A ≤ R を満たしているか")
    O = F.get("ooda")
    if O and O.get("feedback"):
        fb, lt = O["feedback"], O["loop_time"]
        add("OODA", "Decide", "info", f"暗黙のルールで決めた {fb['rule_cases']} 件、会議へ {O['to_meeting']} 件", "、".join(f"{k} {v}" for k, v in (O["by_rule"] or {}).items() if v), "会議に回した件は、ルールにできないか")
        if fb.get("teardown_review", "").startswith("承認線"):
            add("OODA", "Decide", "warn" if fb["teardown_net_k"] > 0 else "ok", f"分解の追加作業の承認線（v = {O['unit_value_k']:.0f} 千ドル/基・月）の純額 {fb['teardown_net_k'] / 1000:+.1f} 百万ドル",
                fb["teardown_review"], "承認線 v を年次で見直す（追加作業の延びる月数の実績で）")
        if fb.get("no_world_fits_months", 0) >= 3:
            add("OODA", "Orient", "crit", f"どの世界にも当てはまらない月が {fb['no_world_fits_months']}", "安全スイッチ", "世界を 1 つ追加する（次の版）")
        if lt:
            D = next((p["now"] for p in lt["parts"] if p["part"].startswith("D")), 0)
            A = next((p["now"] for p in lt["parts"] if p["part"].startswith("A")), 0)
            ok = D + A <= lt["R_months"]
            add("OODA", "Act", "ok" if ok else "crit", f"D + A = {D + A:.1f} か月 {'≤' if ok else '>'} R = {lt['R_months']:.0f}（判断期限までのリード）",
                f"ループ T = {lt['T_now']:.1f} → 目標 {lt['T_target']:.1f} か月", "" if ok else "検知（D）か判断（A）のどちらを縮めるか。E（キット）は先行発注で外せるか")
    Rl = F.get("roll")
    if Rl:
        steps = {s["label"]: s["value"] for s in Rl["bridge"] if s["kind"] == "delta"}
        method = next((v for k, v in steps.items() if k.startswith("決め方")), None)
        if method is not None and abs(method) < 1:
            add("PDCA", "Act", "warn", "次の版で「決め方」を変えていない（Δ決め方 = 0）", "橋渡し: " + "、".join(f"{k[:12]}… {v / 1000:+.1f}" for k, v in steps.items()),
                "確かめるで出た 3 つのずれのうち、決め方（γ・K・世界の集合・承認線）に返したものは何か")
        for k, v in Rl["learned"].items():
            if v.get("n") and v["n"] < 10:
                add("PDCA", "Act", "info", f"{k} の学習は {v['n']} 件の実績（重み {v['weight']:.0%}）", f"事前 {v['prior']:.3g} → 更新 {v['updated']:.3g}", "件数が少ない前提は、他社・他機種の実績で補うか、来年まで動かさない")
        if Rl.get("cpd_reset"):
            add("PDCA", "Act", "ok", f"変化点で学習をリセット（{Rl['cpd_reset']['dropped']} 件を落とした）", "cpd_reset", "")
    G = F.get("demand_growth")
    if G:
        r = G["review"]
        if r.get("triggered"):
            add("PDCA", "Act", "warn", f"需要の伸びの仮定（{G['short']:+.1%}/年）から市場の前年比（{r['latest_yoy']['m']} {r['latest_yoy']['yoy']:+.1%}）が {r['trigger_pt']:.0%} 以上外れた",
                f"次の定期見直し {r['next_review']}、データは {r['data_through']} まで", "年次を待たず、需要の伸びを月次会議で引き直す（必要エンジン数と退役ペースに効く）")
        else:
            add("PDCA", "Act", "ok", f"需要の伸びの仮定は {r['derived_at']} に導出、次の見直し {r['next_review']}（{r['every_months']} か月ごと）",
                f"直近の前年比 {r['latest_yoy']['yoy']:+.1%}（{r['latest_yoy']['m']}）は仮定 {G['short']:+.1%} の範囲内" if r.get("latest_yoy") else "前年比なし", "")
        if abs(G["short"] - G["long"]) > 0.02:
            add("PDCA", "Plan", "info", f"直近の伸び {G['short']:+.1%} と長期の伸び {G['long']:+.1%} の差が大きい", "2 年先までは直近、5 年先からは長期に寄せる（growth_by_horizon）", "退役までの列と予備の数は長期の伸びで、窓の中は直近で見る")
    # the assumptions-review framework: every assumption has a cadence; overdue ones and
    # fired triggers become findings on the loop that owns them
    FW = F.get("framework")
    if FW:
        for x in FW["overdue"]:
            add("PDCA", "Act", "warn", f"前提「{x['name']}」の見直しが期限切れ（{x['months_over']} か月超過）", f"最終導出 {x['last_derived']}、周期 {x['cadence_months']} か月、影響先 {'・'.join(x['affects'])}", f"{x['owner']}が {x['loop']} で引き直す")
        for x in FW["fired"]:
            add("OODA", "Orient", "warn", f"前提「{x['name']}」の引き金が引かれた", x["evidence"], f"{x['owner']}が年次を待たず月次会議へ（影響先 {'・'.join(x['affects'])}）")
        if not FW["overdue"] and not FW["fired"]:
            add("PDCA", "Act", "ok", f"前提 {FW['n']} 件はすべて周期内、引き金なし", "assumptions_review.json", "")
    BT = F.get("backtest")
    if BT:
        sp = BT.get("split")
        if sp:
            add("PDCA", "Check", "ok" if sp["summary"]["better"] == sp["summary"]["of"] else "warn", "学ぶ・確かめる：" + sp["summary"]["text"],
                "、".join(v["text"] for v in sp["verdict"]), "改善した補正だけを次の版の決め方に持ち込む（期限のずらし・計画外の率・幅）")
        for v in BT["verdict"]:
            add("PDCA", "Check", v["status"] if v["status"] in ("ok", "warn", "info") else "info", "過去で検証：" + v["text"], f"{BT['n_versions']} 版・{BT['n_fy']} 年度のバックテスト", "" if v["status"] == "ok" else "決め方（幅・窓の下端・計画外の率）を次の版で直す")
    H = F.get("history")
    if H and H["fy_scored"]:
        r = H["fy_inside_range"] / H["fy_scored"]
        add("PDCA", "Check", "ok" if r >= 0.8 else "warn", f"当時のリスクの幅に実績が入った年度 {H['fy_inside_range']}/{H['fy_scored']}", "決め方のずれ（採点）", "" if r >= 0.8 else "幅が狭すぎる（前提の分散）か、偏っている（前提の平均）か")
    if not T:
        add("PDCA", "Check", "info", "追跡の実績がまだない（つくる、だけの状態）", "track なし", "最初の月次で何を見るか（例外の種類）を決めておく")
    order = {"crit": 0, "warn": 1, "info": 2, "ok": 3}
    out.sort(key=lambda s: (order[s["severity"]], s["loop"], STAGES[s["loop"]].index(s["stage"])))
    return out


def coverage(sym: list[dict]) -> dict:
    """Which stages have findings, and the worst severity per stage."""
    order = {"crit": 0, "warn": 1, "info": 2, "ok": 3}
    cov = {}
    for loop, stages in STAGES.items():
        for st in stages:
            xs = [s for s in sym if s["loop"] == loop and s["stage"] == st]
            cov[f"{loop}.{st}"] = {"n": len(xs), "worst": min((s["severity"] for s in xs), key=order.get, default=None)}
    return cov


def rules_text(F: dict, sym: list[dict]) -> str:
    lines = [f"# {F['company']} 計画の見直し（規則層のみ・合成データ）", ""]
    for loop in STAGES:
        lines.append(f"## {loop}")
        for st in STAGES[loop]:
            xs = [s for s in sym if s["loop"] == loop and s["stage"] == st]
            lines.append(f"### {st}（{JP[st]}）")
            lines += [f"- [{s['severity']}] {s['finding']}　（{s['evidence']}）" + (f"　→ {s['ask']}" if s["ask"] else "") for s in xs] or ["- 指摘なし"]
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ 3. the AI layer
SYSTEM = """あなたは航空会社のエンジン整備計画のレビュアーです。計画は PDCA（年次の版と月次会議：つくる→回す→確かめる→直す）と OODA（日〜週の暗黙のルール：見る→状況判断→決める→動く）の二つの輪で回っています。
与えられるのは (1) 事実パック（計画・追跡・変化点・ルールの再生・次の版への橋渡し・退役までの入場列の数値）と (2) 規則で作った症状表です。
やること：数値を言い換えるのではなく、輪のどの段が弱いかを判断し、根拠の数値を 1 つずつ添えて書く。
形式（Markdown、日本語、簡潔に）：
## 総評（3 行）
## PDCA（つくる／回す／確かめる／直す：各 2〜3 行、弱い段には ★）
## OODA（見る／状況判断／決める／動く：各 2〜3 行、弱い段には ★）
## 会議で聞く 5 つの問い（番号つき、それぞれ 1 行、誰に聞くかを添える）
## 次の版で直す 3 点（決め方＝γ・K・世界の集合・承認線・退役順のどれを、どう）
禁止：メタ／メタメタ／メタ認知という語。数値の捏造。データにない前提の断定。すべて合成データであることを冒頭に 1 行で断る。"""


def ai_review(F: dict, sym: list[dict]) -> dict:
    """Claude writes the review. Returns {"mode": "ai"|"rules", "text", "model", "usage"|"reason"}."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return {"mode": "rules", "reason": "no credentials (ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN unset)", "text": rules_text(F, sym)}
    try:
        import anthropic
    except ImportError:
        return {"mode": "rules", "reason": "anthropic package not installed (pip install anthropic)", "text": rules_text(F, sym)}
    user = ("## 事実パック\n```json\n" + json.dumps(F, ensure_ascii=False, default=float) + "\n```\n\n## 症状表（規則層）\n```json\n"
            + json.dumps(sym, ensure_ascii=False) + "\n```\n\n上の形式でレビューを書いてください。")
    try:
        client = anthropic.Anthropic()
        with client.messages.stream(model=MODEL, max_tokens=4000, thinking={"type": "adaptive"}, system=SYSTEM,
                                    messages=[{"role": "user", "content": user}]) as stream:
            msg = stream.get_final_message()
        text = "".join(blk.text for blk in msg.content if getattr(blk, "type", "") == "text")
        return {"mode": "ai", "model": msg.model, "text": text,
                "usage": {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}}
    except Exception as e:  # noqa: BLE001 - any API failure degrades to the rule layer, never to no review
        return {"mode": "rules", "reason": f"{type(e).__name__}: {e}"[:300], "text": rules_text(F, sym)}


def build(cid: str, baseline_path: Path | None, track_path: Path | None, roll_path: Path | None, runout_path: Path | None,
          history_path: Path | None = None, use_ai: bool = True, plan_path: Path | None = None, backtest_path: Path | None = None) -> dict:
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p and Path(p).exists() else None  # noqa: E731
    b = load(baseline_path or HERE / "baselines" / f"{cid}-2026-10.json")
    F = facts(b, load(track_path), load(roll_path), load(runout_path), load(history_path), load(plan_path), load(backtest_path))
    sym = symptoms(F)
    rev = ai_review(F, sym) if use_ai else {"mode": "rules", "reason": "--no-ai", "text": rules_text(F, sym)}
    return {"company": cid, "facts": F, "symptoms": sym, "coverage": coverage(sym), "review": rev, "framework": F.get("framework"),
            "inputs": {"track": str(track_path) if track_path else None, "roll": str(roll_path) if roll_path else None, "runout": str(runout_path) if runout_path else None},
            "note": "合成データ。規則層は毎回同じ判定、AI 層は Claude が事実パックと症状表から書く（資格情報がなければ規則層のみ）"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--track", type=Path)
    ap.add_argument("--roll", type=Path)
    ap.add_argument("--runout", type=Path)
    ap.add_argument("--history", type=Path)
    ap.add_argument("--plan-from-demand", type=Path, help="plan_from_demand.py output (growth review schedule)")
    ap.add_argument("--backtest", type=Path, help="backtest.py output")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-ai", action="store_true")
    a = ap.parse_args(argv)
    out = build(a.company, a.baseline, a.track, a.roll, a.runout, a.history, use_ai=not a.no_ai, plan_path=a.plan_from_demand, backtest_path=a.backtest)
    p = a.out or HERE / "review" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    sev = {}
    for s in out["symptoms"]:
        sev[s["severity"]] = sev.get(s["severity"], 0) + 1
    print(f"{a.company}: {len(out['symptoms'])} findings {sev}, review mode = {out['review']['mode']}" + (f" ({out['review'].get('reason')})" if out["review"]["mode"] == "rules" else f" model {out['review'].get('model')}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
