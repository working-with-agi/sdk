"""The asset side of the plan (what MX4-style maintenance forecasting tools do):
maintenance reserves, end-of-lease settlement and the maintenance-adjusted value of the
engines.

The planning model asks "which engine, when, how much work" from the operator's side. A
lessor or a financier asks the mirror questions: how much reserve money flows in per hour
and cycle, when it flows out at shop visits, what the balance is, what is settled at
redelivery, and what the engines are worth given their maintenance status (half-life
convention: value = half-life value + adjustment for LLP cycles and time since the last
performance restoration). This module answers those on the same plan, so both sides read
one board.

Everything is synthetic; rates and values are assumptions in data/mx4_params.json.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_params() -> dict:
    return json.loads((HERE / "data" / "mx4_params.json").read_text(encoding="utf-8"))


def engine_value(e: dict, months_since_pr: float, P: dict, cpm: float, mean_run_months: float) -> dict:
    """Maintenance-adjusted value of one engine: half-life value, plus the LLP position
    against half life (per-cycle value), plus the performance-restoration position
    against half of a typical run (per-month value)."""
    llp_left = min(e["llp_remaining"].values())
    half_llp = P["llp_life_cycles"] / 2
    llp_adj = (llp_left - half_llp) * P["llp_value_per_cycle_k"]
    run_left = max(0.0, mean_run_months - months_since_pr)
    pr_adj = (run_left - mean_run_months / 2) * P["pr_value_per_month_k"]
    return {"half_life_k": P["half_life_value_k"], "llp_adj_k": llp_adj, "pr_adj_k": pr_adj,
            "value_k": max(P["scrap_value_k"], P["half_life_value_k"] + llp_adj + pr_adj)}


def build(b: dict, fleet: dict, lease_eval: dict | None) -> dict:
    P = load_params()
    labels = b["monthly"]["labels"]
    H = len(labels)
    subs = fleet.get("meta", {}).get("derivation", {}).get("subfleets") or []
    tot = sum(x["aircraft"] for x in subs) or 1
    cpm = (sum(x["aircraft"] * x["cycles_per_year"] for x in subs) / tot / 12) if subs else 165.0
    fh_per_cycle = (sum(x["aircraft"] * x["fh_per_cycle"] for x in subs) / tot) if subs else 1.6
    mean_run = b["norms"].get("mean_run_months", 72.0)
    rows = {r["esn"]: r for r in b["plan"]}
    eng = {e["esn"]: e for e in fleet["engines"]}
    leases = (fleet.get("leases") or {}).get("engines", [])
    esc = P["escalation_per_year"]

    # 1. reserves cash flow (leased engines): inflow per month = rate_FH x FH + rate_cycle x cycles,
    #    outflow = claim at the shop visit (capped by the balance), balance carried
    infl, outfl, bal = [0.0] * H, [0.0] * H, [0.0] * H
    per_engine = []
    for le in leases:
        esn, t_r = le["esn"], le["return_t"]
        r = rows.get(esn)
        balance = P["reserve_opening_balance_k"]
        rec = {"esn": esn, "return": labels[t_r] if t_r < H else None, "inflow_k": 0.0, "claim_k": 0.0}
        for t in range(min(H, t_r + 1)):
            f = (1 + esc) ** (t / 12)
            pay = (P["reserve_rate_pr_per_fh"] * fh_per_cycle * cpm + P["reserve_rate_llp_per_cycle"] * cpm) / 1000 * f
            infl[t] += pay; balance += pay; rec["inflow_k"] += pay
            if r and r["t"] == t:   # the visit: claim the eligible part of the invoice against the balance
                claim = min(balance, r["exp_cost"] * P["claimable_share"].get(r["workscope"], 0.0))
                outfl[t] += claim; balance -= claim; rec["claim_k"] += claim
            bal[t] += balance
        rec["balance_at_return_k"] = balance
        per_engine.append(rec)
    reserves = {"labels": labels, "inflow": infl, "outflow": outfl, "balance": bal, "engines": per_engine,
                "total_inflow_k": sum(infl), "total_claims_k": sum(outfl), "n_leased": len(leases),
                "rates": {"pr_per_fh": P["reserve_rate_pr_per_fh"], "llp_per_cycle": P["reserve_rate_llp_per_cycle"], "escalation": esc}}

    # 2. end-of-lease settlement: what the operator pays (shortfall) or is refunded (surplus
    #    over the redelivery condition, when the lease refunds it), per leased engine
    settle = []
    if lease_eval:
        by = {x["esn"]: x for x in lease_eval["engines"]}
        for rec in per_engine:
            x = by.get(rec["esn"])
            if not x:
                continue
            pay = x["cost"]["as_is"] if x["recommend"] == "as_is" else 0.0
            surplus = max(0.0, x["llp_at_return"] - lease_eval["terms"]["min_llp_cycles"]) * P["llp_value_per_cycle_k"] * P["surplus_refund_share"]
            settle.append({"esn": rec["esn"], "return": x["return"], "pay_k": pay, "refund_k": surplus, "reserve_left_k": rec["balance_at_return_k"],
                           "net_k": surplus - pay - rec["balance_at_return_k"] * (0 if P["reserves_refundable"] else 1)})
    settlement = {"engines": settle, "pay_k": sum(s["pay_k"] for s in settle), "refund_k": sum(s["refund_k"] for s in settle),
                  "reserves_forfeited_k": sum(s["reserve_left_k"] for s in settle) if not P["reserves_refundable"] else 0.0}

    # 3. maintenance-adjusted value of the due engines, now and at the end of the window
    #    (after the plan's visits): the plan spends money and creates maintenance value
    vals_now, vals_end = [], []
    for esn, e in eng.items():
        since = max(0.0, mean_run - (e["window"][1]))           # crude: months since PR ~ run - months left
        v0 = engine_value(e, since, P, cpm, mean_run)
        r = rows.get(esn)
        if r:
            restored = dict(e)
            restored["llp_remaining"] = {k: (P["llp_life_cycles"] if r["workscope"] in ("CORE", "FULL") else v) for k, v in e["llp_remaining"].items()} if r["workscope"] != "PR" else e["llp_remaining"]
            v1 = engine_value(restored, max(0.0, H - r["t"]), P, cpm, mean_run)
        else:
            v1 = engine_value(e, since + H, P, cpm, mean_run)
        vals_now.append({"esn": esn, **v0}); vals_end.append({"esn": esn, **v1, "visit": r["workscope"] if r else None})
    value = {"now_k": sum(v["value_k"] for v in vals_now), "end_k": sum(v["value_k"] for v in vals_end), "n": len(eng),
             "spend_k": b["plan_of_record"]["total_cost"], "engines_now": vals_now, "engines_end": vals_end,
             "note": "半減期（ハーフライフ）基準：価値 = ハーフライフ価値 + 寿命部品の位置 × サイクル単価 + 性能回復の位置 × 月単価"}
    value["value_created_k"] = value["end_k"] - value["now_k"]
    value["value_per_spend"] = value["value_created_k"] / max(1.0, value["spend_k"])

    # 4. ten-year reserve outlook on the stationary norms (all engines, as if all were leased)
    out10 = []
    for y in [x for x in b["outlook"]["stationary"] if x["year"] >= 0][:10]:
        f = (1 + esc) ** y["year"]
        inflow = fleet["owned_engines"] * 12 * (P["reserve_rate_pr_per_fh"] * fh_per_cycle * cpm + P["reserve_rate_llp_per_cycle"] * cpm) / 1000 * f
        claims = y["spend"] * P["claimable_share_avg"] * f
        out10.append({"year": y["year"], "inflow_k": inflow, "claims_k": claims, "visits": y["visits"]})

    return {"reserves": reserves, "settlement": settlement, "value": value, "outlook": out10, "params": P,
            "note": P["note"]}
