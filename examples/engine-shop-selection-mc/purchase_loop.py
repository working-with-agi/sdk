#!/usr/bin/env python3
"""The purchase loop (購入計画と繰り返しシミュレーション): put a purchase plan on the
table, simulate the plan on the flight schedule, read the AOG risk and cost, add the
cheapest single move, and repeat until the service target holds.

Inner loop (this script)
  candidates   spares@+1 (long-term lease), buy@+1 (purchase), pool@+1 (short-lease cap),
               midlife@+2 (green-time swaps instead of visits)
  step         solve the plan with the current set in the worlds the tracker weighs
               (base, crunch) -> expected cost and AOG; pick the candidate with the lowest
               cost per point of AOG removed; stop when AOG <= target, when no candidate
               helps, or after MAX_STEPS
  output       the purchase plan as a schedule (what, how many, order-by month from the
               lead time, cost) and the trajectory (AOG and cost per iteration)

Outer loops (feedback)
  monthly      actuals -> shortage watch; when it fires, this loop re-runs from the
               current fleet (--from-shortage seeds the short leases it sized)
  yearly       backtest corrections and the demand layer re-derive the inputs; the loop
               re-runs on the new version

  python purchase_loop.py jal --track out/track/jal-track-crunch.json --out out/purchase/jal.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import baseline
from actions import BUY

HERE = Path(__file__).resolve().parent
WORLDS = ("base", "crunch")
CANDIDATES = [("spares", 1, "予備エンジンを長期リースで +1 基", 1), ("buy", 1, "予備エンジンを購入 +1 基", BUY["lead_months"]),
              ("pool", 1, "短期リースの上限を +1 基（プール契約）", 1), ("midlife", 2, "中寿命エンジンへの入れ替え枠 +2 基", 3)]
MAX_STEPS = 8
# the couplings that bound the loop (問題の相互作用):
#   market   green-time engines come from other operators' retirements; in the type's late
#            years with retirements below forecast the market supplies few per year (C)
#   shop     the contracted shop's capacity response needs the committed visits per year;
#            swaps that remove visits below that line forfeit it (shop_response.json)
#   spares   owned spares beyond the shelf need are idle capital (long_spare_max in fleet.json)
CAPS = {"midlife": 4, "pool": 3, "buy": 4}
CAP_NOTES = {"midlife": "中古市場から 2 年で調達できる中寿命機の上限（型式の晩年、退役が予想より少ない：仮定 4 基）",
             "pool": "短期リースの上限は契約の枠（+3 まで）", "buy": "購入は fleet.json の long_spare_max まで"}


def solve(fleet, shops, acts, case, scenarios, seed, time_limit):
    _a, _c, summ, rows = baseline.solve_summary((tuple(acts), case, str(fleet), str(shops), scenarios, seed, 800, time_limit, ("budget",)))
    if summ is None:
        return None
    shop_visits = sum(1 for r in rows if r["workscope"] != "GT")
    return {"total_cost": summ["total_cost"], "aog_prob": summ["aog_prob"], "p90": summ.get("p90"), "visits": shop_visits, "swaps": len(rows) - shop_visits}


def acts_of(counts: dict) -> tuple:
    return tuple(f"{k}@{n}" for k, n in counts.items() if n > 0)


def build(cid: str, track_path: Path | None, shortage_path: Path | None, scenarios: int = 40, seed: int = 42, time_limit: int = 60) -> dict:
    fleet, shops = HERE / "data" / cid / "fleet.json", HERE / "data" / cid / "shops.json"
    f = json.loads(fleet.read_text(encoding="utf-8"))
    target = f["service_target"]["max_aog_prob"]
    post = {"base": 0.8, "crunch": 0.2}
    if track_path and Path(track_path).exists():
        last = json.loads(Path(track_path).read_text(encoding="utf-8"))["timeline"][-1]["posterior"]
        tot = sum(last.get(w, 0) for w in WORLDS) or 1
        post = {w: last.get(w, 0) / tot for w in WORLDS}
    seed_from = None
    if shortage_path and Path(shortage_path).exists():
        sh = json.loads(Path(shortage_path).read_text(encoding="utf-8"))
        if sh.get("triggered") and sh.get("fix", {}).get("short_lease_engines"):
            seed_from = {"pool": sh["fix"]["short_lease_engines"], "why": "不足の見張りが出した短期リースの基数から始める"}
    cache = {}

    def evaluate(counts):
        key = acts_of(counts)
        if key not in cache:
            by = {w: solve(fleet, shops, key, w, scenarios, seed, time_limit) for w in WORLDS}
            ok = [w for w in WORLDS if by[w]]
            exp = {k: sum(post[w] * by[w][k] for w in ok) / max(1e-9, sum(post[w] for w in ok)) for k in ("total_cost", "aog_prob")} if ok else None
            cache[key] = {"by_world": by, "expected": exp}
        return cache[key]

    counts = {k: 0 for k, *_ in CANDIDATES}
    if seed_from:
        counts["pool"] = seed_from["pool"]
    cur = evaluate(counts)
    traj = [{"step": 0, "actions": list(acts_of(counts)), "expected": cur["expected"], "by_world": cur["by_world"], "added": None}]
    stop = None
    for step in range(1, MAX_STEPS + 1):
        if cur["expected"] is None:
            stop = "解けない"; break
        if cur["expected"]["aog_prob"] <= target:
            stop = f"目標 {target:.0%} に到達"; break
        best = None
        for name, inc, label, lead in CANDIDATES:
            if counts[name] + inc > CAPS.get(name, 99) + (0 if name != "buy" else f["long_term_spare"]["max_engines"] - CAPS["buy"]):
                continue
            trial = {**counts, name: counts[name] + inc}
            r = evaluate(trial)
            if not r["expected"]:
                continue
            d_aog = cur["expected"]["aog_prob"] - r["expected"]["aog_prob"]
            d_cost = r["expected"]["total_cost"] - cur["expected"]["total_cost"]
            if d_aog <= 0.002:
                continue
            score = d_cost / d_aog                               # k$ per unit of AOG probability removed (negative = saves money too)
            if best is None or score < best["score"]:
                best = {"name": name, "inc": inc, "label": label, "lead": lead, "score": score, "d_aog": d_aog, "d_cost": d_cost, "result": r, "trial": trial}
        if best is None:
            stop = "効く候補がない（残りは計画側：便の削減か納期の前倒し）"; break
        counts = best["trial"]; cur = best["result"]
        traj.append({"step": step, "actions": list(acts_of(counts)), "expected": cur["expected"], "by_world": cur["by_world"],
                     "added": {k: best[k] for k in ("name", "inc", "label", "lead", "d_aog", "d_cost")}})
    else:
        stop = f"{MAX_STEPS} 手で打ち切り"
    labels = json.loads((HERE / "baselines" / f"{cid}-2026-10.json").read_text(encoding="utf-8"))["monthly"]["labels"]
    plan = []
    for name, inc, label, lead in CANDIDATES:
        n = counts[name]
        if n:
            plan.append({"what": label.split("（")[0].replace(" +1 基", "").replace(" +2 基", ""), "key": name, "count": n, "lead_months": lead,
                         "order_by": labels[0], "in_service": labels[min(len(labels) - 1, lead)],
                         "note": {"spares": "長期リース 85 k$/月・基", "buy": f"購入 {BUY['price_k']:,} k$/基、窓の費用は資本費＋償却", "pool": "プール契約 350 k$/年", "midlife": "入場の代わりに中古の中寿命機へ"}[name]})
    # couplings read back from the result: visits removed vs the shop commitment, capital tied up
    sr = HERE / "shop_response" / f"{cid}.json"
    commit = None
    if sr.exists():
        srj = json.loads(sr.read_text(encoding="utf-8")); commit = srj["inputs"]["committed_visits_per_year"]
    v0 = traj[0]["by_world"]["base"]["visits"] if traj[0]["by_world"].get("base") else None
    v1 = traj[-1]["by_world"]["base"]["visits"] if traj[-1]["by_world"].get("base") else None
    couplings = []
    if v0 is not None and v1 is not None and commit:
        per_year = v1 / 2
        couplings.append({"kind": "工場の約束", "text": f"入場 {v0} → {v1} 件（年 {per_year:.0f}）。約束の年 {commit} 件を{'割る' if per_year < commit else '保つ'}" + ("：工場の増強条件（容量反応）を失う。契約量の見直しか、約束の付け替えが要る" if per_year < commit else "")})
    if counts.get("midlife"):
        couplings.append({"kind": "中古市場", "text": f"中寿命機 {counts['midlife']} 基は他社の退役から来る。型式の晩年で退役が予想より少なく、価格も残存価値の曲線で動く（typelife）"})
    if counts.get("buy") or counts.get("spares"):
        couplings.append({"kind": "資産", "text": "予備の追加は退役までの列で「寿命を残して退役する機」を増やす。税引後（購入かリースか）は 5 年で見る（tax）"})
    couplings.append({"kind": "契約", "text": "入場が減ると所見折半・固定価格の価値（費用超過に効く分）も減る。打ち手の順番（playbook）を購入計画の後に再評価する"})
    first, last = traj[0]["expected"], traj[-1]["expected"]
    return {"company": cid, "target": target, "posterior": post, "seed_from": seed_from, "trajectory": traj, "purchase_plan": plan, "stop": stop,
            "summary": {"steps": len(traj) - 1, "aog_before": first["aog_prob"] if first else None, "aog_after": last["aog_prob"] if last else None,
                        "cost_before": first["total_cost"] if first else None, "cost_after": last["total_cost"] if last else None,
                        "reached": bool(last and last["aog_prob"] <= target)},
            "couplings": couplings, "caps": {k: {"cap": v, "note": CAP_NOTES[k]} for k, v in CAPS.items()},
            "feedback": {"monthly": "実績 → 不足の見張り（3 か月先の欠航確率 > 目標）→ この輪を今の機隊から再実行（--from-shortage）", "yearly": "バックテストの補正と需要の層で入力を引き直し → 年次の版でこの輪を再実行",
                         "inner": "購入計画を置く → 便の計画で解く → 欠航確率と費用 → 最も安い 1 手を足す → 目標まで繰り返す"},
            "note": "候補の費用は年次の値付けと同じ前提（合成）。購入の資本費・償却・納期は仮定（C）。目標は service_target.max_aog_prob"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--track", type=Path)
    ap.add_argument("--from-shortage", type=Path, help="shortage.py output: seed the loop with its short-lease fix")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--scenarios", type=int, default=40)
    ap.add_argument("--time-limit", type=int, default=60)
    a = ap.parse_args(argv)
    out = build(a.company, a.track, a.from_shortage, a.scenarios, time_limit=a.time_limit)
    p = a.out or HERE / "purchase" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    S = out["summary"]
    print(f"{a.company}: {S['steps']} steps, AOG {S['aog_before']:.1%} -> {S['aog_after']:.1%} (target {out['target']:.0%}), cost {S['cost_before']:,.0f} -> {S['cost_after']:,.0f} k$ | {out['stop']}")
    for st in out["trajectory"][1:]:
        ad = st["added"]; print(f"  +{ad['label']}: AOG -{ad['d_aog'] * 100:.1f}pt, cost {ad['d_cost']:+,.0f} k$ -> {st['expected']['aog_prob']:.1%}")
    for x in out["purchase_plan"]:
        print(f"  plan: {x['what']} x{x['count']}, order {x['order_by']}, in service {x['in_service']} ({x['note']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
