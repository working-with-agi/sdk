#!/usr/bin/env python3
"""The 729 route-capacity plans scored the way the government scores an airport project.

The MLIT manual (空港整備事業の費用対効果分析マニュアル Ver.5, 令和 8 年 3 月) counts:
  user benefit      consumer surplus by the rule of a half on each OD route,
                    UB = 1/2 (Q0 + Q1)(C0 - C1). Two parts here:
                    frequency   the generalized cost falls with more flights: C0 - C1 = A ln(F1 / F0),
                                A = 3,461 yen (2004 prices, the manual's 式 5.8), F = round trips a day on
                                the route (all carriers), Q = passengers on the route (all carriers)
                    converted   passengers who could not fly before and now do (the manual's 転換分, there
                                valued by the time saved against the other mode; here, no_source, by the
                                fare x a surplus share 0.25 / 0.45 / 0.70 as in route_optimize.py)
  supplier benefit  the airport manager's revenue increase (landing and navigation fees): per movement,
                    derived from the Fukuoka runway project's 12 oku a year for about 24,000 more
                    movements (MLIT 2014): about 50,000 yen a movement, at both ends of the route
                    (no_source as a transfer to Haneda). Airline profit: left out, as the manual does
                    (no excess profit under competition); shown as a variant.
  period, discount  construction + 50 years, 4 % (annuity 21.48 for 50 years; construction time and
                    residual value left out)
  B/C               present value of the benefits / the airport capital

Public reference: the Fukuoka second runway (1,643 oku): user benefit 218 (converted) + 32 (more
flights) and supplier 12 oku a year at the peak year (MLIT 2014 project sheet), B/C 2.7 (2014).
That project serves all of Fukuoka's routes and international; this model sees only the Haneda trunk.

  python bc_mlit.py      # fleet/bc_mlit_jal.json from fleet/route_opt*/ grids
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import airport_slots as ap
import capacity_scenarios as cs
import carbon_scenarios as cb
import route_fleet as rf
import route_growth as rg

HERE = Path(__file__).resolve().parent
A_FREQ = 3461.0                 # yen per passenger per unit of ln(frequency ratio), MLIT manual 式 5.8 (2004 prices)
FEE_PER_MOVEMENT = 50000.0      # yen: Fukuoka runway 12 oku a year / about 24,000 more movements (MLIT 2014 sheet, 16.4 -> 18.8 万回)
YEARS, RATE = 50, 0.04
SURPLUS = (0.0, 0.25, 0.45, 0.70)
GRIDS = (("before", "distance", 0.0, "fleet/route_opt"), ("after_66_rule", "distance", 0.0, "fleet/route_opt"),
         ("before", "fitted", 0.0, "fleet/route_opt"), ("after_66_rule", "fitted", 0.0, "fleet/route_opt"),
         ("before", "distance", 0.5, "fleet/route_opt_rc50"), ("after_66_rule", "distance", 0.5, "fleet/route_opt_rc50"))


def annuity(rate: float = RATE, years: int = YEARS) -> float:
    return (1 - (1 + rate) ** -years) / rate


def base_market(world: str, fares: str, recapture: float) -> dict:
    """Passengers and round trips a day on each trunk route, all carriers, in the plan's base world."""
    old = (rf.FARE_MODE, rf.RECAPTURE)
    rf.FARE_MODE, rf.RECAPTURE = fares, recapture
    try:
        S = ap.load(); K = cb.load()
        cur = {c: ap.current_freq(S, c) for c in ("jal", "ana")}
        oth = ap.others_freq(S)
        big = {r: cur["jal"][r] + cur["ana"][r] for r in oth}
        s_ab = {r: big[r] / (big[r] + oth[r]) for r in oth}
        base = {}
        for c in ("jal", "ana"):
            s = cs.setup(c); w = rg.world_of(S, c, world)
            free = rg.solve(s, S, w, {}, {}, 3, K)
            lock = {r: free["round_trips"][r] for r in ap.HUB_ROUTES}
            base[c] = rg.solve(s, S, w, {}, {}, 3, K, lock)
        q0 = {r: (base["jal"]["carried_by_route_pax_k"][r] + base["ana"]["carried_by_route_pax_k"][r]) / s_ab[r] for r in oth}
        f0 = {r: (base["jal"]["round_trips"][r] + base["ana"]["round_trips"][r]) / s_ab[r] for r in oth}
        return {"q0_pax_k": q0, "f0_round_trips": f0}
    finally:
        rf.FARE_MODE, rf.RECAPTURE = old


def score(row: dict, m: dict, fare: dict, surplus: float, airline: bool = False) -> dict:
    ann = annuity()
    freq = conv = 0.0
    trips = {rg.ROUTE[k]: v for k, v in row["market_round_trips"].items()}
    for r, add in trips.items():
        if add <= 0:
            continue
        f0 = m["f0_round_trips"][r]; q0 = m["q0_pax_k"][r] * 1e3; q1 = q0 + row["new_pax_by_route_k"][r] * 1e3
        freq += 0.5 * (q0 + q1) * A_FREQ * math.log((f0 + add) / f0) / 1e8
    conv = sum(max(0.0, v) * 1e3 * fare[r] for r, v in row["new_pax_by_route_k"].items()) * surplus / 1e8
    fees = sum(trips.values()) * 4 * 365 * FEE_PER_MOVEMENT / 1e8          # 2 movements at each end per round trip
    air = (row["margin_change_oku"]["jal"] + row["margin_change_oku"]["ana"]) if airline else 0.0
    annual = freq + conv + fees + air
    pv = annual * ann
    cap = row["capital_oku"]
    return {"annual_oku": {"frequency": round(freq, 1), "converted": round(conv, 1), "airport_fees": round(fees, 1), "airline": round(air, 1), "total": round(annual, 1)},
            "pv_benefit_oku": round(pv, 0), "capital_oku": cap, "npv_oku": round(pv - cap, 0), "bc": round(pv / cap, 2) if cap else None}


