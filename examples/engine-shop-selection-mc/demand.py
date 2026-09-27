#!/usr/bin/env python3
"""The layer above the engine plan: seat demand, how much of it each carrier meets, and
how much more the engine fleet could carry.

Three parts, on domestic traffic only (the 737-800 is a domestic aircraft here):
  1. market      demand (RPK) and supply (ASK) by month and by fiscal year, load factor,
                 and the seasonal index of demand -- checked against the flight index
                 the engine model assumes (lifecycle.FLIGHT_INDEX);
  2. carriers    each company's monthly passengers / ASK / RPK / L/F, its share of the
                 market's RPK, and a lower bound of the demand it could not carry
                 (months with L/F above a threshold: spilled ~ ASK x (L/F - threshold));
  3. engines     the engine plan's operations side (runout.ops) turned into seats:
                 spare serviceable engines -> aircraft that could fly -> ASK per month;
                 months short of engines -> ASK not flown -> revenue at the yield.
                 Growth months are where demand is tight (high L/F) and engines have
                 headroom at the same time of year.

Sources are in data/demand.json (e-Stat for the market, ANA's monthly PDF, press
reprints for JAL); the 737-800 share, the L/F threshold and the yield are assumptions
flagged no_source and must be replaced before any real use.

  python demand.py jal --runout runout/jal.json --out demand/jal.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lifecycle

HERE = Path(__file__).resolve().parent


def load() -> dict:
    return json.loads((HERE / "data" / "demand.json").read_text(encoding="utf-8"))


def market_view(D: dict) -> dict:
    M = D["market"]
    months = M["months"]
    avg = sum(x["rpk"] for x in months) / len(months)
    seas = {}
    for x in months:
        seas.setdefault(int(x["m"][5:]), []).append(x["rpk"] / avg)
    idx_demand = {m: sum(v) / len(v) for m, v in seas.items()}
    fi = lifecycle.FLIGHT_INDEX
    compare = [{"month": m, "demand_index": round(idx_demand[m], 3), "model_flight_index": fi[m], "gap": round(idx_demand[m] - fi[m], 3)} for m in sorted(idx_demand)]
    worst = max(compare, key=lambda c: abs(c["gap"]))
    fy = M["fiscal_years"]
    return {"months": months, "fiscal_years": fy, "seasonal": compare,
            "seasonal_note": f"需要の季節指数（RPK ÷ 平均）とモデルの運航指数の差が最も大きい月は {worst['month']} 月（{worst['gap']:+.2f}）",
            "recovery": {"fy2019_rpk": fy[1]["rpk"], "fy2025_rpk": fy[-1]["rpk"], "ratio": round(fy[-1]["rpk"] / fy[1]["rpk"], 3),
                         "ask_ratio": round(fy[-1]["ask"] / fy[1]["ask"], 3), "lf_2019": fy[1]["lf"], "lf_2025": fy[-1]["lf"]},
            "source": M["source"], "confidence": M["confidence"]}


def carrier_view(D: dict, cid: str) -> dict:
    C = D["companies"][cid]
    A = D["assumptions"]
    th = A["lf_capacity_threshold"]
    mk = {x["m"]: x for x in D["market"]["months"]}
    rows = []
    for x in C["months"]:
        lf = x["lf"] / 100 if x["lf"] is not None else None
        spill = (x["ask"] * max(0.0, lf - th) * A["spill_factor"]) if (x["ask"] and lf) else None
        m = mk.get(x["m"])
        rows.append({**x, "share_rpk": round(x["rpk"] / m["rpk"], 3) if (m and x["rpk"]) else None,
                     "share_ask": round(x["ask"] / m["ask"], 3) if (m and x["ask"]) else None,
                     "spilled_rpk": round(spill, 1) if spill is not None else None, "tight": bool(lf and lf >= th)})
    known = [r for r in rows if r["ask"]]
    lf_avg = sum(r["rpk"] for r in known if r["rpk"]) / sum(r["ask"] for r in known if r["rpk"]) if known else None
    tight = [r["m"] for r in rows if r["tight"]]
    spill_total = sum(r["spilled_rpk"] or 0 for r in rows)
    return {"name": C["name"], "months": rows, "lf_avg": round(lf_avg, 3) if lf_avg else None, "tight_months": tight,
            "spilled_rpk_total": round(spill_total, 1), "spilled_pax_est": int(spill_total * 1e6 / A["stage_length_km"]) if spill_total else 0,
            "threshold": th, "source": C["source"], "confidence": C["confidence"], "sources": C.get("sources", [])}


def engine_link(D: dict, cid: str, runout: dict | None, cfg: dict) -> dict | None:
    if not runout or not runout.get("ops"):
        return None
    C = D["companies"][cid]
    A = D["assumptions"]
    seats, share, yld, stage = C["seats_737_800"], C["share_737_800_of_domestic_ask"], C["yield_yen_per_rpk"], A["stage_length_km"]
    subs = cfg.get("subfleets") or []
    tot = sum(x["aircraft"] for x in subs) or 1
    cycles_month = (sum(x["aircraft"] * x["cycles_per_year"] for x in subs) / tot / 12) if subs else 165.0
    ask_per_ac_month = cycles_month * seats * stage / 1e6            # million seat-km an aircraft flies in a month
    cv = carrier_view(D, cid)
    lf_by_month = {}
    for r in cv["months"]:
        if r["lf"] is not None:
            lf_by_month.setdefault(int(r["m"][5:]), []).append(r["lf"] / 100)
    lf_by_month = {m: sum(v) / len(v) for m, v in lf_by_month.items()}
    known_ask = [r["ask"] for r in cv["months"] if r["ask"]]
    ask_month_avg = sum(known_ask) / len(known_ask) if known_ask else None
    out = []
    for o in runout["ops"]:
        m = int(o["label"][5:])
        extra_ac = max(0, o["margin"]) // 2
        short_ac = max(0, -o["margin"]) / 2
        lf = lf_by_month.get(m)
        ask_extra = extra_ac * ask_per_ac_month
        ask_lost = short_ac * ask_per_ac_month
        rev_lost = ask_lost * (lf or 0.8) * yld * 1e6 / 1e8      # 億円: million seat-km x LF x yen/RPK
        out.append({"t": o["t"], "label": o["label"], "margin": o["margin"], "extra_aircraft": int(extra_ac), "ask_headroom": round(ask_extra, 1),
                    "ask_headroom_share": round(ask_extra / (ask_month_avg * share), 3) if ask_month_avg else None,
                    "short_aircraft": short_ac, "ask_lost": round(ask_lost, 1), "revenue_lost_oku_yen": round(rev_lost, 2),
                    "lf_month": round(lf, 3) if lf else None, "growth_month": bool(lf and lf >= A["lf_capacity_threshold"] and extra_ac >= 1)})
    W = runout["window_months"]
    win = [x for x in out if x["t"] < W]
    return {"months": out, "params": {"seats": seats, "share_737_800": share, "yield_yen_per_rpk": yld, "stage_km": stage, "cycles_per_aircraft_month": round(cycles_month, 1),
                                      "ask_per_aircraft_month": round(ask_per_ac_month, 2)},
            "window": {"months": W, "growth_months": sum(1 for x in win if x["growth_month"]), "ask_headroom_avg": round(sum(x["ask_headroom"] for x in win) / max(1, len(win)), 1),
                       "ask_headroom_share_avg": round(sum(x["ask_headroom_share"] or 0 for x in win) / max(1, len(win)), 3),
                       "revenue_lost_oku_yen": round(sum(x["revenue_lost_oku_yen"] for x in win), 2), "short_months": sum(1 for x in win if x["short_aircraft"] > 0)},
            "life": {"revenue_lost_oku_yen": round(sum(x["revenue_lost_oku_yen"] for x in out), 2), "short_months": sum(1 for x in out if x["short_aircraft"] > 0),
                     "growth_months": sum(1 for x in out if x["growth_month"])},
            "note": ("エンジンの余力（稼働可能 − 必要 − 予備）÷ 2 = 飛ばせる機数、× 月の便数 × 座席 × 区間距離 = 上乗せできる ASK。"
                     "足りない月は逆に飛ばせない ASK × 利用率 × 単価 = 失う売上（億円）。伸ばせる月 = 需要が逼迫（利用率 ≥ 閾値）かつ余力あり")}


def build(cid: str, runout_path: Path | None) -> dict:
    D = load()
    conf = json.loads((HERE / "data" / "companies.json").read_text(encoding="utf-8"))["companies"][cid]
    ro = json.loads(runout_path.read_text(encoding="utf-8")) if runout_path and runout_path.exists() else None
    return {"company": cid, "market": market_view(D), "carrier": carrier_view(D, cid), "engines": engine_link(D, cid, ro, conf),
            "assumptions": D["assumptions"], "note": D["note"],
            "caveats": ["737-800 が国内線 ASK に占める割合、利用率の閾値、単価は出典なしの仮定（C）。決算資料と機材別の座席供給で差し替える",
                        "満たせなかった需要は下限の目安（利用率が閾値を超えた分）。路線別の満席便数からのスピル推定は未実装",
                        "JAL の月次は公式 PDF が取得できず報道の転載値。2025-09〜12 は未取得", "市場の季節指数は 13 か月分から。年をまたぐ月は 2 か月の平均"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--runout", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = build(a.company, a.runout)
    p = a.out or HERE / "demand" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    c, e = out["carrier"], out["engines"]
    print(f"{a.company}: L/F avg {c['lf_avg']}, tight months {c['tight_months']}, spilled RPK {c['spilled_rpk_total']} M (≈{c['spilled_pax_est']:,} pax); "
          + (f"window headroom {e['window']['ask_headroom_share_avg']:.0%} of 737-800 ASK, growth months {e['window']['growth_months']}, short months {e['window']['short_months']}, lost {e['window']['revenue_lost_oku_yen']} 億円" if e else "no runout"))
    print("  " + out["market"]["seasonal_note"] + f"; recovery FY2025/FY2019 RPK {out['market']['recovery']['ratio']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
