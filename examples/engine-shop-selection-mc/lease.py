"""Operating-lease redelivery: what a leased engine costs at return, and what to do about
it.

For every leased engine whose return falls in the window there are three ways out:
  as-is    return it as it is and pay the shortfall against the redelivery conditions
           (LLP cycles below the minimum, EGT margin below the minimum);
  visit    put it through the shop before the return so it meets the conditions
           (throws away the green time between the planned and the earlier induction,
           or adds a visit the plan did not have);
  extend   extend the lease by the option term at the extension rent, and return later.
The cheapest is recommended, and the decision deadline is the notice period before the
return. The plan board shows the return as its own deadline.

Synthetic throughout: data/lease_terms.json holds the assumed terms.
"""
from __future__ import annotations


def evaluate(b: dict, fleet: dict, cpm: float | None = None, loss: float | None = None) -> dict | None:
    L = fleet.get("leases")
    if not L or not L["engines"]:
        return None
    T = L["terms"]
    subs = fleet.get("meta", {}).get("derivation", {}).get("subfleets") or []
    if cpm is None:
        tot = sum(x["aircraft"] for x in subs) or 1
        cpm = (sum(x["aircraft"] * x["cycles_per_year"] for x in subs) / tot / 12) if subs else 165.0
    loss = loss if loss is not None else 4.0
    rows = {r["esn"]: r for r in b["plan"]}
    eng = {e["esn"]: e for e in fleet["engines"]}
    labels = b["monthly"]["labels"]
    horizon = len(labels)
    green = b.get("green_time_value_per_month") or 45.0
    out = []
    for le in L["engines"]:
        esn, t_r = le["esn"], le["return_t"]
        e = eng.get(esn)
        if not e or t_r >= horizon:
            continue
        r = rows.get(esn)
        llp_now = min(e["llp_remaining"].values())
        margin_now = e["egt_margin"]
        # condition at return if nothing is done
        llp_at = llp_now - cpm * t_r
        margin_at = margin_now - loss * cpm * t_r / 1000
        short_llp = max(0.0, le["min_llp_cycles"] - llp_at)
        short_margin = max(0.0, le["min_egt_margin"] - margin_at)
        asis = short_llp * T["compensation_per_cycle_k"] + short_margin * T["compensation_per_degc_k"]
        # a visit before the return: the plan's visit if it comes back in time, else earlier
        off = r["quoted_off_wing"] if r else 4
        planned_t = r["t"] if r else None
        need_t = t_r - off
        if planned_t is not None and planned_t <= need_t:
            visit = 0.0; asis = 0.0; visit_how = f"計画の入場（{labels[planned_t]}）で間に合う（条件は満たされる）"
        elif planned_t is not None:
            early = planned_t - max(0, need_t)
            visit = early * green; visit_how = f"入場を {early} か月前倒し（{labels[planned_t]} → {labels[max(0, need_t)]}）、翼上寿命 {early} か月分を捨てる"
        else:
            visit = 2900.0 + 0.0; visit_how = "窓の外の機を軽作業（PR）で入場"
        if need_t < 0:
            visit = float("inf"); visit_how = "返却までに戻らない"
        extend = le["extend_option_months"] * T["extension_rent_k_per_month"]
        opts = {"as_is": asis, "visit": visit, "extend": extend}
        best = min(opts, key=opts.get)
        deadline_t = t_r - T["notice_months"]
        out.append({"esn": esn, "lessor": le["lessor"], "return_t": t_r, "return": labels[t_r],
                    "deadline_t": deadline_t, "decide_by": labels[max(0, deadline_t)] if deadline_t >= 0 else "手配済み（前提）",
                    "llp_at_return": int(llp_at), "margin_at_return": round(margin_at, 1),
                    "short_llp": int(short_llp), "short_margin": round(short_margin, 1),
                    "planned": labels[planned_t] if planned_t is not None else None, "planned_ws": r["workscope"] if r else None,
                    "cost": {k: (None if v == float("inf") else round(v)) for k, v in opts.items()},
                    "visit_how": visit_how, "recommend": best,
                    "saving_vs_asis": round(asis - opts[best])})
    tot_asis = sum(x["cost"]["as_is"] for x in out)
    tot_best = sum(x["cost"][x["recommend"]] for x in out)
    return {"terms": T, "engines": out, "n": len(out), "total_as_is_k": tot_asis, "total_best_k": tot_best,
            "by_recommend": {k: sum(1 for x in out if x["recommend"] == k) for k in ("as_is", "visit", "extend")},
            "note": L["terms"]["note"]}
