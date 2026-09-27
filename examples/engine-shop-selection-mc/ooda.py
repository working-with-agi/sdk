"""The fast loop: implicit rules that act between monthly meetings (OODA), and the
counts that feed back into the yearly loop (PDCA).

Observe   three stream types: leading (weekly quotes), engine state (per flight),
          outcomes (visits, returns, invoices, unscheduled removals).
Orient    three outcomes: stay in the current world / move to a prepared world / no
          world fits (a change point without a world moving -> the safety switch).
Decide    the implicit rules in data/<company>/rules.json, priced with the unit value
          v = annual shop cost / installed engines / 12 (k$ per engine-month).
Act       same day / days / monthly meeting / yearly board, per rule.

Loop time T = D + O + A + E: detection delay, orientation interval, decision time,
execution lead. The report shows each part with its lever.

All cases here are synthetic, replayed from the tracker's month-by-month timeline.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

DEFAULT_RULES = {
    "note": "暗黙のルール：月次会議を待たずに動く判断。単位価値 v = 年間整備費 ÷ 取付エンジン数 ÷ 12（1 基が 1 か月飛ぶ価値）",
    "unit_value_note": "v は fleet.json の定常整備費と取付エンジン数から毎回計算する",
    "rules": [
        {"id": "teardown_extra", "trigger": "分解で追加作業が見つかった", "condition": "追加費用 ≤ 延びる翼上月数 × v", "action": "承認（当日）", "who": "整備計画の担当", "cadence": "same_day"},
        {"id": "cm_alert", "trigger": "状態監視の警報", "condition": "残り寿命が短い（期限まで 3 か月未満）または取卸しが繁忙期に落ちる", "action": "今下ろす（当日）。それ以外は様子見", "who": "技術", "cadence": "same_day"},
        {"id": "tat_slip", "trigger": "戻り遅れで予備が足りない", "condition": "余力がマイナス", "action": "短期リースを上限まで（数日）", "who": "運航・調達", "cadence": "days"},
        {"id": "world_shift", "trigger": "前提（世界）の確率が動いた", "condition": "乗り換えの価値 ΔV を計算", "action": "月次会議へ（判断期限つき）", "who": "整備計画", "cadence": "monthly"},
        {"id": "safety_switch", "trigger": "どの世界にも当てはまらない（変化点あり・確率動かず）", "condition": "—", "action": "暗黙のルールを全て停止し、全件を会議へ", "who": "全員", "cadence": "monthly"},
        {"id": "invest_gate", "trigger": "投資ゲートの条件（受領・海外の待ち）が揃った", "condition": "段階の判断条件", "action": "取締役会へ（年次）", "who": "経営", "cadence": "yearly"},
    ],
    "thresholds": {"cm_months_left": 3, "hysteresis_months": 2, "material_k": 300},
}


def load_rules(company: str | None) -> dict:
    p = HERE / "data" / (company or "") / "rules.json"
    if company and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return DEFAULT_RULES


def unit_value(b: dict, p0) -> float:
    """k$ per engine-month: annual shop cost / installed engines / 12 (installed = owned
    less the shelf buffer)."""
    installed = max(1, p0.owned_engines - max(p0.buffer))
    return b["norms"]["spend_per_year_k"] / installed / 12


def replay(b: dict, act: dict, timeline: list, cpd: dict | None, rules: dict, p0, seed: int = 3) -> dict:
    """Apply the implicit rules month by month to what the tracker saw. Returns the
    cases, the counts per month and the OODA->PDCA feedback."""
    rng = np.random.default_rng(seed)
    v = unit_value(b, p0)
    th = rules["thresholds"]
    rows = {r["esn"]: r for r in b["plan"]}
    peak = b["monthly"]["peak"]
    labels = b["monthly"]["labels"]
    rets = {x["esn"]: x for x in act["returns"]}
    K = act["months"]
    safety_from = None
    if cpd and cpd.get("state") == "cpd_only" and cpd.get("cpd_month"):
        safety_from = cpd["cpd_month"]
    months_out, cases = [], []
    lease_max = p0.short_lease_max
    for x in timeline:
        k = x["k"]
        safety = bool(safety_from and k >= safety_from and (cpd["agreement"][k - 1]["state"] == "cpd_only"))
        m = {"k": k, "as_of": x["as_of"], "safety_switch": safety, "by_rule": {}, "to_meeting": 0, "decided": 0}
        # 1. extra work found at teardown: returns this month invoiced above the expected cost
        for esn, r in rets.items():
            if r["t"] != k - 1 or esn not in rows:
                continue
            extra = r["cost_k"] - rows[esn]["exp_cost"]
            if extra <= 0:
                continue
            added = int(rng.integers(2, 15))          # months the extra work adds on wing (synthetic)
            ok = extra <= added * v
            cases.append(_case(m, "teardown_extra", safety, esn, f"追加 {extra:,.0f} k$、延びる {added} か月 × v {v:,.0f} = {added * v:,.0f}",
                               "承認" if ok else "見送り", outcome=extra - added * v))
        # 2. condition-monitoring alerts: engines on watch with a deadline near, not yet inducted
        ind = {y["esn"] for y in act["inductions"] if y["t"] < k}
        for esn, r in rows.items():
            if not r.get("watch") or esn in ind or r["t"] < k - 1:
                continue
            if r["t"] != k - 1 + 3:                    # an alert arrives 3 months ahead of the planned month (synthetic)
                continue
            left = r["limit_t"] - (k - 1) if "limit_t" in r else labels.index(r["limit"]) - (k - 1)
            in_peak = bool(peak[min(len(peak) - 1, r["t"])])
            now = left < th["cm_months_left"] or in_peak
            cases.append(_case(m, "cm_alert", safety, esn, f"期限まで {left} か月、計画月は{'繁忙期' if in_peak else '閑散期'}", "今下ろす" if now else "様子見"))
        # 3. TAT slip: returns overdue and margin negative -> short-term lease
        late = [e for e in x["exceptions"] if e["kind"] == "戻り遅れ"]
        margin = b["monthly"]["serviceable"][k - 1] - b["monthly"]["required"][k - 1] - b["monthly"]["buffer"][k - 1] - len(late)
        if late and margin < 0:
            n = min(lease_max, -margin)
            cases.append(_case(m, "tat_slip", safety, ",".join(e["esn"] for e in late), f"戻り遅れ {len(late)} 基、余力 {margin:+d}", f"短期リース {n} 基"))
        # 4. world shift: probability moved -> switch value to the meeting
        top = max(x["posterior"], key=x["posterior"].get)
        if top != "base" and x["posterior"][top] > 0.5:
            sw = x["switch"].get(top)
            if sw:
                cases.append(_case(m, "world_shift", safety, top, f"ΔV {sw['saving']:+,.0f} k$、判断期限 {sw['decide_by'] or '—'}", "会議へ", meeting=True))
        # 5. safety switch itself
        if safety:
            cases.append(_case(m, "safety_switch", safety, "—", "変化点あり・前提の確率は動かず", "全件を会議へ", meeting=True))
        # 6. investment gate: not evaluated monthly (yearly, from invest.py)
        months_out.append(m)
    # OODA -> PDCA feedback
    decided = [c for c in cases if not c["to_meeting"]]
    outcomes = [c["outcome"] for c in cases if c["rule"] == "teardown_extra" and c["outcome"] is not None]
    D = cpd["value"]["months_earlier"] if cpd and cpd.get("value") else None
    fb = {
        "rule_cases": len(decided), "rule_cases_by_rule": {r["id"]: sum(1 for c in decided if c["rule"] == r["id"]) for r in rules["rules"]},
        "teardown_net_k": float(np.sum(outcomes)) if outcomes else 0.0,
        "teardown_review": "承認線 v を見直す" if outcomes and float(np.mean(outcomes)) > 0 else "承認線は妥当",
        "no_world_fits_months": sum(1 for m in months_out if m["safety_switch"]),
        "add_world": bool(sum(1 for m in months_out if m["safety_switch"]) >= 3),
        "detection_delay_months": None if not cpd else (cpd["cpd_month"] or None),
        "bayes_delay_months": None if not cpd else cpd.get("bayes_month"),
        "to_meeting_by_safety": sum(1 for c in cases if c["rule"] == "safety_switch"),
        "streams_to_watch": None if not cpd else [s["label"] for s in cpd["streams"].values() if s.get("week") is not None],
    }
    loop = loop_time(cpd, fb, p0)
    return {"unit_value_k": v, "rules": rules["rules"], "thresholds": th, "cases": cases, "months": months_out,
            "feedback": fb, "loop_time": loop, "note": "合成データ。追加作業の延びる月数と警報の到着は仮定"}


def _case(m, rule, safety, esn, detail, decision, outcome=None, meeting=False):
    to_meeting = meeting or safety
    c = {"k": m["k"], "as_of": m["as_of"], "rule": rule, "esn": esn, "detail": detail,
         "decision": "会議へ（安全スイッチ）" if safety and not meeting else decision, "to_meeting": to_meeting, "outcome": outcome}
    m["by_rule"][rule] = m["by_rule"].get(rule, 0) + 1
    if to_meeting:
        m["to_meeting"] += 1
    else:
        m["decided"] += 1
    return c


def loop_time(cpd, fb, p0) -> dict:
    """T = D + O + A + E with the current value and the lever for each part."""
    D_now = 6.0 if not cpd or not cpd.get("cpd_month") else float(cpd["cpd_month"])
    D_bayes = None if not cpd else cpd.get("bayes_month")
    kit = int(p0.llp_kit_lead_months)
    book = int(max((k.booking_lead_months for k in p0.shops if hasattr(k, "booking_lead_months")), default=3))
    parts = [
        {"part": "D 検知の遅れ", "now": D_now, "unit": "か月", "was": D_bayes if D_bayes else "12+（前提の確率が動かず）",
         "lever": "先行指標（見積もり工期・枠回答・キット納期）を週次で見て変化点検知にかける"},
        {"part": "O 状況判断の間隔", "now": 1.0, "unit": "か月", "was": "月次", "lever": "週次データが来るたびに更新する（0.25 か月）", "target": 0.25},
        {"part": "A 判断の時間", "now": 1.0, "unit": "か月", "was": "月次会議", "lever": "暗黙のルールで当日〜数日に（会議は乗り換えと安全スイッチだけ）", "target": 0.1},
        {"part": "E 実行のリード", "now": float(max(kit, book)), "unit": "か月", "was": f"キット {kit}・枠予約 {book}", "lever": "先行発注・プール契約でキットの待ちを外す", "target": float(book)},
    ]
    T_now = sum(p["now"] for p in parts)
    T_target = sum(p.get("target", p["now"]) for p in parts)
    return {"parts": parts, "T_now": T_now, "T_target": T_target,
            "timing_rule": "D + A ≤ R（判断期限までのリード）。逼迫世界では 1 か月遅れるごとに約 0.9 百万ドル（単一フリート例）",
            "R_months": float(kit)}
