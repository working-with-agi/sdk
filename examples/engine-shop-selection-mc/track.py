#!/usr/bin/env python3
"""Plan tracking: as the months pass, which plan are we following, which world do the
actuals point to, and would switching now pay?

The baseline (baseline.py freeze) holds one candidate plan per assumed world:
  base     inputs as given                              -> 基準計画
  backlog  external shops +1 month TAT                  -> 混雑対応計画
  crunch   LLP kits 12 months, half the kits on hand    -> 逼迫対応計画
  stress   backlog + crunch + failure rate x1.5         -> 複合ストレス対応計画

Each month the actuals arrive: inductions (planned or forced by an in-service failure),
returns with the invoiced cost, engines in the shop for unscheduled removals, and the
LLP kit lead times suppliers quote. For every month k this script works out

  following   how closely the inductions so far match each candidate plan
  world       P(world | actuals up to k): the prior weights of decide.py updated with
              the likelihood of what was observed -- off-wing time against the quote,
              forced removals, unscheduled engines in the shop, kit lead times --
              under each world's Monte Carlo scenarios of the plan being executed
  switch      the expected cost of keeping the plan against switching now: engines
              already inducted stay as they are, the rest follow the candidate
  forecast    spend by fiscal year: invoiced + committed (in the shop) + still to come

  python track.py actuals --truth backlog --out data/actuals_backlog.json   # synthetic actuals
  python track.py actuals --truth crunch  --out data/actuals_crunch.json
  python track.py status  --actuals data/actuals_crunch.json --json-out track_crunch.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
from pathlib import Path

import numpy as np

from shop_mc import sample
from shop_mc.model import Plan

import actions
from baseline import CANDIDATES, DEFAULT_FLEET, DEFAULT_SHOPS
from decide import CASES, assess

HERE = Path(__file__).resolve().parent
WORLDS = list(CANDIDATES)  # one world per candidate plan


def key(esn, shop, ws, t, rush):
    return (esn, shop, ws, int(t), bool(rush))


def option_index(sc):
    return {key(o.visit.esn, o.shop.id, o.workscope, o.month, o.rush): i for i, o in enumerate(sc.options)}


def rows_to_indices(rows, idx):
    return [idx[key(r["esn"], r["shop"], r["workscope"], r["t"], r["rush"])] for r in rows]


# ---------------------------------------------------------------- synthetic actuals

def make_actuals(args) -> int:
    """Execute the base plan in one scenario of the 'true' world and record what an
    operator would see. The truth is written to meta only, for checking the tracker."""
    b = json.loads(args.baseline.read_text(encoding="utf-8"))
    inputs_of(args, b)
    rows = b["candidates"]["base"]["rows"]
    p = actions.build(str(args.fleet), str(args.shops), (), args.truth)
    sc = sample(p, 200, args.seed)
    s = args.scenario
    idx = rows_to_indices(rows, option_index(sc))
    K = args.months
    ind, ret = [], []
    for r, i in zip(rows, idx):
        start, down = int(sc.start[s, i]), int(sc.down[s, i])
        if start < K:
            ind.append({"esn": r["esn"], "month": p.month_label(start), "t": start, "shop": r["shop"],
                        "workscope": r["workscope"], "reason": "failure" if start < r["t"] else "planned"})
        if start + down < K:
            ret.append({"esn": r["esn"], "month": p.month_label(start + down), "t": start + down,
                        "cost_k": round(float(sc.cost[s, i]))})
    rng = np.random.default_rng(args.seed)
    kits = []
    for r in rows:  # suppliers quote a lead time whenever an LLP kit order is placed
        if r["workscope"] in p.llp_workscopes and 0 <= r["deadline_t"] < K and "LLP" in r["deadline_reason"]:
            kits.append({"month": p.month_label(r["deadline_t"]), "t": r["deadline_t"], "esn": r["esn"],
                         "lead_months": int(p.llp_kit_lead_months + rng.integers(-2, 3))})
    out = {
        "as_of": p.month_label(K - 1), "months": K,
        "inductions": sorted(ind, key=lambda x: x["t"]), "returns": sorted(ret, key=lambda x: x["t"]),
        "unscheduled_in_shop": [int(round(float(x))) for x in sc.unsched[s, :K]],
        "kit_quotes": sorted(kits, key=lambda x: x["t"]),
        "meta": {"synthetic": True, "truth_world": args.truth, "scenario": s, "seed": args.seed,
                 "executed_plan": "base",
                 "note": "合成データ。正解の世界は検証用にここだけに書き、追跡には使わない。"},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(ind)} inductions, {len(ret)} returns, {len(kits)} kit quotes up to {out['as_of']} -> {args.out}")
    return 0


# ---------------------------------------------------------------- tracking

def observed(act, rows_by_esn, k):
    """Indicator values seen in the actuals before month k (None = nothing to see yet)."""
    ind = {x["esn"]: x for x in act["inductions"] if x["t"] < k}
    rets = [x for x in act["returns"] if x["t"] < k and x["esn"] in ind]
    excess = [x["t"] - ind[x["esn"]]["t"] - rows_by_esn[x["esn"]]["quoted_off_wing"] for x in rets]
    kits = [x["lead_months"] for x in act["kit_quotes"] if x["t"] < k]
    return {
        "tat_excess": float(np.mean(excess)) if excess else None,
        "forced": float(sum(1 for x in ind.values() if x["reason"] == "failure")),
        "unsched": float(np.mean(act["unscheduled_in_shop"][:k])),
        "kit_lead": float(np.mean(kits)) if kits else None,
        "_kit_n": len(kits),
    }


def simulated(p, sc, rows, idx, k):
    """The same indicators in every scenario of one world, for the plan being executed."""
    start, down = sc.start[:, idx], sc.down[:, idx]
    planned = np.array([r["t"] for r in rows])
    quoted = np.array([r["quoted_off_wing"] for r in rows])
    back = start + down
    ret = (start < k) & (back < k)
    with np.errstate(invalid="ignore"):
        excess = np.where(ret, down - quoted, 0).sum(1) / ret.sum(1)
    return {
        "tat_excess": excess,  # NaN where nothing has come back yet
        "forced": ((start < planned) & (start < k)).sum(1).astype(float),
        "unsched": sc.unsched[:, :k].mean(1),
        "kit_lead": np.full(sc.n, float(p.llp_kit_lead_months)),
    }


FLOOR = {"tat_excess": 0.25, "forced": 0.5, "unsched": 0.3, "kit_lead": 1.5}  # measurement noise
# The worlds are caricatures and the indicators are not independent: the likelihood is
# tempered so a single month of evidence cannot make one world certain.
TEMPER = 0.5
INDICATORS = {
    "tat_excess": ("戻りの遅れ", "見積もりより何か月長く翼を離れたか（戻った基の平均）"),
    "forced": ("故障による前倒し", "計画前に故障して入場した基数（累計）"),
    "unsched": ("予定外で工場にいる数", "計画外の取卸しで工場にいるエンジン（月平均）"),
    "kit_lead": ("LLP キットの納期回答", "発注時にサプライヤーが回答した納期（か月、平均）"),
}


def loglik(obs, sims):
    out, used = 0.0, {}
    for name, x in obs.items():
        if x is None or name.startswith("_"):
            continue
        v = sims[name]
        v = v[np.isfinite(v)]
        if len(v) < 20:
            continue
        noise = FLOOR[name]
        if name == "kit_lead":  # an average of several quotes; suppliers move together, so count at most 4
            noise /= math.sqrt(min(4, max(1, obs["_kit_n"])))
        mu, sd = float(v.mean()), math.hypot(float(v.std()), noise)
        out += -0.5 * ((x - mu) / sd) ** 2 - math.log(sd)
        used[name] = {"mu": mu, "sd": sd}
    return out, used


def hybrid(base_rows, cand_rows, k, idx, options, llp_ws, kit_lead):
    """Engines already inducted (per the plan executed) stay; the rest follow the candidate.
    A candidate induction that would have been before k moves to k when the window allows.
    Each change carries the month it must be decided: the new shop's slot booking, or a
    new LLP kit order when the change needs a kit the current plan has not ordered."""
    cand = {r["esn"]: r for r in cand_rows}
    chosen, changed = [], []
    for r in base_rows:
        c = cand.get(r["esn"])
        if r["t"] < k or c is None:
            chosen.append(idx[key(r["esn"], r["shop"], r["workscope"], r["t"], r["rush"])])
            continue
        t = max(k, c["t"])
        i = idx.get(key(c["esn"], c["shop"], c["workscope"], t, c["rush"]))
        if i is None:
            i = idx[key(r["esn"], r["shop"], r["workscope"], r["t"], r["rush"])]
        elif (c["shop"], c["workscope"], t, c["rush"]) != (r["shop"], r["workscope"], r["t"], r["rush"]):
            new_kit = c["workscope"] in llp_ws and (r["workscope"] not in llp_ws or t < r["t"])
            lead, reason = options[i].shop.booking_lead_months, "工場の枠予約"
            if new_kit and kit_lead > lead:
                lead, reason = kit_lead, "LLP キット発注"
            changed.append({"esn": r["esn"], "from": {"month": r["month"], "shop": r["shop"], "workscope": r["workscope"]},
                            "to": {"t": t, "shop": c["shop"], "workscope": c["workscope"]},
                            "decide_t": t - lead, "reason": f"{reason} {lead} か月前", "new_kit": new_kit})
        chosen.append(i)
    return chosen, changed


def inputs_of(args, b):
    """Fleet and shop files: as given, else the ones the baseline was frozen from."""
    paths = b.get("paths", {})
    if args.fleet is None:
        args.fleet = HERE / paths["fleet"] if "fleet" in paths else DEFAULT_FLEET
    if args.shops is None:
        args.shops = HERE / paths["shops"] if "shops" in paths else DEFAULT_SHOPS


def status(args) -> int:
    b = json.loads(args.baseline.read_text(encoding="utf-8"))
    inputs_of(args, b)
    act = json.loads(args.actuals.read_text(encoding="utf-8"))
    C = b["candidates"]
    base_rows = C["base"]["rows"]
    rows_by_esn = {r["esn"]: r for r in base_rows}
    probs = {w: actions.build(str(args.fleet), str(args.shops), (), w) for w in WORLDS}
    p0 = probs["base"]
    lik_sc = {w: sample(probs[w], args.scenarios, args.seed) for w in WORLDS}
    eval_sc = {w: sample(probs[w], args.eval_scenarios, args.seed + 999) for w in WORLDS}
    lik_idx = {w: rows_to_indices(base_rows, option_index(lik_sc[w])) for w in WORLDS}
    ev_idx = {w: option_index(eval_sc[w]) for w in WORLDS}
    prior = {w: CASES[w][1] for w in WORLDS}
    wp = json.loads(Path(args.fleet).read_text(encoding="utf-8")).get("meta", {}).get("world_prior")
    if wp:  # a rolled version starts from where last year's tracking ended
        prior = {w: float(wp.get(w, prior[w])) for w in WORLDS}
        tot = sum(prior.values()); prior = {w: max(0.02, v / tot) for w, v in prior.items()}
        tot = sum(prior.values()); prior = {w: v / tot for w, v in prior.items()}
    cand_long = {c: (C[c]["summary"] or {}).get("long_spares", 0) for c in C}

    # expected cost of each base row in each world (for the spend forecast)
    exp_cost = {w: eval_sc[w].cost.mean(0) for w in WORLDS}
    cache = {}

    def keep_of(c, w):  # the executed plan kept to the end, evaluated in world w
        if (c, w) not in cache:
            pl = Plan(chosen=rows_to_indices(C[c]["rows"], ev_idx[w]), long_spares=cand_long[c], objective=0.0, status="frozen")
            cache[c, w] = assess(probs[w], pl, eval_sc[w])
        return cache[c, w]

    timeline = []
    for k in range(1, act["months"] + 1):
        obs = observed(act, rows_by_esn, k)
        ll, used = {}, {}
        for w in WORLDS:
            ll[w], used[w] = loglik(obs, simulated(probs[w], lik_sc[w], base_rows, lik_idx[w], k))
        m = max(ll.values())
        z = {w: prior[w] * math.exp(TEMPER * (ll[w] - m)) for w in WORLDS}
        post = {w: z[w] / sum(z.values()) for w in WORLDS}

        # which plan are we following: inductions so far against each candidate's (engine,
        # month, workscope, shop -- with one contracted shop the timing and workscope are the plan)
        actual = {(x["esn"], x["t"], x["workscope"], x["shop"]) for x in act["inductions"] if x["t"] < k}
        follow = {}
        for c, v in C.items():
            if not v["feasible"]:
                continue
            want = {(r["esn"], r["t"], r["workscope"], r["shop"]) for r in v["rows"] if r["t"] < k}
            union = actual | want
            follow[c] = len(actual & want) / len(union) if union else 1.0
        executed = max(follow, key=lambda c: (round(follow[c], 6), c == "base"))

        # exceptions against the plan being executed
        ind = {x["esn"]: x for x in act["inductions"] if x["t"] < k}
        rets = {x["esn"]: x for x in act["returns"] if x["t"] < k}
        exc = []
        for r in C[executed]["rows"]:
            a = ind.get(r["esn"])
            due_back = (a["t"] if a else r["t"]) + r["quoted_off_wing"]
            if a and a["reason"] == "failure":
                exc.append({"esn": r["esn"], "kind": "故障で前倒し", "detail": f"計画 {r['month']} → 実際 {a['month']}（{r['t'] - a['t']} か月前）", "severity": "warn"})
            elif a and a["shop"] != r["shop"]:
                exc.append({"esn": r["esn"], "kind": "工場が違う", "detail": f"計画 {r['shop']} → 実際 {a['shop']}", "severity": "warn"})
            elif a and a["t"] != r["t"]:
                exc.append({"esn": r["esn"], "kind": "時期が違う", "detail": f"計画 {r['month']} → 実際 {a['month']}", "severity": "warn"})
            elif a and a["workscope"] != r["workscope"]:
                exc.append({"esn": r["esn"], "kind": "整備範囲が違う", "detail": f"計画 {r['workscope']} → 実際 {a['workscope']}", "severity": "warn"})
            elif not a and r["t"] < k:
                exc.append({"esn": r["esn"], "kind": "未入場", "detail": f"計画 {r['month']}", "severity": "crit"})
            if a and r["esn"] not in rets and due_back < k:
                exc.append({"esn": r["esn"], "kind": "戻り遅れ", "detail": f"見積もりでは {p0.month_label(due_back)} に戻る予定（{k - due_back} か月超過）", "severity": "crit" if k - due_back >= 2 else "warn"})
            if r["esn"] in rets:
                c_ = rets[r["esn"]]["cost_k"]
                if c_ > 1.15 * r["exp_cost"]:
                    exc.append({"esn": r["esn"], "kind": "費用超過", "detail": f"請求 {c_:,} k$ ／ 見込み {r['exp_cost']:,} k$（+{c_ / r['exp_cost'] - 1:.0%}）", "severity": "warn"})

        # switching now: engines not yet inducted follow the candidate
        switch = {}
        for c, v in C.items():
            if c == executed or not v["feasible"]:
                continue
            by_w, changes_w = {}, {}
            for w in WORLDS:
                chosen, ch = hybrid(C[executed]["rows"], v["rows"], k, ev_idx[w], eval_sc[w].options,
                                    probs[w].llp_workscopes, probs[w].llp_kit_lead_months)
                for x in ch:
                    x["to"]["month"] = p0.month_label(x["to"]["t"])
                    x["overdue"] = x["decide_t"] < k - 1
                    x["decide_by"] = p0.month_label(max(0, x["decide_t"]))
                pl = Plan(chosen=chosen, long_spares=cand_long[c], objective=0.0, status="hybrid")
                a = assess(probs[w], pl, eval_sc[w])
                # a change past its decision deadline needs an emergency order: a new LLP kit
                # at the premium (a missed shop slot is assumed to be found at no extra cost)
                late = sum(1 for x in ch if x["overdue"] and x["new_kit"])
                by_w[w] = {"saving": keep_of(executed, w)["mean"] - a["mean"] - late * probs[w].emergency_kit_premium,
                           "aog_delta": a["aog_prob"] - keep_of(executed, w)["aog_prob"], "late_kits": late}
                changes_w[w] = ch
            changed = changes_w[max(post, key=post.get)]  # deadlines as the most likely world has them
            late_kits = sum(1 for x in changed if x["overdue"] and x["new_kit"])
            switch[c] = {
                "late_kits": late_kits,
                "saving": sum(post[w] * by_w[w]["saving"] for w in WORLDS),
                "aog_delta": sum(post[w] * by_w[w]["aog_delta"] for w in WORLDS),
                "by_world": by_w, "changes": changed,
                # the earliest change needs deciding before its lead time runs out
                "first_change": min((x["from"]["month"] for x in changed), default=None),
                "decide_by": min((x["decide_by"] for x in changed if not x["overdue"]), default=None),
                "overdue": sum(1 for x in changed if x["overdue"]),
            }

        # spend by fiscal year: invoiced + committed + to come (posterior-weighted)
        fc = {}
        for r in C[executed]["rows"]:
            fy = r["fy"]
            row = fc.setdefault(fy, {"invoiced": 0.0, "committed": 0.0, "to_come": 0.0, "budget": b["budgets"].get(fy, 0)})
            e = sum(post[w] * float(exp_cost[w][ev_idx[w][key(r["esn"], r["shop"], r["workscope"], r["t"], r["rush"])]]) for w in WORLDS)
            if r["esn"] in rets:
                row["invoiced"] += rets[r["esn"]]["cost_k"]
            elif r["esn"] in ind:
                row["committed"] += e
            else:
                row["to_come"] += e
        for row in fc.values():
            row["total"] = row["invoiced"] + row["committed"] + row["to_come"]
        # the scenario range: draw a world by its probability, then one of its scenarios, and
        # add up the visits not yet invoiced (findings, FX and failures move together within a
        # scenario). Gives the 10-90 % landing per fiscal year and the chance of exceeding budget.
        rng_fc = np.random.default_rng(args.seed + k)
        draws = 2000
        wsel = rng_fc.choice(len(WORLDS), size=draws, p=[post[w] for w in WORLDS])
        open_rows = [r for r in C[executed]["rows"] if r["esn"] not in rets]
        by_fy = {}
        for j, w in enumerate(WORLDS):
            idx_draw = np.nonzero(wsel == j)[0]
            if not len(idx_draw):
                continue
            sidx = rng_fc.integers(0, eval_sc[w].n, len(idx_draw))
            for r in open_rows:
                i = ev_idx[w][key(r["esn"], r["shop"], r["workscope"], r["t"], r["rush"])]
                by_fy.setdefault(r["fy"], np.zeros(draws))[idx_draw] += eval_sc[w].cost[sidx, i]
        for fy, row in fc.items():
            tot = row["invoiced"] + by_fy.get(fy, np.zeros(draws))
            row["p10"], row["p50"], row["p90"] = (float(np.percentile(tot, q)) for q in (10, 50, 90))
            row["p_over"] = float((tot > row["budget"]).mean()) if row["budget"] else 0.0
            row["by_world"] = {w: row["invoiced"] + sum(float(exp_cost[w][ev_idx[w][key(r["esn"], r["shop"], r["workscope"], r["t"], r["rush"])]])
                                                         for r in open_rows if r["fy"] == fy) for w in WORLDS}

        timeline.append({
            "k": k, "as_of": p0.month_label(k - 1), "posterior": post, "observed": obs,
            "expected": {w: {n: u["mu"] for n, u in used[w].items()} for w in WORLDS},
            "keep": {"mean": sum(post[w] * keep_of(executed, w)["mean"] for w in WORLDS),
                     "aog_prob": sum(post[w] * keep_of(executed, w)["aog_prob"] for w in WORLDS)},
            "follow": follow, "executed": executed, "exceptions": exc, "switch": switch, "forecast": fc,
            "inducted": len(ind), "returned": len(rets),
            "planned_by_now": sum(1 for r in C[executed]["rows"] if r["t"] < k),
        })

    out = {
        "baseline_version": b["version"], "months": [p0.month_label(t) for t in range(p0.horizon)],
        "worlds": {w: {"label": CASES[w][0], "prior": prior[w], "what": CASES[w][2]} for w in WORLDS},
        "candidates": {c: {"label": v["label"], "world": v["world"], "what": v["what"], "feasible": v["feasible"],
                           "summary": v["summary"], "rows": v["rows"]} for c, v in C.items()},
        "indicators": {n: {"label": a, "what": d} for n, (a, d) in INDICATORS.items()},
        # every candidate kept to the end in every world (regret matrix)
        "matrix": {c: {w: {"mean": keep_of(c, w)["mean"], "aog_prob": keep_of(c, w)["aog_prob"]} for w in WORLDS}
                   for c in C if C[c]["feasible"]},
        "budgets": b["budgets"], "shops": {}, "company": b.get("company", {}),
        "actuals": act, "timeline": timeline,
    }
    shops = json.loads(args.shops.read_text(encoding="utf-8"))["shops"]
    out["shops"] = {k["id"]: k["name"] for k in shops}
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    last = timeline[-1]
    print(f"as of {last['as_of']}: following {C[last['executed']]['label']}; world "
          + ", ".join(f"{CASES[w][0]} {last['posterior'][w]:.0%}" for w in WORLDS))
    for c, s in last["switch"].items():
        print(f"  switch to {C[c]['label']}: saving {s['saving']:+,.0f} k$, AOG {s['aog_delta'] * 100:+.1f}pt, {len(s['changes'])} engines change")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("actuals", "status"):
        sp = sub.add_parser(name)
        sp.add_argument("--baseline", type=Path, default=HERE / "baselines" / "2026-10.json")
        sp.add_argument("--fleet", type=Path, help="default: the fleet file the baseline was frozen from")
        sp.add_argument("--shops", type=Path)
        sp.add_argument("--seed", type=int, default=42)
        if name == "actuals":
            sp.add_argument("--truth", choices=WORLDS, default="backlog")
            sp.add_argument("--scenario", type=int, default=0)
            sp.add_argument("--months", type=int, default=12)
            sp.add_argument("--out", type=Path, default=HERE / "data" / "actuals.json")
        else:
            sp.add_argument("--actuals", type=Path, default=HERE / "data" / "actuals.json")
            sp.add_argument("--scenarios", type=int, default=400)
            sp.add_argument("--eval-scenarios", type=int, default=1000)
            sp.add_argument("--json-out", type=Path, default=Path("track.json"))
    args = ap.parse_args(argv)
    return make_actuals(args) if args.cmd == "actuals" else status(args)


if __name__ == "__main__":
    sys.exit(main())