def plan_text(p: dict) -> str:
    APT = {"CTS": "新千歳", "FUK": "福岡", "OKA": "那覇"}
    parts = [f"{APT[c]} A+{p['jal'].get(c, 0)}・B+{p['ana'].get(c, 0)}" for c in ("CTS", "FUK", "OKA") if p["jal"].get(c) or p["ana"].get(c)]
    return "、".join(parts) or "足さない"


def build(out: Path | None = None, log=print) -> dict:
    res = {}
    for world, fares, rc, d in GRIDS:
        p = HERE / d / f"{world}_{fares}.json"
        if not p.exists():
            continue
        g = json.loads(p.read_text(encoding="utf-8"))
        m = base_market(world, fares, rc)
        fare = g["fare_yen"]
        key = f"{world}/{fares}/rc{round(rc * 100)}"
        out_k = {"base_market": {k: {r: round(v, 1) for r, v in x.items()} for k, x in m.items()}, "by_surplus": {}}
        for sv in SURPLUS:
            scored = [(r, score(r, m, fare, sv)) for r in g["rows"]]
            best = max(scored, key=lambda x: x[1]["npv_oku"])
            pos = [x for x in scored if x[1]["npv_oku"] > 0]
            singles = {}
            for code in ("CTS", "FUK", "OKA"):
                one = [x for x in scored if set(x[0]["plan"]["jal"]) | set(x[0]["plan"]["ana"]) == {code}]
                if one:
                    b1 = max(one, key=lambda x: x[1]["npv_oku"])
                    singles[code] = {"plan": plan_text(b1[0]["plan"]), **b1[1]}
            with_air = max(((r, score(r, m, fare, sv, airline=True)) for r in g["rows"]), key=lambda x: x[1]["npv_oku"])
            out_k["by_surplus"][str(sv)] = {"best": {"plan": plan_text(best[0]["plan"]), "new_pax_k": best[0]["new_pax_k"], "margin_change_oku": best[0]["margin_change_oku"], **best[1]},
                                            "n_npv_positive": len(pos), "best_single_route": singles,
                                            "best_with_airline": {"plan": plan_text(with_air[0]["plan"]), **with_air[1]}}
        res[key] = out_k
        log(f"  {key}: " + "; ".join(f"{sv}: {v['best']['plan']} B/C {v['best']['bc']}" for sv, v in out_k["by_surplus"].items()))
    d = {"results": res, "params": {"A_frequency_yen": A_FREQ, "fee_per_movement_yen": FEE_PER_MOVEMENT, "years": YEARS, "rate": RATE, "annuity": round(annuity(), 2), "surplus_shares": SURPLUS},
         "public_reference": {"fukuoka_runway_2014": {"cost_oku": 1643, "user_benefit_peak_oku_per_year": {"converted": 218, "more_flights": 32}, "supplier_benefit_peak_oku_per_year": 12, "bc": 2.7,
                                                      "source": "https://www.mlit.go.jp/tec/hyouka/public/jghks/karute/img/2014/12/14111289001/14111289001_1.pdf（便益は最大便益の年度・割引前）。B/C 2.7 は https://www.nikkei.com/article/DGXLASFS11H57_R11C14A2PP8000/。令和元年度の再評価で 2.0（二次情報）"},
                              "naha_runway": {"bc": 4.1, "source": "data/airport_investment.json"},
                              "manual": "https://www.mlit.go.jp/koku/content/001992156.pdf（Ver.5、令和 8 年 3 月：利用者便益は消費者余剰〔式 5.1〕、運航頻度の便益〔式 5.8、A = 3,461 円〕、供給者便益は空港管理者の収益増が中心、エアラインの供給者便益は超過利潤がなければ無視できる〔5.2.2（4）〕、評価期間は建設期間＋50 年、社会的割引率 4%）"},
         "how": "729 計画（route_optimize.py の格子）を国の物差しで採点し直す。年の便益 ＝ 運航頻度の便益 ＋ 乗れなかった旅客が乗れる便益（転換分に当たる、運賃 × 割合、no_source）＋ 空港の着陸料等（1 回 5 万円 × 両端の発着）。航空会社の利益は入れない（入れた場合も best_with_airline に出す）。50 年・4% で現在価値にし、空港の事業費と比べる（B/C、純現在価値）",
         "caveat": "運航頻度の便益の原単位は 2004 年度価格のまま。路線の旅客と便数（全社）は、両社の解を両社の合計の取り分で割った近似。需要は FY2030 で 50 年一定（伸び・人口減は入れていない）。建設期間と残存価値は入れていない。着陸料等の原単位は福岡の事業の値を羽田にも当てた（no_source）"}
    out = out or HERE / "fleet" / "bc_mlit_jal.json"
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"wrote {out}")
    return d


if __name__ == "__main__":
    build()
