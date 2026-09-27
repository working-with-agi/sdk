#!/usr/bin/env python3
"""The agreed order of moves, as an execution plan priced in the simulation (打ち手の順番).

The diagnosis: the slowness is the LLP-kit lead (E = 8 months of the 12-month loop) and
the findings overrun (17 of 24 exceptions), not the number of shops. So the order is
  1. kits    pre-order / pool the LLP kits, tied to the change-point detection: ordered
             only when the kit-lead stream fires (so the holding cost is paid in the
             tight world, not in the base world);
  2. contract move the contracted shop to a findings-sharing (or fixed) form;
  3. option   a framework agreement with a second shop -- an option, not a build -- for
             the crunch world and the type's late years.
Each step is solved on top of the previous ones in the base and the crunch world, and
the expected value is taken under the tracker's posterior over those worlds. The plan
also lists who moves when, the deadline and the trigger for each step.

  python playbook.py jal --track out/track/jal-track-crunch.json --out playbook/jal.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import baseline

HERE = Path(__file__).resolve().parent
LATE = "late@0.2"      # the late-years world at the level the plan can still be solved for (slots -20 %; -30 % is infeasible within the window)
WORLDS = ("base", "crunch", LATE)
LATE_WEIGHT = 0.2      # prior weight of the type's late-years world (slots -30 %, TAT +1, price +5 %); assumption (C), the tracker has no posterior for it yet
STEPS = [
    {"key": "kits", "label": "① キットの先行発注・プール（変化点検知に連動）", "actions": {"base": (), "crunch": ("kits_ahead",), LATE: ()},
     "who": "調達", "when": "変化点検知がキット納期で警報を出した月（今回は 2 か月目）", "deadline": "判断期限 R = キット納期 8 か月の前", "trigger": "先行指標『LLP キット納期回答（週）』の変化点",
     "loop": {"E_before": 8.0, "E_after": 3.0, "note": "実行のリード E をキット納期から枠予約（3 か月）へ"}},
    {"key": "contract", "label": "② 契約形態を所見折半へ（費用超過に効く）", "actions": {"base": ("contract_share50",), "crunch": ("kits_ahead", "contract_share50"), LATE: ("contract_share50",)},
     "who": "調達・財務", "when": "次の契約更新（2026 年、未確認）", "deadline": "更新の 6 か月前", "trigger": "追跡の例外のうち費用超過が過半（今回 17／24）", "loop": None},
    {"key": "second", "label": "③ 第二工場の枠組み契約（選択権、新設しない）", "actions": {"base": ("contract_share50", "second_shop"), "crunch": ("kits_ahead", "contract_share50", "second_shop"), LATE: ("contract_share50", "second_shop")},
     "who": "調達・経営", "when": "年次の版（型式の晩年に入っているので早めに）", "deadline": "工場の枠が 9／10 を超える前", "trigger": "枠の回答が 2 か月以上遅れる／混雑の世界の確率が 30% を超える", "loop": None},
]


def solve(fleet: Path, shops: Path, acts: tuple, case: str, scenarios: int, seed: int, time_limit: int) -> dict | None:
    _a, _c, summ, rows = baseline.solve_summary((acts, case, str(fleet), str(shops), scenarios, seed, 800, time_limit, ("budget",)))
    if summ is None:
        return None
    return {"total_cost": summ["total_cost"], "aog_prob": summ["aog_prob"], "p90": summ.get("p90"), "recourse": summ.get("recourse"),
            "visits": len(rows), "shops": summ.get("shops"), "relaxed": summ.get("relaxed", [])}


def build(cid: str, track_path: Path | None, scenarios: int = 40, seed: int = 42, time_limit: int = 60) -> dict:
    fleet, shops = HERE / "data" / cid / "fleet.json", HERE / "data" / cid / "shops.json"
    post = {"base": 0.8 * (1 - LATE_WEIGHT), "crunch": 0.2 * (1 - LATE_WEIGHT), LATE: LATE_WEIGHT}
    if track_path and Path(track_path).exists():
        t = json.loads(Path(track_path).read_text(encoding="utf-8"))
        last = t["timeline"][-1]["posterior"]
        tot = sum(last.get(w, 0) for w in ("base", "crunch")) or 1
        post = {w: last.get(w, 0) / tot * (1 - LATE_WEIGHT) for w in ("base", "crunch")} | {LATE: LATE_WEIGHT}
    cache = {}

    def S(acts, w):
        k = (tuple(acts), w)
        if k not in cache:
            cache[k] = solve(fleet, shops, tuple(acts), w, scenarios, seed, time_limit)
        return cache[k]

    steps = [{"key": "base", "label": "⓪ 基準計画", "actions": {w: () for w in WORLDS}, "who": "—", "when": "—", "deadline": "—", "trigger": "—", "loop": None}] + STEPS
    out_steps = []
    prev = None
    for st in steps:
        by = {w: S(st["actions"][w], w) for w in WORLDS}
        exp = {k: sum(post[w] * (by[w][k] or 0) for w in WORLDS if by[w]) for k in ("total_cost", "aog_prob", "p90", "recourse")}
        row = {**{k: st[k] for k in ("key", "label", "who", "when", "deadline", "trigger", "loop")}, "actions": {w: list(st["actions"][w]) for w in WORLDS},
               "by_world": by, "expected": exp}
        if prev:
            row["delta_vs_prev"] = {k: exp[k] - prev["expected"][k] for k in exp}
            row["delta_vs_base"] = {k: exp[k] - out_steps[0]["expected"][k] for k in exp}
        out_steps.append(row); prev = row
    E0 = 8.0; loop_now = 2.0 + 1.0 + 1.0 + E0
    loop_after = 2.0 + 1.0 + 1.0 + 3.0
    fin = out_steps[-1]
    # where each step pays: the value of an option is in the world it was bought for
    for st in out_steps[1:]:
        st["pays_in"] = {w: (st["by_world"][w]["total_cost"] - out_steps[0]["by_world"][w]["total_cost"]) for w in WORLDS if st["by_world"][w] and out_steps[0]["by_world"][w]}
    k1, k2, k3 = out_steps[1], out_steps[2], out_steps[3]
    late3 = k3["pays_in"][LATE] - k2["pays_in"][LATE]
    base3 = k3["pays_in"]["base"] - k2["pays_in"]["base"]
    verdict = [
        {"status": "info" if abs(k1["pays_in"]["crunch"]) < 500 else "ok", "text": f"① キット：逼迫の世界で {k1['pays_in']['crunch'] / 1000:+.1f} 百万ドル。費用の効果は小さいが、ループの時間を {loop_now:.0f} → {loop_after:.0f} か月に縮める（費用でなく速さの打ち手）"},
        {"status": "ok" if k2["delta_vs_base"]["total_cost"] < -1000 else "info", "text": f"② 契約：期待値で {k2['delta_vs_base']['total_cost'] / 1000:+.1f} 百万ドル、立て直し費 {k2['delta_vs_base']['recourse'] / 1000:+.1f}（費用超過に直接効く）"},
        {"status": "warn", "text": ""},
    ]
    aog3 = (k3["expected"]["aog_prob"] - k2["expected"]["aog_prob"]) * 100
    cost3 = (k3["delta_vs_base"]["total_cost"] - k2["delta_vs_base"]["total_cost"]) / 1000
    if cost3 < 0 and aog3 > 1.0:
        verdict[2] = {"status": "warn", "text": f"③ 第二工場の選択権：費用は下がる（期待値 {cost3:+.1f} 百万ドル、晩年の世界で {late3 / 1000:+.1f}）が、計画が遠い工場を使って欠航リスクを {aog3:+.1f}pt 上げる。費用でなく能力の保険として買うなら、使い方の条件（枠が埋まった月だけ）を契約に書く"}
    elif cost3 < 0:
        verdict[2] = {"status": "ok", "text": f"③ 第二工場の選択権：期待値 {cost3:+.1f} 百万ドル（基準 {base3 / 1000:+.1f}、晩年 {late3 / 1000:+.1f}）、欠航リスク {aog3:+.1f}pt：買う価値がある"}
    else:
        verdict[2] = {"status": "warn", "text": f"③ 第二工場の選択権：基準の世界で {base3 / 1000:+.1f} 百万ドル（選択権料）、晩年の世界で {late3 / 1000:+.1f}、期待値 {cost3:+.1f}：いまの重み {LATE_WEIGHT:.0%} では買わない。晩年の確率が上がったら（枠の回答の遅れ）買う"}
    return {"company": cid, "posterior": post, "worlds": {"base": "基準", "crunch": "逼迫（キット納期 12 か月・手持ち半減）", LATE: "晩年（工場の枠 −20%・工期 +1 か月・価格 +5%。−30% では窓の中で解けない）"}, "steps": out_steps, "verdict": verdict,
            "loop_time": {"before": loop_now, "after": loop_after, "E_before": E0, "E_after": 3.0, "rule": "D + A ≤ R：キットのプールで R が枠予約の 3 か月になる分、判断の猶予は減る。検知 D=2・判断 A=1 なら 3 ≤ 3 でぎりぎり"},
            "summary": {"expected_saving_k": -fin["delta_vs_base"]["total_cost"], "aog_delta_pt": fin["delta_vs_base"]["aog_prob"] * 100,
                        "p90_saving_k": -fin["delta_vs_base"]["p90"], "recourse_saving_k": -fin["delta_vs_base"]["recourse"]},
            "note": ("合成データ。各段は前の段の上に重ね、基準と逼迫の世界で解いて、追跡の事後確率（この 2 世界で正規化）で期待値を取る。"
                     "キットは条件付き（逼迫の世界でだけ発注）なので基準の世界では保有費を払わない。第二工場は選択権料を両世界で払う")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--track", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--scenarios", type=int, default=40)
    ap.add_argument("--time-limit", type=int, default=60)
    a = ap.parse_args(argv)
    out = build(a.company, a.track, a.scenarios, time_limit=a.time_limit)
    p = a.out or HERE / "playbook" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"{a.company}: posterior {', '.join(f'{w} {v:.0%}' for w, v in out['posterior'].items())}")
    for st in out["steps"]:
        e = st["expected"]; d = st.get("delta_vs_base", {})
        print(f"  {st['label']}: expected {e['total_cost']:,.0f} k$ ({d.get('total_cost', 0):+,.0f}), AOG {e['aog_prob']:.1%}, p90 {e['p90']:,.0f}, recourse {e['recourse']:,.0f} | "
              + ", ".join(f"{w} {st['by_world'][w]['total_cost']:,.0f}/{st['by_world'][w]['aog_prob']:.1%}" for w in WORLDS if st["by_world"][w]))
    print(f"  loop T {out['loop_time']['before']:.0f} -> {out['loop_time']['after']:.0f} months")
    return 0


if __name__ == "__main__":
    sys.exit(main())
