#!/usr/bin/env python3
"""Where to add airport capacity, what it costs, and what comes back to one airline.

The capacity scenarios (capacity_scenarios.py) showed that lifting the hub's trunk slots pays
only as far as the airports at the other end can take the flights. This module puts prices on
both ends with the public cost of recent runway projects (data/airport_investment.json):

  cost per round trip a day   a project's cost / (movements added a year / 730)
                              Haneda: the D runway; Fukuoka: its second runway; Naha: its second
                              runway; New Chitose has grown by changing operations, not building
                              (lower bound 0, upper bound the Fukuoka runway); Itami cannot grow
  options                     hub +n round trips, with the destinations as they are or with
                              their headroom raised (an expansion there)
  the airline's side          the margin gained a year (revenue - operating cost, p50, the trunk
                              fleet assignment re-solved), the round trips it actually adds at
                              each airport, the cost those round trips stand for (its share of
                              the projects), the present value over 30 years at 4 % and the
                              payback in years; and the engines (cycles move to the 737 / 767)

The cost is what the capacity the airline uses stands for, not what it pays (the state builds,
the airlines pay through landing fees). The margin is before aircraft ownership and overhead, and
it is held at the first year's value (growth would raise it). Everything is synthetic or public
and flagged.

  python investment_scenarios.py jal --out fleet/investment_jal.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import airport_slots as ap
import capacity_scenarios as cs

HERE = Path(__file__).resolve().parent
INVEST = HERE / "data" / "airport_investment.json"
ROUTE_AIRPORT = {"HND-CTS": "CTS", "HND-ITM": "ITM", "HND-FUK": "FUK", "HND-OKA": "OKA"}
OPTIONS = (
    {"id": "hnd12", "label": "羽田 +12 往復（対向空港の今の余地に収まる）", "delta": 12, "extra": {}},
    {"id": "hnd20", "label": "羽田 +20 往復（対向空港はそのまま）", "delta": 20, "extra": {}},
    {"id": "hnd20_cts_fuk", "label": "羽田 +20 往復 ＋ 新千歳・福岡 各 +4 往復", "delta": 20, "extra": {"CTS": 4, "FUK": 4}},
    {"id": "hnd30_cts_fuk_oka", "label": "羽田 +30 往復 ＋ 新千歳・福岡 各 +6、那覇 +4 往復", "delta": 30, "extra": {"CTS": 6, "FUK": 6, "OKA": 4}},
    {"id": "hnd20_open", "label": "羽田 +20 往復、対向空港の上限なし（参考）", "delta": 20, "extra": None},
)


def load() -> dict:
    return json.loads(INVEST.read_text(encoding="utf-8"))


def cost_per_round_trip(inv: dict) -> dict:
    """億円 per round trip a day of capacity, by project."""
    out = {}
    for k, p in inv["projects"].items():
        if p.get("movements_before") and p.get("movements_after"):
            rt = (p["movements_after"] - p["movements_before"]) / 730
            out[k] = round(p["cost_oku"] / rt, 1)
    return out


def unit_costs(inv: dict) -> dict:
    """The cost range (億円 per round trip a day) used at each airport."""
    c = cost_per_round_trip(inv)
    return {"HND": (c["HND_D"], c["HND_D"]), "CTS": (0.0, c["FUK_2"]), "FUK": (c["FUK_2"], c["FUK_2"]), "OKA": (c["OKA_2"], c["OKA_2"]), "ITM": (None, None)}


def annuity(rate: float, years: int) -> float:
    return (1 - (1 + rate) ** -years) / rate


def build(cid: str, out: Path | None = None, years_ahead: int = 3, options: tuple = OPTIONS, log=print) -> dict:
    inv = load()
    unit = unit_costs(inv)
    A = annuity(inv["appraisal"]["discount_rate"], inv["appraisal"]["years"])
    s = cs.setup(cid)
    t0 = time.time()
    base = cs.run(s, years_ahead, dest=True)
    hub0 = base["version_round_trips"]
    rows = []
    for o in options:
        r = cs.run(s, years_ahead, delta=o["delta"], dest=(o["extra"] if o["extra"] else True) if o["extra"] is not None else False)
        rt = r["version_round_trips"]
        added = {"HND": round(sum(rt[x] - hub0[x] for x in ap.HUB_ROUTES), 1)}
        for route, code in ROUTE_AIRPORT.items():
            added[code] = round(rt[route] - hub0[route], 1)
        # the cost the added round trips stand for: all of them at the hub; at a destination only
        # those beyond today's headroom (the expansion there), capped at the expansion's size
        dest = ap.load_destinations()["airports"]
        caps0 = ap.destination_caps(ap.load(), cid)
        over = {}
        for route, code in ROUTE_AIRPORT.items():
            beyond = max(0.0, rt[route] - caps0[route])
            if o["extra"]:
                beyond = min(beyond, o["extra"].get(code, 0))
            over[code] = round(beyond, 1)
        lo = added["HND"] * unit["HND"][0] + sum(over[c] * (unit[c][0] or 0) for c in over)
        hi = added["HND"] * unit["HND"][1] + sum(over[c] * (unit[c][1] or 0) for c in over)
        gain = round(r["margin_oku"] - base["margin_oku"], 1)
        d_demand = round(r["demand_pax_k"] - base["demand_pax_k"], 1)          # the company's demand rises with its frequency share (from the other carriers)
        d_spill = round(r["spill_pax_k"] - base["spill_pax_k"], 1)             # its own passengers left behind (negative = more of them now fly)
        eng = {e["type"]: e for e in r["engines"]}
        eng0 = {e["type"]: e for e in base["engines"]}
        rows.append({"id": o["id"], "label": o["label"], "delta_round_trips": o["delta"], "destination_extra": o["extra"],
                     "round_trips": rt, "added_round_trips": added, "beyond_today_headroom": over, "unusable_round_trips": r["unusable_round_trips"],
                     "gain_oku_per_year": gain,
                     "pax_k": {"added": round(r["carried_pax_k"] - base["carried_pax_k"], 1), "from_share": d_demand, "from_own_spill": round(-d_spill, 1)}, "gain_per_added_round_trip_oku": round(gain / added["HND"], 1) if added["HND"] else None,
                     "cost_share_oku": [round(lo), round(hi)],
                     "npv_oku": [round(gain * A - hi), round(gain * A - lo)],
                     "payback_years": [round(lo / gain, 1) if gain > 0 else None, round(hi / gain, 1) if gain > 0 else None],
                     "carried_pax_k": r["carried_pax_k"], "spill_pax_k": r["spill_pax_k"],
                     "engines": {t: {"utilisation_multiplier": eng[t].get("utilisation_multiplier"), "spend_per_year_oku_yen": eng[t].get("spend_per_year_oku_yen"),
                                     "spend_change_oku": round((eng[t].get("spend_per_year_oku_yen") or 0) - (eng0[t].get("spend_per_year_oku_yen") or 0), 1)}
                                 for t in ("737", "767", "787") if t in eng}})
        if log:
            log(f"  [{time.time() - t0:4.0f}s] {o['id']}: gain {gain} 億円/年, cost share {round(lo)}–{round(hi)} 億円")
    result = {"company": cid, "fiscal_year": cs.fy_after(s["fy"], years_ahead), "base_margin_oku": base["margin_oku"], "base_round_trips": hub0,
              "unit_cost_oku_per_round_trip_day": {k: list(v) for k, v in unit.items()}, "project_cost_per_round_trip_day": cost_per_round_trip(inv),
              "annuity_factor": round(A, 2), "rows": rows,
              "assumptions": {"cost": "空港ごとの 1 日 1 往復あたりの費用。羽田は D 滑走路、福岡は第 2 滑走路、那覇は第 2 滑走路の事業費 ÷ 増えた容量。新千歳は運用の見直しで増やしてきたので下限 0、上限は福岡の滑走路。伊丹は増やせない",
                              "share": "会社が使う分（羽田で増えた往復のすべて、対向空港では今の余地を超えた分）に 1 往復あたりの費用を掛けた額。誰が払うかではなく、使う容量が表す費用",
                              "gain": "その年度の差し引き（売上 − 運航費、p50）の増分を 30 年同じとして、割引率 4% で現在価値にする。機体の所有費・本社費・着陸料は引いていない",
                              "split": "増えた旅客 ＝ 自社の需要の増分（便数の取り分が増えて他社から移る旅客）− 乗れない旅客の増分。後者が負なら、乗れなかった自社の旅客を運べた分。他社の便と乗れない旅客はモデルの外なので、移った旅客のうち他社で乗れなかった人（社会の側の増分）は分けられない",
                              "source": "data/airport_investment.json"},
              "note": "数値は合成データと公開値の混合。p50"}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("company")
    a.add_argument("--out", type=Path)
    args = a.parse_args(argv)
    r = build(args.company, args.out)
    print(f"{r['fiscal_year']} base margin {r['base_margin_oku']}, unit cost {r['unit_cost_oku_per_round_trip_day']}, annuity {r['annuity_factor']}")
    for x in r["rows"]:
        print(f" {x['id']}: pax {x['pax_k']}")
        print(f" {x['id']}: gain {x['gain_oku_per_year']}/yr ({x['gain_per_added_round_trip_oku']}/rt) added {x['added_round_trips']} beyond {x['beyond_today_headroom']} unusable {x['unusable_round_trips']} cost {x['cost_share_oku']} npv {x['npv_oku']} payback {x['payback_years']} engines {x['engines']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
