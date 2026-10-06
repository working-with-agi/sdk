#!/usr/bin/env python3
"""The policy levers through political lenses: which levers each -ism picks, and where they agree.

The levers come with numbers from the models (airline margin, passengers, the users' fare and time
burden, public money) and with three judgments the models cannot make (the regional network, noise
and environment, the Japan-US airspace coordination). Each -ism in data/politics.json weights these
and draws red lines (an axis below which it will not go). The weights, red lines and judgment scores
are no_source -- a starting point for the argument, not anyone's platform.

  python politics.py --out fleet/politics.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUMBER_AXES = ("airline", "passengers", "user_cost", "public")


def numbers(world: str = "before") -> dict:
    """The model outputs each lever's number axes come from (FY2030, company A, p50). world "after":
    the Haneda expansion is valued in the world after the Linear (66 % of the air demand stays)."""
    load = lambda n: json.loads((HERE / "fleet" / n).read_text(encoding="utf-8"))  # noqa: E731
    inv, far, cap, cor = load("investment_jal.json"), load("fares_jal.json"), load("capacity_jal.json"), load("corridor_jal.json")
    fr = {(r["fiscal_year"], r["elasticity"]): r["vs_today_fares"] for r in far["rows"] if r["elasticity"]}
    fy = cs_fy = inv["fiscal_year"]
    hold, mkt = fr[(fy, -1.4)], fr[(fy, -0.8)]
    wb = next(w for w in cap["widebody"] if w["years_ahead"] == 3 and w["lift"] == 0 and w["variant"] == "a350+2")
    rows = {r["id"]: r for r in inv["rows"]}
    rail = next(a for a in cor["rail_airports"]["airports"] if a["airport"].startswith("山梨"))
    it = cor["itami_smaller"]
    mc = it["monte_carlo"]
    game = cor["linear_game"]["rows"][0]                                                       # the base forecast (66 % stays)
    best, nash = game["cells"][game["joint_best"]], game["cells"][game["nash"][0]]
    rule_gain = round(best["a"] - nash["a"], 1)                                                  # company A under the rule against the scramble's equilibrium
    rule_b = round(best["b"] - nash["b"], 1)
    nums = {
        "fare_hold": {"airline": hold["margin_oku"], "passengers": hold["carried_pax_k"] / 10, "user_cost": -hold["revenue_oku"], "public": 0.0},
        "fare_market": {"airline": mkt["margin_oku"], "passengers": mkt["carried_pax_k"] / 10, "user_cost": -mkt["revenue_oku"], "public": 0.0},
        "widebody": {"airline": wb["vs_base"]["margin_net_oku"], "passengers": -wb["vs_base"]["spill_pax_k"] / 10, "user_cost": 0.0, "public": 0.0},
        "slot_gain": {"airline": rows["hnd20"]["gain_per_added_round_trip_oku"], "passengers": 0.0, "user_cost": 0.0, "public": 0.0},
        "linear_rule": {"airline": rule_gain, "passengers": 0.0, "user_cost": 0.0, "public": 0.0},
        "hnd_only": {"airline": rows["hnd20"]["gain_oku_per_year"], "passengers": rows["hnd20"]["pax_k"]["added"] / 10, "user_cost": 0.0, "public": -rows["hnd20"]["cost_share_oku"][0]},
        "hnd_dest": {"airline": rows["hnd20_cts_fuk"]["gain_oku_per_year"], "passengers": rows["hnd20_cts_fuk"]["pax_k"]["added"] / 10, "user_cost": 0.0,
                     "public": -sum(rows["hnd20_cts_fuk"]["cost_share_oku"]) / 2},
        "rail_airport": {"airline": None, "passengers": rail["captured_pax_k"] / 10, "user_cost": -round(rail["captured_pax_k"] * 1e3 * rail["extra_cost_one_way_yen"] / 1e8, 1), "public": -1900.0},
        "itami_shrink": {"airline": 0.0, "passengers": 0.0, "user_cost": -it["rows"][0]["extra_cost_oku_per_year"],
                         "public": mc["public_net_oku_p10_p50_p90"][1]},
    }
    if world == "after":
        w = next(x for x in cor["linear_world"]["rows"] if x["air_keeps"] == cor["linear_world"]["rows"][0]["air_keeps"] and x["cell"] == game["joint_best"])   # the rule's world at 66 %
        for k in ("hnd20", "hnd20_cts_fuk"):
            lev = "hnd_only" if k == "hnd20" else "hnd_dest"
            nums[lev]["airline"] = w["expansion"][k]["gain_oku_per_year"]
            nums[lev]["passengers"] = w["expansion"][k]["pax_added_k"] / 10
    notes = {"slot_gain": "業界全体では移し替え（一社の得は他社の損）", "linear_rule": f"規則で二社の合計が最大の組み合わせ（66% では両社とも移さない）に寄せたときの会社 A の得（取り合いの均衡と比べて）。会社 B は {rule_b} 億円（埋め合わせが要る）",
             "hnd_only": "旅客の多くは他社から移る取り分。公費は会社 A が使う容量ぶん", "hnd_dest": "同上",
             "rail_airport": "公費は内陸の空港の例（静岡空港 全体 約 1,900 億円）。航空会社の利益は測っていない",
             "itami_shrink": "公費は 跡地の値 − 造成費 − 地価の下落 − 関西・神戸の容量の手当て の中央値（売却益として正）"}
    return {"values": nums, "notes": notes, "fiscal_year": fy}


LINEAR_ONLY = ("linear_rule", "itami_shrink", "rail_airport")   # levers that exist only once the Linear runs


def build(out: Path | None = None) -> dict:
    after = build_world("after")
    res = {"before": build_world("before", scale=after["scale"]), "after": after}           # one scale for both worlds, so a red line means the same thing
    change = {}
    for i in res["after"]["isms"]:
        b, a = res["before"]["isms"][i], res["after"]["isms"][i]
        change[i] = {"name": a["name"], "top3_before": b["top3"], "top3_after": a["top3"],
                     "new_in_top3": [k for k in a["top3"] if k not in b["top3"]], "dropped": [k for k in b["top3"] if k not in a["top3"]]}
    res["change"] = change
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def build_world(world: str = "before", scale: dict | None = None) -> dict:
    P = json.loads((HERE / "data" / "politics.json").read_text(encoding="utf-8"))
    N = numbers(world)
    levers = {k: v for k, v in P["levers"].items() if world == "after" or k not in LINEAR_ONLY}
    raw = {k: {a: (N["values"].get(k, {}).get(a) if N["values"].get(k, {}).get(a) is not None else levers[k].get(a)) for a in NUMBER_AXES} for k in levers}
    if scale is None:
        scale = {a: float(P["scales"][a]) for a in NUMBER_AXES}                                  # fixed reference values (data/politics.json)
    score = {}
    for k, L in levers.items():
        sc = {}
        for a in NUMBER_AXES:
            v = raw[k][a]
            if v is None:
                sc[a] = 0.0
            elif k in N["values"] and N["values"][k].get(a) is not None:
                sc[a] = round(max(-2.0, min(2.0, 2 * v / scale[a])), 2)
            else:
                sc[a] = float(v)                                                                  # a judgment already on the -2..+2 scale
        for a in ("regional", "noise_env", "airspace"):
            sc[a] = float(L[a])
        score[k] = sc
    isms = {}
    for i, I in P["isms"].items():
        rows = []
        for k, sc in score.items():
            total = round(sum(I["weights"][a] * sc[a] for a in sc), 3)
            red = [a for a, lim in I["red_lines"].items() if sc[a] <= lim]
            rows.append({"lever": k, "name": levers[k]["name"], "score": total, "red_lines": red})
        rows.sort(key=lambda r: (bool(r["red_lines"]), -r["score"]))
        isms[i] = {"name": I["name"], "idea": I["idea"], "ranking": rows, "top3": [r["lever"] for r in rows if not r["red_lines"]][:3],
                   "excluded": [r["lever"] for r in rows if r["red_lines"]]}
    n = len(isms)
    agree = []
    for k in levers:
        tops = sum(1 for v in isms.values() if k in v["top3"])
        ok = sum(1 for v in isms.values() if k not in v["excluded"])
        rank = [next(j for j, r in enumerate(v["ranking"]) if r["lever"] == k) + 1 for v in isms.values()]
        agree.append({"lever": k, "name": levers[k]["name"], "in_top3": tops, "not_excluded": ok, "excluded_by": [v["name"] for v in isms.values() if k in v["excluded"]],
                      "ranks": rank, "spread": max(rank) - min(rank)})
    agree.sort(key=lambda x: (-x["not_excluded"], -x["in_top3"], x["spread"]))
    # the weights are judgments: shake them (Dirichlet around each -ism's weights) and count how often a lever stays in the top 3
    import numpy as np
    rng = np.random.default_rng(11)
    axes = list(next(iter(score.values())).keys())
    stab = {}
    for i, I in P["isms"].items():
        w0 = np.array([max(I["weights"][a], 0.01) for a in axes])
        draws = rng.dirichlet(w0 * 20, 2000)
        M = np.array([[score[k][a] for a in axes] for k in levers])
        allowed = np.array([not any(score[k][a] <= lim for a, lim in I["red_lines"].items()) for k in levers])
        tot = draws @ M.T                                                                         # draws x levers
        tot[:, ~allowed] = -1e9
        top = np.argsort(-tot, axis=1)[:, :3]
        keys = list(levers)
        stab[i] = {keys[j]: round(float((top == j).any(axis=1).mean()), 2) for j in range(len(keys)) if allowed[j]}
    for i in isms:
        isms[i]["top3_probability"] = dict(sorted(stab[i].items(), key=lambda kv: -kv[1]))
    res = {"fiscal_year": N["fiscal_year"], "raw": raw, "scale": scale, "scores": score, "number_notes": N["notes"], "isms": isms, "agreement": agree,
           "consensus": [a["lever"] for a in agree if a["not_excluded"] == n and a["in_top3"] >= n // 2],
           "contested": [a["lever"] for a in agree if a["excluded_by"] and a["in_top3"] >= 1],
           "world": world, "assumptions": {"weights_and_scores": "data/politics.json（no_source）", "how": P["how"],
                                            "world": "before：リニアの前（伊丹を縮める・リニア後の配分の規則・鉄道でつなぐ新空港はない）。after：リニアの後（羽田の拡張はリニア後の世界で評価）"}}
    return res


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--out", type=Path)
    R = build(a.parse_args(argv).out)
    for i, c in R["change"].items():
        print(f"{c['name']}: before {c['top3_before']} -> after {c['top3_after']}")
    r = R["after"]
    for i, v in r["isms"].items():
        print(f"{v['name']}: top3 {v['top3']} excluded {v['excluded']} p(top3) {v['top3_probability']}")
    print("consensus", r["consensus"], "contested", r["contested"])
    for x in r["agreement"]:
        print(f"  {x['name']}: top3 in {x['in_top3']}, allowed by {x['not_excluded']}, ranks {x['ranks']}, excluded by {x['excluded_by']}")
    print("scores", json.dumps(r["scores"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
