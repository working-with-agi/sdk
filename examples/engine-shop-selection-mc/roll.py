#!/usr/bin/env python3
"""Roll the plan to its next version: what the year's actuals taught, carried into the
inputs of the next 2-year plan, and the bridge from the old version to the new one.

  learn    from the tracked actuals (returns against quoted times, invoices against
           expected cost, unscheduled removals, the world probabilities) update the
           assumptions with credibility weights: few observations keep the old value,
           many observations move it towards what was seen
  carry    engines already inducted stay where they are; inductions whose decision
           deadline has passed (slot booked, kit ordered) are fixed in the new version;
           LLP kits on hand are updated
  solve    the next version from the same fleet history one year on
  bridge   old version's second year against the new version's first year, split into
           the fleet state having moved (engines due, inducted, dropped), the assumptions
           corrected, and the plan re-optimised

  python roll.py jal --actuals data/jal/actuals_backlog.json --out-dir baselines
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

import baseline
import company
import track

HERE = Path(__file__).resolve().parent
K0 = {"delay": 12, "findings": 12, "unsched": 12, "hazard": 8}   # observations at which old and new weigh the same


def cred(n: int, k0: int) -> float:
    return n / (n + k0)


def learn(b: dict, act: dict, shops: dict, fleet: dict, T: dict, cp: dict | None = None, ooda_fb: dict | None = None) -> dict:
    """Updated assumptions and the evidence behind each.

    cp: the tracker's change-point block. The n/(n+k0) weight assumes the year is one
    regime; after a detected change point in the shop's quotes only the returns of engines
    inducted from that month on are used for the delay, and n restarts there."""
    K = act["months"]
    rows = {r["esn"]: r for r in b["candidates"]["base"]["rows"]}
    ind = {x["esn"]: x for x in act["inductions"] if x["t"] < K}
    rets_all = [x for x in act["returns"] if x["t"] < K and x["esn"] in ind]
    reset_at = None
    if cp and cp.get("cpd_month") and cp.get("fired_world") == "backlog":
        reset_at = cp["cpd_month"] - 1
    rets = [x for x in rets_all if reset_at is None or ind[x["esn"]]["t"] >= reset_at]
    k = shops["shops"][0]
    out = {"evidence": {}, "shops": json.loads(json.dumps(shops)), "fleet_patch": {}}

    # 1. shop delay: excess off-wing months on returns (shop + engine delay together)
    prior_excess = sum(m * p for m, p in zip(k["delay"]["shop_months"], k["delay"]["shop_probs"])) \
        + sum(m * p for m, p in zip(k["delay"]["engine_months"], k["delay"]["engine_probs"]))
    excess = [x["t"] - ind[x["esn"]]["t"] - rows[x["esn"]]["quoted_off_wing"] for x in rets]
    z = cred(len(excess), K0["delay"])
    new_excess = z * (float(np.mean(excess)) if excess else prior_excess) + (1 - z) * prior_excess
    eng_mean = sum(m * p for m, p in zip(k["delay"]["engine_months"], k["delay"]["engine_probs"]))
    shop_mean = max(0.05, new_excess - eng_mean)
    ms = list(range(0, 5))
    w = np.array([shop_mean ** m / math.factorial(m) for m in ms])
    w /= w.sum()
    out["shops"]["shops"][0]["delay"]["shop_months"] = ms
    probs = [round(float(x), 4) for x in w]
    probs[-1] = round(1 - sum(probs[:-1]), 4)   # rounding must still sum to 1
    out["shops"]["shops"][0]["delay"]["shop_probs"] = probs
    excess_all = [x["t"] - ind[x["esn"]]["t"] - rows[x["esn"]]["quoted_off_wing"] for x in rets_all]
    z_all = cred(len(excess_all), K0["delay"])
    out["evidence"]["delay"] = {"n": len(excess), "observed": float(np.mean(excess)) if excess else None, "prior": prior_excess,
                                "updated": new_excess, "weight": z, "what": "戻ったエンジンの、見積もりより長く翼を離れた月数",
                                "cpd_reset": None if reset_at is None else {
                                    "reset_at_t": reset_at, "dropped": len(excess_all) - len(excess),
                                    "without_reset": {"n": len(excess_all), "observed": float(np.mean(excess_all)) if excess_all else None,
                                                      "weight": z_all, "updated": z_all * (float(np.mean(excess_all)) if excess_all else prior_excess) + (1 - z_all) * prior_excess}}}

    # 2. findings: invoiced against expected cost
    ratio = [x["cost_k"] / rows[x["esn"]]["exp_cost"] for x in rets]
    z = cred(len(ratio), K0["findings"])
    r_obs = float(np.mean(ratio)) if ratio else 1.0
    f = k["findings"]
    prior_share = f["prob"] * f["overrun_mean"] * k["overrun_share"]   # expected overrun share of price
    factor = 1 + z * (r_obs - 1) / max(1e-6, prior_share)
    factor = float(np.clip(factor, 0.5, 2.0))
    out["shops"]["shops"][0]["findings"]["overrun_mean"] = round(f["overrun_mean"] * factor, 3)
    out["evidence"]["findings"] = {"n": len(ratio), "observed": r_obs, "prior": 1.0, "updated": 1 + prior_share * (factor - 1) + 0.0,
                                   "weight": z, "what": "請求額 ÷ 見込み額（戻ったエンジン）", "overrun_mean": [f["overrun_mean"], round(f["overrun_mean"] * factor, 3)]}

    # 3. unscheduled removals of the rest of the fleet: engines in the shop for that reason
    un = fleet["unscheduled_removals"]
    mean_tat = sum(d * p for d, p in zip(un["tat_months"], un["tat_probs"]))
    seen = float(np.mean(act["unscheduled_in_shop"][:K]))
    implied = seen / max(1, un["background_engines"] * mean_tat)
    z = cred(K, K0["unsched"])
    rate = z * implied + (1 - z) * un["rate_per_engine_month"]
    out["fleet_patch"]["unsched_rate"] = rate
    out["evidence"]["unsched"] = {"n": K, "observed": implied, "prior": un["rate_per_engine_month"], "updated": rate, "weight": z,
                                  "what": "計画外の取卸しで工場にいるエンジン数から逆算した、1 基 1 か月あたりの率"}

    # 4. hazard of planned engines: forced inductions against what the plan expected
    forced = sum(1 for x in ind.values() if x["reason"] == "failure")
    exp_forced = T["expected"].get("base", {}).get("forced", None)
    z = cred(len(ind), K0["hazard"])
    hz = 1.0 if not exp_forced else float(np.clip(1 + z * (forced / max(0.5, exp_forced) - 1), 0.5, 2.0))
    out["fleet_patch"]["hazard_factor"] = hz
    out["evidence"]["hazard"] = {"n": len(ind), "observed": forced, "prior": exp_forced, "updated": (exp_forced or 0) * hz, "weight": z,
                                 "what": "計画前に故障して入場した基数（累計）と、計画が見込んだ数"}

    # 5. the world: this year's posterior becomes next year's prior
    out["fleet_patch"]["world_prior"] = T["posterior"]
    out["evidence"]["world"] = {"posterior": T["posterior"], "what": "追跡で更新した前提の確率を、次の版の出発点にする"}
    # 6. what the fast loop (OODA) hands to the yearly loop: rule cases and how they turned
    #    out, months with no fitting world, the detection delay, the safety-switch load
    if ooda_fb:
        out["evidence"]["ooda"] = {**ooda_fb, "what": "暗黙のルールの件数と結果、当てはまる世界がなかった月数、検知の遅れ、安全スイッチで会議に回した件数",
                                   "actions": [a for a in (
                                       "承認線 v と閾値を見直す" if ooda_fb.get("teardown_review", "").startswith("承認線 v") else None,
                                       "前提（世界）を 1 つ追加する" if ooda_fb.get("add_world") else None,
                                       f"見る先行指標を {', '.join(ooda_fb['streams_to_watch'])} にする" if ooda_fb.get("streams_to_watch") else None,
                                       "安全スイッチの月が多い：会議の処理能力を見直す" if ooda_fb.get("to_meeting_by_safety", 0) >= 3 else None) if a]}
    return out


def carry(b: dict, act: dict, new_fleet: dict) -> dict:
    """Fix in the new version what the old one already committed."""
    K = act["months"]
    rows = b["candidates"]["base"]["rows"]
    inducted = {x["esn"] for x in act["inductions"] if x["t"] < K}
    by_esn = {e["esn"]: e for e in new_fleet["engines"]}
    fixed, dropped = [], []
    for r in rows:
        if r["esn"] in inducted or r["t"] < K:
            continue
        if r["deadline_t"] >= K:
            continue  # not yet decided: free in the new version
        t_new = r["t"] - K
        if r["esn"] in by_esn and t_new < new_fleet["horizon_months"]:
            e = by_esn[r["esn"]]
            e["window"] = [t_new, t_new]
            e["allowed_workscopes"] = [r["workscope"]]
            fixed.append({"esn": r["esn"], "month": r["month"], "workscope": r["workscope"], "reason": r["deadline_reason"]})
        else:
            dropped.append(r["esn"])
    llp = new_fleet["llp_kits"]
    used = sum(1 for x in act["inductions"] if x["t"] < K and x["workscope"] in llp["workscopes"])
    ordered = sum(1 for f in fixed if f["workscope"] in llp["workscopes"])
    old_on_hand = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))["llp_kits"]["on_hand"]
    llp["on_hand"] = max(0, old_on_hand - used) + ordered
    return {"fixed": fixed, "dropped_committed": dropped, "kits": {"old_on_hand": old_on_hand, "used": used, "ordered": ordered, "new_on_hand": llp["on_hand"]}}


def solve(fleet: dict, shops: dict, tmp: Path, tag: str, scenarios: int, seed: int, time_limit: int):
    fp, sp = tmp / f"fleet_{tag}.json", tmp / f"shops_{tag}.json"
    fp.write_text(json.dumps(fleet, ensure_ascii=False), encoding="utf-8")
    sp.write_text(json.dumps(shops, ensure_ascii=False), encoding="utf-8")
    _a, _c, summ, rows = baseline.solve_summary(((), "base", str(fp), str(sp), scenarios, seed, 800, time_limit, ("budget",)))
    return summ, rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--actuals", type=Path)
    ap.add_argument("--out-dir", type=Path, default=HERE / "baselines")
    ap.add_argument("--scenarios", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=int, default=120)
    args = ap.parse_args(argv)
    cid = args.company
    bpath = args.baseline or HERE / "baselines" / f"{cid}-2026-10.json"
    apath = args.actuals or HERE / "data" / cid / "actuals_backlog.json"
    b = json.loads(bpath.read_text(encoding="utf-8"))
    act = json.loads(apath.read_text(encoding="utf-8"))
    K = act["months"]
    if K % 12:
        print("the actuals must cover whole years"); return 1
    years = K // 12
    shops = json.loads((HERE / b["paths"]["shops"]).read_text(encoding="utf-8"))
    old_fleet = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        # what the year taught
        tpath = tmp / "track.json"
        track.main(["status", "--baseline", str(bpath), "--actuals", str(apath), "--json-out", str(tpath)])
        TJ = json.loads(tpath.read_text(encoding="utf-8"))
        T = TJ["timeline"][-1]
        L = learn(b, act, shops, old_fleet, T, TJ.get("cpd"), (TJ.get("ooda") or {}).get("feedback"))

        # the fleet one year on, from the same history
        conf = json.loads((HERE / "data" / "companies.json").read_text(encoding="utf-8"))
        cfg, common = conf["companies"][cid], conf["common"]
        new_fleet, norms = company.fleet_for(cid, cfg, common, years_back=-years)
        new_fleet["meta"]["version_of"] = b["version"]
        new_fleet["meta"]["rolled_from"] = str(bpath.name)
        C = carry(b, act, new_fleet)
        # learned assumptions into the new inputs
        learned = json.loads(json.dumps(new_fleet))
        learned["unscheduled_removals"]["rate_per_engine_month"] = round(L["fleet_patch"]["unsched_rate"], 5)
        for e in learned["engines"]:
            e["hazard"] = round(min(0.5, e["hazard"] * L["fleet_patch"]["hazard_factor"]), 4)
        learned["meta"]["world_prior"] = L["fleet_patch"]["world_prior"]
        learned["meta"]["learned_from"] = {k: v for k, v in L["evidence"].items()}

        # bridge: old year 2 -> new year 1 with old assumptions -> with learned assumptions
        old_rows = b["candidates"]["base"]["rows"]
        old_y2 = [r for r in old_rows if K <= r["t"] < K + 12]
        summ_old_assump, rows_old_assump = solve(new_fleet, shops, tmp, "state", args.scenarios, args.seed, args.time_limit)
        summ_new, rows_new = solve(learned, L["shops"], tmp, "learned", args.scenarios, args.seed, args.time_limit)
        if summ_new is None or summ_old_assump is None:
            print("no feasible plan for the next version"); return 1
        y1_state = [r for r in rows_old_assump if r["t"] < 12]
        y1_new = [r for r in rows_new if r["t"] < 12]
        old_esn, state_esn, new_esn = {r["esn"] for r in old_y2}, {r["esn"] for r in y1_state}, {r["esn"] for r in y1_new}
        spend = lambda rs: sum(r["exp_cost"] for r in rs)  # noqa: E731
        bridge = {
            "old_year2": {"visits": len(old_y2), "spend": spend(old_y2)},
            "state": {"visits": len(y1_state), "spend": spend(y1_state), "added": sorted(state_esn - old_esn), "gone": sorted(old_esn - state_esn),
                      "moved": sum(1 for r in y1_state if r["esn"] in old_esn and abs(r["t"] - next(o["t"] - K for o in old_y2 if o["esn"] == r["esn"])) > 1)},
            "learned": {"visits": len(y1_new), "spend": spend(y1_new)},
            "steps": [
                {"label": f"{b['version']} 版の 2 年目", "value": spend(old_y2), "kind": "level"},
                {"label": "機材の状態が動いた分（新たに期限が来た・済んだ・時期が動いた）", "value": spend(y1_state) - spend(old_y2), "kind": "delta"},
                {"label": "前提を実績で直した分（工期・所見・故障率）", "value": spend(y1_new) - spend(y1_state), "kind": "delta"},
                {"label": "決め方を変えた分（γ・K・世界の集合は今回変えていない）", "value": 0.0, "kind": "delta"},
                {"label": f"{learned['start']} 版の 1 年目", "value": spend(y1_new), "kind": "level"},
            ],
        }
        # write the next version's inputs and baseline
        out_dir = args.out_dir
        (HERE / "data" / cid / "fleet_next.json").write_text(json.dumps(learned, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (HERE / "data" / cid / "shops_next.json").write_text(json.dumps(L["shops"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        ver = learned["start"]
        result = {"company": cid, "from_version": b["version"], "to_version": ver, "months_of_actuals": K,
                  "learned": L["evidence"], "carried": C, "bridge": bridge,
                  "next": {"plan_of_record": summ_new, "visits": len(rows_new), "by_fy": summ_new["by_fiscal_year"]},
                  "paths": {"fleet": f"data/{cid}/fleet_next.json", "shops": f"data/{cid}/shops_next.json"}}
        out_dir.mkdir(parents=True, exist_ok=True)
        rp = out_dir / f"{cid}-roll-{ver}.json"
        rp.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    ev = L["evidence"]
    print(f"{cid}: {b['version']} -> {ver} version, {K} months of actuals")
    for kk in ("delay", "findings", "unsched", "hazard"):
        e = ev[kk]
        print(f"  {kk:<9} n={e['n']:<3} prior {e['prior']!s:>8} observed {e['observed']!s:>8} -> {e['updated']:.3f} (weight {e['weight']:.2f})")
    print(f"  carried: {len(C['fixed'])} fixed, kits {C['kits']}")
    for s_ in bridge["steps"]:
        print(f"  {s_['label']}: {s_['value']:+,.0f}" if s_["kind"] == "delta" else f"  {s_['label']}: {s_['value']:,.0f}")
    print(f"  -> {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
