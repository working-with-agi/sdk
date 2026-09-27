"""Money mechanisms around the plan: prepayment, tax timing, balance sheet, and the
arrangements only a very large carrier can use (alliance pools, volume tiers, group MRO,
escalation caps, no-reserve leases).

None of these change *which* engine goes in when. They change what the same plan costs,
when the cash leaves, and what sits on the balance sheet. Each item is priced with a simple
formula on the frozen baseline, with its assumption and a flag when a tax adviser must
confirm it. Everything is synthetic; parameters and sources are in data/finance.json.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_params() -> dict:
    return json.loads((HERE / "data" / "finance.json").read_text(encoding="utf-8"))


def npv_factor(rate: float, years: float) -> float:
    return 1.0 / (1.0 + rate) ** years


def build(b: dict, fleet: dict, cfg: dict | None, invest: dict | None, deltas: dict | None = None) -> dict:
    P = load_params()
    r, tax = P["discount_rate"], P["tax_rate"]
    pr = b["plan_of_record"]
    spend = pr["total_cost"]                       # k$ over the 2-year window
    committed = pr.get("committed", spend * 0.83)
    visits = pr["shop_visits"]
    owned = fleet["owned_engines"]
    buffer = fleet["buffer_spares"][0]
    long_cost = fleet["long_term_spare"]["cost_per_month"]
    leased_ac = (cfg or {}).get("aircraft", {}).get("leased", 0) if cfg else 0
    items = []

    def add(key, name, kind, effect, cash=0.0, balance=0.0, large=False, review=False, what="", how="", conf="C"):
        items.append({"key": key, "name": name, "kind": kind, "effect_k": float(effect), "cash_k": float(cash), "balance_k": float(balance),
                      "large_only": large, "needs_tax_review": review, "what": what, "how": how, "confidence": conf})

    # 1. prepayment discount: quotes paid ahead at a discount, financed at the discount rate
    d, ahead = P["prepay"]["discount"], P["prepay"]["months_ahead"]
    disc = committed * d
    fin = committed * (1 - npv_factor(r, ahead / 12))
    add("prepay", "前払い割引", "資金", -(disc - fin), cash=-committed * ahead / 24, what=f"見積もり額の {d:.0%} 引きと引き換えに、平均 {ahead} か月早く払う",
        how=f"割引 {disc:,.0f} − 早払いの金利 {fin:,.0f}（年 {r:.0%}）", conf="B")

    # 2. tax timing: PBH-style monthly payments are deducted as flown; T&M lumps at induction.
    #    A deferral, not a saving: the value is the time value of the earlier deduction.
    shift = P["tax_timing"]["months_earlier"]
    add("tax_timing", "損金の期ズレ（時間課金型 vs 都度払い）", "税・会計", -tax * spend * (1 - npv_factor(r, shift / 12)),
        review=True, what=f"時間課金型は飛行のたびに損金、都度払いは入場時。平均 {shift} か月早く落ちる分の時間価値",
        how=f"税率 {tax:.1%} × 費用 {spend:,.0f} × 早まる分の割引差。税額は減らない（繰延）", conf="C")

    # 3. consumption tax / customs on overseas repair: neutral, listed so nobody looks for it
    add("vat_customs", "消費税・関税（海外修理）", "税・会計", 0.0, review=True,
        what="海外工場での修理は消費税の課税対象外、国内は課税だが仕入税額控除で中立。修理のための輸出入は再輸入減税（関税定率法 11 条）",
        how="損得なし。前提として置かない", conf="B")

    # 4. subsidy on a domestic shop: 圧縮記帳 defers the tax on the grant over the asset life
    if invest and invest.get("subsidy"):
        sub = invest["subsidy"]
        amt = float(sub.get("amount_k") or sub.get("amount") or 0) * (1000 if float(sub.get("amount_k") or sub.get("amount") or 0) < 1000 else 1)
        life = P["subsidy"]["asset_life_years"]
        add("subsidy_deferral", "補助金の圧縮記帳（国内工場）", "税・会計", -tax * amt * (1 - npv_factor(r, life / 2)),
            review=True, what="補助金を資産の取得価額から減らし、補助金への課税を償却期間にわたって繰り延べる",
            how=f"税率 {tax:.1%} × 補助金 {amt:,.0f} × {life} 年償却の時間価値", conf="C")

    # 5. sale-and-leaseback of spare engines: cash in now, lease out later; more expensive over
    #    the window, lighter balance sheet
    n_slb = buffer + pr.get("long_spares", 0)
    price = P["engine_value_k"]
    lease_2y = n_slb * long_cost * 24
    capital = n_slb * price * (1 - npv_factor(r, 2))
    add("slb", "予備エンジンのセール＆リースバック", "資金", lease_2y - capital, cash=n_slb * price, balance=-n_slb * price, large=False,
        what=f"予備 {n_slb} 基（1 基 {price:,.0f} k$）を売って借り戻す。現金が今入り、リース料が出ていく",
        how=f"2 年のリース料 {lease_2y:,.0f} − 資本の機会費用 {capital:,.0f}。費用は増え、資産は軽くなる", conf="B")

    # 6. alliance spare-engine pool: the buffer of n similar operators pooled needs sqrt(n)/n each
    n_pool = P["alliance_pool"]["partners"]
    freed = buffer * (1 - (n_pool ** 0.5) / n_pool)
    add("alliance_pool", "アライアンス共同の予備プール", "規模", -freed * long_cost * 24, large=True,
        what=f"同型機を持つ {n_pool} 社で予備を共有すると、必要な予備は各社 √{n_pool}/{n_pool}", how=f"浮く予備 {freed:.1f} 基 × 保有費 {long_cost} k$/月 × 24", conf="C")

    # 7. volume tier from the OEM: fleet of 100+ engines gets a tier discount on quotes
    tier = P["volume_tier"]["discount_100_engines"] if owned >= 100 else 0.0
    add("volume_tier", "規模による見積もり割引（OEM のティア）", "規模", -committed * tier, large=True,
        what=f"保有 {owned} 基。100 基超のティアで見積もり {tier:.0%} 引き（仮定）", how=f"計画どおり分 {committed:,.0f} × {tier:.0%}", conf="C")

    # 8. group MRO insourcing: a share of light visits done by the group's own shop
    s, ip = P["group_mro"]["insource_share"], P["group_mro"]["internal_price_discount"]
    pr_spend = sum(v.get("PR", 0) for v in pr["by_fiscal_year"].values()) * P["group_mro"]["pr_price_k"]
    add("group_mro", "グループ整備会社への内製（軽作業）", "グループ", -(pr_spend * s * ip + visits * s * 0.4 * P["group_mro"]["transport_k"]), large=True,
        what=f"軽作業（PR）の {s:.0%} をグループの整備会社で、内部価格 {ip:.0%} 引き、輸送なし", how="輸送費と内部価格差。能力と設備投資は「国内工場の新設」で別に評価", conf="C")

    # 9. maintenance reserves on leased aircraft: large carriers negotiate no reserves (LoC instead)
    n_leased_eng = 2 * leased_ac
    bal = n_leased_eng * P["reserves"]["avg_balance_k"]
    add("no_reserves", "リース機の整備積立金を不要に（信用状で代替）", "グループ", -bal * ((1 + r) ** 2 - 1), cash=bal, large=True,
        what=f"リース機 {leased_ac} 機（エンジン {n_leased_eng} 基）の積立金残高 {bal:,.0f} k$ を持たない", how="積立金の金利 2 年分。大手は信用力で積立金なしを取れる", conf="B")

    # 10. escalation cap in a multi-year contract
    mkt, cap = P["escalation"]["market"], P["escalation"]["cap"]
    add("escalation_cap", "複数年契約の値上げ上限", "規模", -committed * max(0.0, (mkt - cap)) * 0.5 * 2, large=True,
        what=f"市場の値上げ {mkt:.0%}/年に対し契約で {cap:.0%}/年に上限", how="2 年の平均差 × 計画どおり分", conf="C")

    # 11. FX: quotes in USD; a natural hedge from USD revenue (international) or forwards
    vol = fleet.get("fx", {}).get("volatility", 0.1)
    add("fx_hedge", "為替の自然ヘッジ・先物", "資金", 0.0, cash=0.0, large=True,
        what=f"見積もりはドル建て（変動 {vol:.0%}）。国際線のドル収入で相殺、残りは先物で固定", how="期待値は変えない。着地の幅（p10〜p90）を狭める", conf="B")

    # the same items priced inside the Monte Carlo (baseline.compare, actions fin_*)
    SIM = {"prepay": "fin_prepay", "volume_tier": "fin_tier", "escalation_cap": "fin_escalation", "alliance_pool": "fin_pool_alliance",
           "group_mro": "fin_group_mro", "fx_hedge": "fin_fx_hedge", "slb": "fin_slb", "no_reserves": "fin_no_reserves"}
    if deltas:
        by_act = {tuple(x["actions"]): x for x in deltas["answers"] if x["feasible"] and x["delta"] and x["case"] == "base"}
        for i in items:
            x = by_act.get((SIM.get(i["key"]),))
            if x:
                i["sim_effect_k"] = x["delta"]["total_cost"]
                i["sim_p90_k"] = x["delta"].get("p90")
                i["sim_aog"] = x["delta"].get("aog_prob")
        pk = by_act.get(("fin_package",))
        package = None if not pk else {"effect_k": pk["delta"]["total_cost"], "p90_k": pk["delta"].get("p90"), "aog": pk["delta"].get("aog_prob"),
                                       "recourse_k": pk["delta"].get("recourse")}
    else:
        package = None
    total = sum(i["effect_k"] for i in items if not i["needs_tax_review"])
    total_large = sum(i["effect_k"] for i in items if i["large_only"] and not i["needs_tax_review"])
    return {"items": items, "total_effect_k": total, "total_large_only_k": total_large, "spend_k": spend, "package_sim": package,
            "params": {"discount_rate": r, "tax_rate": tax}, "note": P["note"]}
