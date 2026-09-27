"""The type's clock (型式の時計): where an engine type stands in its generation, and what
that does to residual value, late-life costs and the chance the successor is late.

Above the engine's own clock (cycles, EGT margin) sits the type's: entry into service ->
end of production -> the retirement wave -> the successor. The run-out chain ends where
the company's transition puts it, but the *value* of what leaves and the *cost* of what
stays depend on how old the type is by then.

  stage           young (before production end), late (after it), fading (past the middle
                  of the retirement wave)
  residual        the half-life value multiplier by calendar year: 1.0 at production end,
                  falling straight to a floor when the type disappears (assumption C)
  late-life costs parts escalation per year and TAT extension after production end (C)
  successor risk  probability that the successor's deliveries slip, by its age (C)

Sources and assumptions: data/engine_types.json.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load() -> dict:
    return json.loads((HERE / "data" / "engine_types.json").read_text(encoding="utf-8"))


def residual_multiplier(T: dict, etype: str, year: float) -> float:
    t = T["types"][etype]
    d = T["assumptions"]["residual_decay"]
    a, b = t["production_end"], t["retirement_wave_end"]
    if year <= a:
        return 1.0
    if year >= b:
        return d["floor"]
    return 1.0 - (1.0 - d["floor"]) * (year - a) / (b - a)


def stage(T: dict, etype: str, year: float) -> str:
    t = T["types"][etype]
    if t.get("production_end") is None or year < t["production_end"]:
        return "young"
    mid = (t["production_end"] + t["retirement_wave_end"]) / 2
    return "late" if year < mid else "fading"


def successor_delay_prob(T: dict, etype: str, year: float) -> float | None:
    succ = T["types"][etype].get("successor")
    s = T["types"].get(succ)
    if not s or not s.get("eis"):
        return None
    age = year - s["eis"]
    p = T["assumptions"]["delivery_delay_prob_by_successor_age"]
    return p["0-5"] if age < 5 else p["5-10"] if age < 10 else p["10+"]


def build(etype: str, start: str, runout: dict | None) -> dict:
    T = load()
    t = T["types"][etype]
    A = T["assumptions"]
    y0 = int(start[:4]) + (int(start[5:7]) - 1) / 12
    years = list(range(int(y0), t["retirement_wave_end"] + 1))
    curve = [{"year": y, "multiplier": round(residual_multiplier(T, etype, y), 3), "stage": stage(T, etype, y)} for y in years]
    out = {"type": etype, "aircraft": t["aircraft"], "eis": t["eis"], "production_end": t["production_end"], "retirement_wave_end": t["retirement_wave_end"],
           "successor": t.get("successor"), "successor_eis": T["types"].get(t.get("successor"), {}).get("eis"),
           "successor_next": T["types"].get(t.get("successor"), {}).get("successor"), "successor_next_eis": T["types"].get(t.get("successor"), {}).get("successor_eis"),
           "age_at_start": round(y0 - t["eis"], 1), "years_since_production_end": round(y0 - t["production_end"], 1), "stage_now": stage(T, etype, y0),
           "generation_interval": A["generation_interval_years"], "curve": curve,
           "late_life": {"parts_escalation_per_year": A["late_life_parts_escalation_per_year"], "tat_extra_months_per_5y": A["late_life_tat_extra_months_per_5y"],
                         "years_late_by_fleet_exit": None},
           "successor_delay_prob_now": successor_delay_prob(T, etype, y0),
           "sources": {"eis": t["eis_source"], "production_end": t["production_end_source"], "values": t["values"]["source"], "market": t.get("market_note"),
                       "successor": T["types"].get(t.get("successor"), {}).get("successor_eis_source"), "assumptions": [A["generation_source"], A["residual_decay"]["note"], A["late_life_source"], A["delivery_delay_prob_by_successor_age"]["source"]]},
           "note": T["note"]}
    if runout:
        # the residual value that leaves with each engine, at the type's age in its exit year
        rows = []
        tot_raw = tot_adj = 0.0
        for e in runout["engines"]:
            if e["retire_t"] is None:
                continue
            y = int(e["retire"][:4]) + (int(e["retire"][5:7]) - 1) / 12
            m = residual_multiplier(T, etype, y)
            rows.append({"esn": e["esn"], "retire": e["retire"], "multiplier": round(m, 3), "residual_k": e["residual_value_k"], "residual_adj_k": round(e["residual_value_k"] * m)})
            tot_raw += e["residual_value_k"]; tot_adj += e["residual_value_k"] * m
        last = max((int(e["retire"][:4]) for e in runout["engines"] if e["retire"]), default=int(y0))
        out["residual"] = {"engines": rows, "raw_k": round(tot_raw), "adjusted_k": round(tot_adj), "lost_to_type_age_k": round(tot_raw - tot_adj),
                           "note": "退役で処分する残存価値（ハーフライフ換算）に、退役年の型式の年齢の倍率を掛けたもの。差が、型式の晩年に売る分の値下がり"}
        out["late_life"]["years_late_by_fleet_exit"] = last - t["production_end"]
        out["late_life"]["parts_factor_by_fleet_exit"] = round((1 + A["late_life_parts_escalation_per_year"]) ** max(0, last - t["production_end"]), 3)
        out["late_life"]["tat_extra_by_fleet_exit"] = round(A["late_life_tat_extra_months_per_5y"] * max(0, last - t["production_end"]) / 5, 2)
        out["fleet_exit_year"] = last
        out["fleet_vs_world"] = (f"当社の最終退役 {last} 年は、型式が世界から消える {t['retirement_wave_end']} 年の {t['retirement_wave_end'] - last} 年前。"
                                 + ("世界より早く出るので、退役機の売り先（グリーンタイム・部品取り）はまだある" if t["retirement_wave_end"] - last >= 5 else "世界と同時に出るので、退役機の売り先は薄い"))
    return out
