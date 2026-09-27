"""After-tax yardstick for the same plan: what the plan costs once the tax shield of each
fiscal year is counted, how a shift of spend between fiscal years moves the after-tax
figure, spare engines bought against leased, the domestic shop with and without 圧縮記帳,
and the shops compared at effective after-tax cost.

Nothing here chooses a shop or a month for tax reasons. The plan is fixed; this module
only converts its money to after-tax money and shows where the yardstick differs from the
pre-tax one. Everything is synthetic; every parameter is in data/tax_params.json with a
source and a confidence (A/B/C or no_source).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = ("PR", "CORE", "FULL")


def load_params() -> dict:
    return json.loads((HERE / "data" / "tax_params.json").read_text(encoding="utf-8"))


def rate_for(P: dict, fy: str, country: str = "JP") -> float:
    """Effective rate for the fiscal year (the last known year carries forward)."""
    years = P["by_country"][country]
    if fy in years:
        return years[fy]["rate"]
    return years[sorted(years)[-1]]["rate"]


def declining_balance(cost: float, years: int, rate: float, guarantee: float, revised: float) -> list[float]:
    """200% declining balance as the Japanese 定率法: rate on the remaining balance until the
    year's charge falls below cost × guarantee, then the revised rate on that balance spread
    evenly to the end. Whole years, no monthly proration (see params.simplification)."""
    out, bal, floor = [], cost, cost * guarantee
    switched_base = None
    for y in range(years):
        if switched_base is None:
            d = bal * rate
            if d < floor:
                switched_base = bal
                d = switched_base * revised
        else:
            d = switched_base * revised
        d = bal if y == years - 1 else min(d, bal)   # the last year clears the balance (1 yen memorandum ignored)
        out.append(d)
        bal -= d
    return out


def straight_line(cost: float, years: int) -> list[float]:
    return [cost / years] * years


def pv(flows: list[float], r: float, start_year: int = 0) -> float:
    return sum(f / (1 + r) ** (start_year + i) for i, f in enumerate(flows))


def shield_pv_factor(P: dict, r: float, asset: str = "engine") -> float:
    """PV of the depreciation of 1 unit of capital spend, as a share of that unit."""
    d = P["depreciation"][asset]
    sched = declining_balance(1.0, d["years"], d["rate"], d["guarantee_rate"], d["revised_rate"]) if d["method"] == "定率法" else straight_line(1.0, d["years"])
    return pv(sched, r)


# ---------------------------------------------------------------- 1. split
def split_by_fy(b: dict, P: dict, r: float) -> dict:
    """Repair vs capital by fiscal year from the plan rows, the tax shield of each fiscal
    year (repair × rate + depreciation of the capital spend of this and earlier years), the
    after-tax spend, and the PV of the shields including the years past the window."""
    shares = P["repair_vs_capital"]
    d = P["depreciation"]["engine"]
    fys = sorted({row["fy"] for row in b["plan"]})
    idx = {fy: i for i, fy in enumerate(fys)}
    horizon = len(fys) + d["years"]
    rows = {fy: {"fy": fy, "spend": 0.0, "repair": 0.0, "capital": 0.0, "by_ws": {w: 0.0 for w in WS}} for fy in fys}
    for row in b["plan"]:
        ws, fy, cost = row["workscope"], row["fy"], float(row["exp_cost"])
        s = shares.get(ws, shares["FULL"])
        R = rows[fy]
        R["spend"] += cost
        R["repair"] += cost * s["repair"]
        R["capital"] += cost * s["capital"]
        R["by_ws"][ws] = R["by_ws"].get(ws, 0.0) + cost
    dep = [0.0] * horizon                    # tax depreciation by year index
    book = [0.0] * horizon                   # book straight-line (for the DTL estimate)
    for fy, R in rows.items():
        sched = declining_balance(R["capital"], d["years"], d["rate"], d["guarantee_rate"], d["revised_rate"])
        sl = straight_line(R["capital"], d["years"])
        for k, (a, s_) in enumerate(zip(sched, sl)):
            dep[idx[fy] + k] += a
            book[idx[fy] + k] += s_
    out, shield_flows = [], []
    cum_dtl = 0.0
    for i in range(horizon):
        fy = fys[i] if i < len(fys) else f"FY{int(fys[-1][2:]) + (i - len(fys) + 1)}"
        rate = rate_for(P, fy)
        R = rows.get(fy, {"spend": 0.0, "repair": 0.0, "capital": 0.0, "by_ws": {}})
        shield = (R["repair"] + dep[i]) * rate
        cum_dtl += (dep[i] - book[i]) * rate
        shield_flows.append(shield)
        out.append({"fy": fy, "in_window": i < len(fys), "rate": rate, "spend": R["spend"], "repair": R["repair"], "capital": R["capital"],
                    "by_ws": R["by_ws"], "depreciation": dep[i], "deductible": R["repair"] + dep[i], "shield": shield,
                    "after_tax": R["spend"] - shield, "dtl": cum_dtl})
    window = [x for x in out if x["in_window"]]
    tot_spend = sum(x["spend"] for x in window)
    return {"rows": out, "window": window,
            "total_spend_k": tot_spend, "total_repair_k": sum(x["repair"] for x in window), "total_capital_k": sum(x["capital"] for x in window),
            "shield_in_window_k": sum(x["shield"] for x in window), "shield_total_k": sum(shield_flows),
            "shield_pv_k": pv(shield_flows, r), "after_tax_in_window_k": tot_spend - sum(x["shield"] for x in window),
            "after_tax_pv_k": tot_spend - pv(shield_flows, r),
            "shares": {w: shares[w] for w in WS}, "shield_factor_capital": shield_pv_factor(P, r),
            "dtl_end_of_window_k": window[-1]["dtl"] if window else 0.0}


# ---------------------------------------------------------------- 2. shift
def shift_of(deltas: dict | None, P: dict, r: float) -> dict | None:
    """The backlog case 'external TAT one month longer': spend that moves between fiscal
    years, and what that does after tax (the deduction moves with it) and to the timing
    of the tax payment: rate × moved × (1 − 1/(1+r))."""
    if not deltas:
        return None
    ans = [a for a in deltas["answers"] if a["feasible"] and a["delta"] and "TAT" in a["question"] and a["case"] == "backlog"]
    if not ans:
        ans = [a for a in deltas["answers"] if a["feasible"] and a["delta"] and "TAT" in a["question"]]
    if not ans:
        return None
    a = ans[0]
    rows = []
    for fy, v in sorted(a["delta"]["by_fiscal_year"].items()):
        rate = rate_for(P, fy)
        rows.append({"fy": fy, "spend": v["spend"], "visits": v.get("visits", 0), "after_tax": v["spend"] * (1 - rate), "tax_effect": -v["spend"] * rate})
    moved = sum(max(0.0, x["spend"]) for x in rows)
    rate = rate_for(P, rows[0]["fy"]) if rows else 0.0
    return {"question": a["question"], "case": a["case"], "rows": rows, "moved_k": moved,
            "pre_tax_delta_k": sum(x["spend"] for x in rows), "after_tax_delta_k": sum(x["after_tax"] for x in rows),
            "timing_value_k": rate * moved * (1 - 1 / (1 + r)),
            "note": "費用が後の年度に移れば損金も移る。税額は変わらず、納税が 1 年遅れる分の時間価値だけが差になる"}


# ---------------------------------------------------------------- 3. spares
def spares_of(fleet: dict, P: dict, r: float) -> dict:
    """One spare engine: buy (depreciate, keep the tax book value as residual) vs long-term
    lease vs short-term lease, after-tax PV over 2 and 10 years."""
    price = P["spares"]["engine_value_k"]
    d = P["depreciation"]["engine"]
    sched = declining_balance(price, d["years"], d["rate"], d["guarantee_rate"], d["revised_rate"])
    long_m = fleet["long_term_spare"]["cost_per_month"]
    short_m = fleet["short_term_lease"]["cost_per_month"]
    rows = []
    for years in (2, 10):
        rate = [rate_for(P, f"FY{2026 + y}") for y in range(years)]
        shield = pv([sched[y] * rate[y] for y in range(years)], r)
        residual = price - sum(sched[:years])
        buy = price - shield - residual / (1 + r) ** years
        lease = {}
        for key, m in (("long", long_m), ("short", short_m)):
            pre = pv([m * 12] * years, r)
            post = pv([m * 12 * (1 - rate[y]) for y in range(years)], r)
            lease[key] = {"pre_tax_pv": pre, "after_tax_pv": post, "per_month": m}
        cands = {"buy": buy, "long": lease["long"]["after_tax_pv"], "short": lease["short"]["after_tax_pv"]}
        rows.append({"years": years, "buy": {"price": price, "shield_pv": shield, "residual_pv": residual / (1 + r) ** years, "after_tax_pv": buy,
                                             "pre_tax_pv": price - residual / (1 + r) ** years},
                     "long": lease["long"], "short": lease["short"], "best": min(cands, key=cands.get)})
    return {"rows": rows, "price_k": price, "long_per_month": long_m, "short_per_month": short_m,
            "note": "購入は税務簿価で期末に売れる（売却損益なし）と置く。リース料は当期の損金。判断は保有か借りるかの物差しであって、税のために保有する話ではない"}


# ---------------------------------------------------------------- 4. invest
def invest_of(invest: dict | None, P: dict, r: float) -> dict | None:
    """The domestic-shop policies of invest.py (M$): the after-tax NPV with depreciation
    shields on the capex, and the subsidy either taxed on receipt or deferred by 圧縮記帳."""
    src = invest
    if not src or not src.get("policies"):
        li = json.loads((HERE / "data" / "leap_invest.json").read_text(encoding="utf-8"))
        src = {"policies": [{"id": s["id"], "label": s["label"], "capex": sum(s["capex"]) / 2, "npv": None, "parts": {"capex": -sum(s["capex"]) / 2}} for s in li["stages"]],
               "from_stages": True}
    split = P["depreciation"]["capex_split"]
    fb, fm = shield_pv_factor(P, r, "shop_building"), shield_pv_factor(P, r, "shop_machinery")
    f_dep = split["building"] * fb + split["machinery"] * fm
    share = P["subsidy"]["share_assumed"]
    rows = []
    for p in src["policies"]:
        capex = float(p.get("capex") or 0.0) * 1000.0                 # M$ -> k$
        if capex <= 0:
            continue
        rate = rate_for(P, "FY2027")
        capex_pv = float((p.get("parts") or {}).get("capex", -p.get("capex", 0.0))) * 1000.0
        npv = None if p.get("npv") is None else float(p["npv"]) * 1000.0
        ops_pv = None if npv is None else npv - capex_pv
        shield = -capex_pv * rate * f_dep                               # PV of the depreciation shield, on the PV'd capex
        sub = -capex_pv * share
        taxed = {"tax_on_subsidy": sub * rate, "lost_shield": 0.0}
        compressed = {"tax_on_subsidy": 0.0, "lost_shield": sub * rate * f_dep}
        base = None if ops_pv is None else ops_pv * (1 - rate) + capex_pv + shield
        rows.append({"id": p["id"], "label": p["label"], "capex_k": capex, "capex_pv_k": capex_pv, "npv_pre_tax_k": npv,
                     "shield_pv_k": shield, "subsidy_k": sub,
                     "after_tax_no_subsidy_k": base,
                     "after_tax_subsidy_taxed_k": None if base is None else base + sub - taxed["tax_on_subsidy"],
                     "after_tax_subsidy_compressed_k": None if base is None else base + sub - compressed["lost_shield"],
                     "compression_gain_k": taxed["tax_on_subsidy"] - compressed["lost_shield"]})
    return {"rows": rows, "subsidy_share": share, "shield_factor": f_dep, "from_stages": src.get("from_stages", False),
            "note": "税引後 NPV ＝ 営業の現在価値 ×(1−税率) − 投資 ＋ 償却の盾。補助金は受け取り時に課税（益金）か、圧縮記帳で取得価額を減らして償却の盾を失う代わりに課税を繰り延べる。差は時間価値だけ"}


# ---------------------------------------------------------------- 5. shops
def shops_of(P: dict, r: float) -> dict:
    """The five shop archetypes of data/shop_quotes.json at effective after-tax cost per
    FULL visit: quote + transport + non-deductible customs/VAT (0) + expected delay cost −
    PV of the tax shield. Sorted; it ranks the yardstick, not the shop choice."""
    Q = json.loads((HERE / "data" / "shop_quotes.json").read_text(encoding="utf-8"))
    ws = P["shops"]["reference_workscope"]
    lease = P["shops"]["aog_lease_k_per_month"]
    s = P["repair_vs_capital"][ws]
    f_dep = shield_pv_factor(P, r)
    rate = rate_for(P, "FY2027")
    rows = []
    for sh in Q["shops"]:
        q = sh["quotes"].get(ws)
        if not q:
            rows.append({"id": sh["id"], "name": sh["name"], "has_quote": False, "workscopes": list(sh["quotes"])})
            continue
        dl = sh["delay"]
        exp_delay = sum(m * p for m, p in zip(dl["shop_months"], dl["shop_probs"])) + sum(m * p for m, p in zip(dl["engine_months"], dl["engine_probs"]))
        off_wing = q["tat"] + 2 * sh["transport_months"] + exp_delay
        rows.append({"id": sh["id"], "name": sh["name"], "has_quote": True, "currency": sh["currency"], "quote": q["price"], "tat": q["tat"],
                     "transport": sh["transport_cost"], "transport_months": sh["transport_months"], "exp_delay_months": exp_delay, "off_wing_months": off_wing})
    quoted = [x for x in rows if x["has_quote"]]
    base_off = min(x["off_wing_months"] for x in quoted)
    for x in quoted:
        x["extra_months"] = x["off_wing_months"] - base_off
        x["delay_cost"] = x["extra_months"] * lease
        x["customs_vat"] = 0.0
        work = x["quote"] + x["transport"]
        x["shield_pv"] = rate * (work * s["repair"] + work * s["capital"] * f_dep + x["delay_cost"])
        x["pre_tax"] = work + x["customs_vat"] + x["delay_cost"]
        x["effective"] = x["pre_tax"] - x["shield_pv"]
    quoted.sort(key=lambda x: x["effective"])
    for i, x in enumerate(quoted):
        x["rank"] = i + 1
    return {"rows": quoted, "no_quote": [x for x in rows if not x["has_quote"]], "workscope": ws, "lease_per_month": lease, "base_off_wing_months": base_off,
            "rate": rate, "shield_factor_capital": f_dep,
            "note": "関税は修繕のための輸出・再輸入の減税と民間航空機協定で 0、輸入消費税は仕入税額控除で中立（0）。翼を離れる期間の差は短期リース料で値付け。税引後にしても順位は税引前とほぼ同じ＝税は工場を選ぶ理由にならない"}


# ---------------------------------------------------------------- build
def build(b: dict, fleet: dict, deltas: dict | None, invest: dict | None, shop_quotes: dict | None = None) -> dict:
    P = load_params()
    r = P["discount_rate"]
    split = split_by_fy(b, P, r)
    shift = shift_of(deltas, P, r)
    spares = spares_of(fleet, P, r)
    inv = invest_of(invest, P, r)
    shops = shops_of(P, r)
    jp = P["by_country"]["JP"]
    params = {"discount_rate": r, "discount_rate_source": P["discount_rate_source"],
              "rates": {fy: {"rate": v["rate"], "corporate": v["corporate_effective_rate"], "defense_add": v["defense_surtax"]["effective_add"],
                             "sources": [v["corporate_effective_rate_source"], {"source": v["defense_surtax"]["source"], "confidence": v["defense_surtax"]["confidence"]}]}
                        for fy, v in jp.items()},
              "depreciation": {k: {kk: vv for kk, vv in v.items()} for k, v in P["depreciation"].items() if isinstance(v, dict)},
              "depreciation_simplification": P["depreciation"]["simplification"],
              "repair_vs_capital": P["repair_vs_capital"], "customs": P["customs"], "subsidy": P["subsidy"], "deferred_tax": P["deferred_tax"],
              "spares": P["spares"], "shops": P["shops"]}
    return {"split": split, "shift": shift, "spares": spares, "invest": inv, "shops": shops, "params": params, "observe": P["observe"], "note": P["note"]}


if __name__ == "__main__":
    import sys
    bp = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "baselines" / "jal-2026-10.json"
    b = json.loads(bp.read_text(encoding="utf-8"))
    fleet = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))
    print(json.dumps(build(b, fleet, None, None), ensure_ascii=False, indent=1, default=float)[:4000])
