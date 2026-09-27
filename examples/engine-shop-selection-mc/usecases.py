#!/usr/bin/env python3
"""Everyday decisions beyond the plan, for the layered report. Each function answers one
question with a rule the planner can reuse, and returns the curves the report draws.

  quote_approval   how much extra shop work to approve for how much longer on wing
  trend_alert      remove an engine on a trend alert now, or keep flying and watch
  spares           how many spare engines keep the fleet flying, at today's shop times
  offer            the most to pay for an offered green-time engine
  cash             when the money leaves (invoices at induction and return) and FX
  reliability      unscheduled removal rate per 1,000 engine hours against the alert level

The value of on-wing life is the maintenance cost an engine accrues per month it flies
(the normal-state spend over the installed engines): a month more on wing defers that much.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import company
import lifecycle

HERE = Path(__file__).resolve().parent
USD_JPY = 150.0          # no_source: reference rate for the yen view
FX_BAND = 0.10           # +-10 % over a year (the fleet file's FX volatility)
PAY_AT_INDUCTION = 0.3   # no_source: share of a time-and-materials invoice paid at induction


def poisson_cdf(k: int, lam: float) -> float:
    term = math.exp(-lam)
    total = term
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return min(1.0, total)


def build(b: dict) -> dict:
    fleet = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))
    shops = json.loads((HERE / b["paths"]["shops"]).read_text(encoding="utf-8"))["shops"]
    n = b["norms"]
    installed = max(fleet["required_positions"])
    V = n["spend_per_year_k"] / 1000 / (installed * 12)          # M$ per engine-month on wing
    visit_cost = n["spend_per_year_k"] / 1000 / n["visits_per_year"]
    lease = fleet["short_term_lease"]["cost_per_month"] / 1000
    un = fleet["unscheduled_removals"]
    fail_factor, fail_months = un["failure_cost_factor"], un["failure_extra_months"]
    peak = max(float(x) for x in fleet["aog_peak_multiplier"].values())
    aog = fleet["aog_tiers"][0]["cost_per_month"] / 1000
    out = {"value_per_engine_month": V, "visit_cost": visit_cost}

    # 1. quote approval: approve extra work X if it adds more than X / V months on wing
    months = list(range(0, 25))
    out["quote"] = {"months": months, "max_extra_cost": [m * V for m in months],
                    "examples": [{"what": "高圧タービン翼の追加交換（例）", "cost": 0.45, "months": 6},
                                 {"what": "燃焼器ライナーの修理（例）", "cost": 0.20, "months": 1},
                                 {"what": "寿命部品の早め交換で残りをそろえる（例）", "cost": 1.20, "months": 14}],
                    "note": "例の費用と延びる期間は説明用（出典なし）。線より下なら承認が得"}

    # 2. trend alert: keep flying g more months (risk of failure) or remove now (lose g months)
    g = list(range(0, 13))
    cases = {}
    for label, h in (("通常のエンジン", 0.01), ("要監視のエンジン", 0.06)):
        fail_cost = (fail_factor - 1) * visit_cost + fail_months * lease
        wait = [(1 - (1 - h) ** m) * fail_cost for m in g]
        wait_peak = [(1 - (1 - h) ** m) * (fail_cost + 0.5 * aog * peak) for m in g]
        cases[label] = {"wait": wait, "wait_peak": wait_peak}
    out["trend"] = {"months": g, "remove_now": [m * V for m in g], "cases": cases,
                    "note": "今下ろすと失うのは残りの月数分の飛べる寿命。待つと故障の確率 × 故障の追加費用（傷みの拡大 30%＋1 か月長い工期、繁忙期は運休の一部）"}

    # 3. spares: engines off wing at once ~ Poisson(removals per month x months off wing)
    lam = n["visits_per_year"] / 12
    delay = shops[0]["delay"]
    mean_delay = sum(d * p for d, p in zip(delay["shop_months"], delay["shop_probs"]))
    off_now = float(np.mean([r["quoted_off_wing"] for r in b["plan"]])) + mean_delay
    scen = {"平常（工期 4 か月）": 4.0, "今の工期": off_now, "混雑がさらに 2 か月": off_now + 2}
    have = fleet["owned_engines"] - installed
    s_range = list(range(0, 26))
    out["spares"] = {"spares": s_range, "have": have, "rule_10pct": round(0.1 * installed, 1),
                     "curves": {k: [poisson_cdf(s, lam * m) for s in s_range] for k, m in scen.items()},
                     "mean_off": {k: lam * m for k, m in scen.items()},
                     "note": "取卸しは月 {:.1f} 基。翼を離れる期間 × 取卸しの率 が同時に工場側にいる基数の平均（ポアソン）。".format(lam)}

    # 3b. the other side: what each spare costs to hold, against the shortage it avoids.
    # Shortage engine-months are filled by short-term leases up to the market cap, then by
    # cancelling flights (the cheapest AOG tier). Holding a spare costs a long-term lease
    # (or the capital and preservation of an owned one). The best count balances the two.
    hold = fleet["long_term_spare"]["cost_per_month"] / 1000
    cap = fleet["short_term_lease"]["max_engines"]

    def shortage(k: int, mu: float) -> float:
        """E[(X - k)^+] for X ~ Poisson(mu)."""
        tail, p, cdf = 0.0, math.exp(-mu), 0.0
        for x in range(0, int(mu * 4 + 40)):
            if x > 0:
                p *= mu / x
            if x > k:
                tail += (x - k) * p
        return tail
    cost = {}
    for k_, m_ in scen.items():
        mu = lam * m_
        rows = []
        for s_ in s_range:
            leased = shortage(s_, mu) - shortage(s_ + cap, mu)
            cancelled = shortage(s_ + cap, mu)
            rows.append({"hold": 12 * s_ * hold, "lease": 12 * leased * lease, "cancel": 12 * cancelled * aog})
        tot = [r["hold"] + r["lease"] + r["cancel"] for r in rows]
        best = int(np.argmin(tot))
        cost[k_] = {"hold": [r["hold"] for r in rows], "short": [r["lease"] + r["cancel"] for r in rows],
                    "total": tot, "best": best, "at_have": tot[have] if have < len(tot) else None,
                    "excess_cost": (tot[have] - tot[best]) if have < len(tot) else None}
    out["spares"]["cost"] = cost
    out["spares"]["hold_per_month"] = hold
    out["spares"]["lease_out"] = {"per_month": [0.08, 0.09], "source": "IBA 2025：CFM56-7B の中長期リース 80〜90k$/月"}
    out["spares"]["note_cost"] = ("予備 1 基を持つ費用は長期リース 1 か月 {:.0f} 千ドル（自社保有なら資本費・保管・保存整備）。足りない分は短期リース（上限 {} 基）、"
                                  "それでも足りなければ便を止める損（1 基 1 か月 {:.0f} 千ドル〜）").format(hold * 1000, cap, aog * 1000)

    # 4. offer: the most to pay for a green-time engine with R cycles left
    cpm = lifecycle.CYCLES_PER_MONTH if lifecycle.CYCLES_PER_MONTH else 2000 / 12
    cycles = list(range(0, 16001, 1000))
    out["offer"] = {"cycles": cycles, "max_price": [c / cpm * V for c in cycles],
                    "max_price_peak": [c / cpm * V + 3 * lease for c in cycles],
                    "market": {"low": 5.2, "high": 6.8, "cycles": 10000,
                               "source": "IBA 2025：CFM56-7B のハーフライフ価値 5.2〜6.8 百万ドル（型による）"},
                    "note": "上限価格＝残りの飛べる月数 × 1 か月に積もる整備費（自分のエンジンの入場をその分先送りできる）。繁忙期の前に届けば、リース 3 か月分を上乗せ"}

    # 5. cash: invoices at induction and at return, in dollars and in yen
    labels = b["monthly"]["labels"]
    T = len(labels)
    pay = [0.0] * T
    for r in b["plan"]:
        pay[r["t"]] += PAY_AT_INDUCTION * r["exp_cost"] / 1000
        back = r["t"] + r["quoted_off_wing"]
        if back < T:
            pay[back] += (1 - PAY_AT_INDUCTION) * r["exp_cost"] / 1000
    budget_m = []
    for t in range(T):
        fy = b["monthly"]["fy"][t]
        ts = [u for u in range(T) if b["monthly"]["fy"][u] == fy]
        norm = sum(b["monthly"]["norm_spend"][u] for u in ts) or 1
        budget_m.append(b["budgets"].get(fy, 0) / 1000 * b["monthly"]["norm_spend"][t] / norm)
    out["cash"] = {"labels": labels, "pay": pay, "cum": list(np.cumsum(pay)), "cum_budget": list(np.cumsum(budget_m)),
                   "yen_oku": {"mid": sum(pay) * USD_JPY / 100, "low": sum(pay) * USD_JPY * (1 - FX_BAND) / 100,
                               "high": sum(pay) * USD_JPY * (1 + FX_BAND) / 100},
                   "note": f"請求の {int(PAY_AT_INDUCTION * 100)}% を入場時、残りを戻り時に払うと仮定（出典なし）。円換算は 1 ドル {USD_JPY:.0f} 円 ±{int(FX_BAND * 100)}%"}

    # 6. reliability: unscheduled removals per 1,000 engine flight hours, 3-month average
    seed = company.configure_for_fleet(HERE / b["paths"]["fleet"]) or 7
    visits, *_ , Tsim = lifecycle.simulate(seed)
    efh = [lifecycle.needed_positions(t) * lifecycle.CYCLES_PER_MONTH * lifecycle.FLIGHT_INDEX[lifecycle.month_of(t)]
           * lifecycle.HOURS_PER_CYCLE for t in range(Tsim)]
    uer = np.zeros(Tsim)
    svr = np.zeros(Tsim)
    for v in visits:
        svr[v["t"]] += 1
        if v["unscheduled"]:
            uer[v["t"]] += 1
    rate = uer / np.array(efh) * 1000
    ma3 = np.convolve(rate, np.ones(3) / 3, mode="valid")
    base = ma3[lifecycle.WARMUP * 12: -36]
    alert = float(base.mean() + 3 * base.std())
    last = ma3[-36:]
    lab0 = b["monthly"]["labels"][0]
    y0, m0 = map(int, lab0.split("-"))
    lab = [f"{y0 + (m0 - 1 - 36 + i) // 12}-{(m0 - 1 - 36 + i) % 12 + 1:02d}" for i in range(36)]
    out["reliability"] = {"labels": lab, "uer_3m": [float(x) for x in last], "alert": alert, "mean": float(base.mean()),
                          "svr_per_1000": float(svr[lifecycle.WARMUP * 12:].sum() / sum(efh[lifecycle.WARMUP * 12:]) * 1000),
                          "above": int((last > alert).sum()),
                          "note": "予定外取卸し率（1,000 飛行時間あたり）の 3 か月移動平均。警戒値＝過去 12 年の平均＋3 標準偏差（FAA AC 120-17B などの例と同じ作り方）。合成データ"}
    return out
