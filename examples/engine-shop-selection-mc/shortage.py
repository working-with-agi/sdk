#!/usr/bin/env python3
"""The shortage watch (エンジン不足の見張り): every time actuals arrive, look 6 months
ahead and, if engines may run short, size the fix now instead of waiting for the meeting.

From the tracker's actuals at month k: the engines in the shop (planned inductions not yet
returned, with the shop's delay distribution conditional on being overdue), the planned
inductions still to come, and unscheduled removals at the assumed rate. Monte Carlo over
those gives, per month ahead, the probability that serviceable engines fall below what
the schedule needs (AOG) and below need plus the shelf buffer (margin gone).

Verdict: if the AOG probability in the next 3 months exceeds the service target, the
watch says "re-solve now" and sizes the cheapest immediate fix: short-term leases (up to
the contract cap) to bring the probability under the target, and the levers the yearly
compare already priced (spares, pool, substitute). This is the one loop that does not
wait for the monthly meeting.

  python shortage.py jal --track out/track/jal-track-crunch.json --out out/shortage/jal.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
AHEAD = 6
DRAWS = 4000


def build(cid: str, track_path: Path, deltas_path: Path | None = None, seed: int = 5) -> dict:
    t = json.loads(track_path.read_text(encoding="utf-8"))
    b = json.loads((HERE / "baselines" / f"{cid}-2026-10.json").read_text(encoding="utf-8"))
    fleet = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))
    shops = {k["id"]: k for k in json.loads((HERE / b["paths"]["shops"]).read_text(encoding="utf-8"))["shops"]}
    m = b["monthly"]; labels = m["labels"]; H = len(labels)
    k = t["actuals"]["months"]                       # months of actuals in hand; now = start of month k
    owned = fleet["owned_engines"]
    un = fleet["unscheduled_removals"]
    rng = np.random.default_rng(seed)
    returned = {r["esn"] for r in t["actuals"]["returns"] if r["t"] < k}
    in_shop = [x for x in t["actuals"]["inductions"] if x["t"] < k and x["esn"] not in returned]
    plan = {r["esn"]: r for r in b["plan"]}
    inducted = {x["esn"] for x in t["actuals"]["inductions"] if x["t"] < k}
    to_come = [r for r in b["plan"] if r["esn"] not in inducted and k <= r["t"] < k + AHEAD]
    unsched_now = (t["actuals"]["unscheduled_in_shop"][k - 1] if k - 1 < len(t["actuals"]["unscheduled_in_shop"]) else 0) if k else 0
    months = list(range(k, min(H, k + AHEAD)))
    busy = np.zeros((DRAWS, len(months)))          # engines in the shop, per draw and month ahead
    # 1. engines in the shop now: return month = induction + quoted off-wing + shop delay + engine delay, conditional on not yet back
    for x in in_shop:
        sh = shops.get(x["shop"]) or next(iter(shops.values()))
        q = sh["quotes"][x["workscope"]]
        base = x["t"] + q["tat"] + sh.get("transport_months", 0)
        d = sh["delay"]
        delay = rng.choice(d["shop_months"], size=DRAWS, p=d["shop_probs"]) + rng.choice(d["engine_months"], size=DRAWS, p=d["engine_probs"])
        back = base + delay
        # conditional on being overdue: a return before now is impossible; push it to at least next month with the same tail
        back = np.where(back < k, k + (delay - np.maximum(0, k - base - delay)).clip(0) % 3 + 1, back)
        for j, mo in enumerate(months):
            busy[:, j] += (back > mo)
    # 2. planned inductions to come: away for the quoted off-wing plus the same delay tail
    for r in to_come:
        sh = shops.get(r["shop"]) or next(iter(shops.values()))
        d = sh["delay"]
        delay = rng.choice(d["shop_months"], size=DRAWS, p=d["shop_probs"]) + rng.choice(d["engine_months"], size=DRAWS, p=d["engine_probs"])
        back = r["t"] + r["quoted_off_wing"] + delay
        for j, mo in enumerate(months):
            busy[:, j] += ((mo >= r["t"]) & (back > mo))
    # 3. unscheduled removals: those already in the shop now, plus new ones at the assumed rate with the TAT distribution
    tat = rng.choice(un["tat_months"], size=(DRAWS, len(months)), p=un["tat_probs"])
    new = rng.poisson(un["rate_per_engine_month"] * un["background_engines"], size=(DRAWS, len(months)))
    for j in range(len(months)):
        for jj in range(j, len(months)):
            busy[:, jj] += new[:, j] * (j + tat[:, j] > jj)
    busy += unsched_now * (np.arange(len(months))[None, :] < 2)        # the current unscheduled ones: assume 2 more months
    serviceable = owned - busy
    out_months = []
    for j, mo in enumerate(months):
        req, buf = m["required"][mo], m["buffer"][mo]
        s = serviceable[:, j]
        out_months.append({"t": mo, "label": labels[mo], "required": req, "buffer": buf, "in_shop_mean": float(busy[:, j].mean()),
                           "serviceable_mean": float(s.mean()), "serviceable_p10": float(np.percentile(s, 10)),
                           "margin_mean": float((s - req - buf).mean()), "p_aog": float((s < req).mean()), "p_margin_gone": float((s < req + buf).mean())})
    target = fleet["service_target"]["max_aog_prob"]
    horizon3 = out_months[:3]
    worst = max(horizon3, key=lambda x: x["p_aog"]) if horizon3 else None
    triggered = bool(worst and worst["p_aog"] > target)
    # size the immediate fix: short-term leases to bring p_aog under the target in the worst month
    fix = None
    if worst:
        cap = fleet["short_term_lease"]["max_engines_peak"] if m["peak"][worst["t"]] else fleet["short_term_lease"]["max_engines"]
        j = months.index(worst["t"])
        need = 0
        for n in range(0, cap + 1):
            if float(((serviceable[:, j] + n) < worst["required"]).mean()) <= target:
                need = n; break
        else:
            need = cap
        p_after = float(((serviceable[:, j] + need) < worst["required"]).mean())
        fix = {"short_lease_engines": need, "cap": cap, "months": 3, "cost_k": need * fleet["short_term_lease"]["cost_per_month"] * 3, "p_aog_after": p_after,
               "enough": p_after <= target, "what": f"短期リース {need} 基を 3 か月（上限 {cap}）" if need else "追加不要"}
    levers = []
    if deltas_path and deltas_path.exists():
        d = json.loads(deltas_path.read_text(encoding="utf-8"))
        for x in d["answers"]:
            if x["feasible"] and x["delta"] and x["case"] == "base" and tuple(x["actions"]) in (("spares",), ("pool",), ("substitute",), ("slots",)):
                levers.append({"actions": x["actions"], "question": x.get("question"), "cost_k": x["delta"]["total_cost"], "aog_delta": x["delta"]["aog_prob"]})
    verdict = ("いま解き直す：" + (f"{horizon3.index(worst) + 1} か月先（{worst['label']}）の欠航確率 {worst['p_aog']:.0%} が目標 {target:.0%} を超える。{fix['what']}で {fix['p_aog_after']:.0%} に" + ("" if fix["enough"] else "。足りないので計画案を解き直す（予備・プール・代替運航）"))
               if triggered else f"見張りは静か：3 か月先までの欠航確率は最大 {worst['p_aog']:.1%}（目標 {target:.0%}）" if worst else "先の月がない")
    return {"company": cid, "as_of": t["actuals"]["as_of"], "k": k, "target": target, "in_shop_now": len(in_shop) + unsched_now, "planned_to_come": len(to_come),
            "months": out_months, "worst": worst, "triggered": triggered, "fix": fix, "levers": levers, "verdict": verdict,
            "rule": "実績が入るたびに 6 か月先まで見る。3 か月先までの欠航確率が目標を超えたら月次会議を待たずに解き直す（短期リース → 予備・プール・代替運航の順）",
            "note": "工場の遅れの分布・計画外取卸しの率・工期は入力の前提。合成データ"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--track", type=Path, required=True)
    ap.add_argument("--deltas", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = build(a.company, a.track, a.deltas)
    p = a.out or HERE / "shortage" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"{a.company} as of {out['as_of']}: in shop {out['in_shop_now']}, to come {out['planned_to_come']} | " + ", ".join(f"{x['label']} p_aog {x['p_aog']:.1%} margin {x['margin_mean']:+.1f}" for x in out["months"]))
    print("  " + out["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
