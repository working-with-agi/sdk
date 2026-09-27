#!/usr/bin/env python3
"""Build one company's inputs from data/companies.json.

Each company plans its own 737-800 engines under its own long-term shop contract, so the
daily decisions are *when* each engine goes in and *how much* work it gets -- not which
shop (that is decided at contract renewal: the tender use case, data/shop_quotes.json).

For a company this script
  1. runs the 20-year life-cycle simulation on its fleet (first 5 years discarded) to get
     the normal-state norms and the current state of every engine;
  2. writes data/<company>/fleet.json: engines due in the next 24 months, positions the
     schedule needs each month (seasonal), shelf buffer, spares, leases, budgets spread
     over the fiscal years by the seasonal norm, end-of-window condition;
  3. writes data/<company>/shops.json: the contracted shop only.

  python company.py jal ana          # both companies
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import lifecycle

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "data" / "companies.json"
TEMPLATE = HERE / "data" / "fleet_visits.json"


def poisson_quantile(mean: float, q: float) -> int:
    k, term = 0, math.exp(-mean)
    cdf = term
    while cdf < q:
        k += 1
        term *= mean / k
        cdf += term
    return k


def shops_for(name: str, cfg: dict, common: dict) -> dict:
    c = cfg["contract"]
    return {
        "meta": {"company": name, "description": f"{cfg['name']} の契約工場のみ（工場の選び直しは契約更新時の入札ユースケース）",
                 "contract_type": c["type"], "renewal": c["renewal"], "source": c["source"]},
        "shops": [{
            "id": c["shop_id"], "name": c["name"], "slots": c["slots_in_shop"],
            "transport_cost": common["transport_cost"], "transport_months": c["transport_months"],
            "overrun_share": common["findings"]["overrun_share"], "currency": "USD",
            "booking_lead_months": c["booking_lead_months"],
            "quotes": {w: {"price": q["price"], "tat": q["tat"]} for w, q in common["quotes"].items() if w != "source"},
            "findings": {k: common["findings"][k] for k in ("prob", "overrun_mean", "overrun_cv")},
            "delay": {k: common["delay"][k] for k in ("shop_months", "shop_probs", "engine_months", "engine_probs")},
        }],
    }


def fleet_for(name: str, cfg: dict, common: dict, years_back: int = 0) -> tuple[dict, dict]:
    """years_back > 0 rebuilds the input the company would have had that many years ago:
    the same simulated history, cut earlier (the plan versions of history.py)."""
    lifecycle.configure({**cfg, "contract": {**cfg["contract"], "quotes": {w: q for w, q in common["quotes"].items() if w != "source"}}})
    seed = cfg["lifecycle_seed"]
    visits, shelf, short, state, T = lifecycle.simulate(seed, years=lifecycle.YEARS - years_back)
    n = lifecycle.norms(visits, shelf, short, T)
    rows = lifecycle.window(state, T)
    base = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    if years_back:
        y, m = map(int, base["start"].split("-"))
        base["start"] = f"{y - years_back}-{m:02d}"
    H = base["horizon_months"]
    required = [lifecycle.needed_positions(t) for t in range(H)]
    un = base["unscheduled_removals"]
    mean_tat = sum(d * p for d, p in zip(un["tat_months"], un["tat_probs"]))
    buffer = poisson_quantile(un["rate_per_engine_month"] * cfg["engines"]["owned"] * mean_tat, 0.95)
    sp = cfg["spares"]
    months = {}
    y0, m0 = map(int, base["start"].split("-"))
    fy_start = base["budget"]["fiscal_year_start_month"]
    for t in range(H):
        y, m = y0 + (m0 - 1 + t) // 12, (m0 - 1 + t) % 12 + 1
        fy = f"FY{y if m >= fy_start else y - 1}"
        months[fy] = months.get(fy, 0) + n["seasonal"][m]["spend_k"]
    fleet = {
        "meta": {
            "company": name, "name": cfg["name"], "generator": "company.py", "lifecycle_seed": seed,
            "description": (f"{cfg['name']}: {cfg.get('type', '737-800')} {cfg['aircraft']['total']} 機、保有エンジン {cfg['engines']['owned']} 基。"
                            f"20 年のライフサイクル・シミュレーション（最初の 5 年は捨てる、定常）から、今後 24 か月に入場期限が来る {len(rows)} 基。"),
            "sources": {"aircraft": cfg["aircraft"]["source"], "engines": cfg["engines"]["source"],
                        "subfleets": {x["name"]: x["source"] for x in cfg.get("subfleets", [])},
                        "wear": cfg.get("wear", {}).get("source"), "severity": common.get("severity_source"),
                        "contract": cfg["contract"]["source"], "transition": cfg["transition"]["source"],
                        "quotes": common["quotes"]["source"], "leases": common["short_term_lease"]["source"],
                        "llp_kits": common["llp_kits"]["source"], "spares": sp["source"]},
            "units": base["meta"]["units"],
            "derivation": {"aircraft": cfg["aircraft"]["by_operator"], "thrust": cfg.get("wear", {}).get("thrust"),
                           "subfleets": [{k: x[k] for k in ("name", "aircraft", "cycles_per_year", "fh_per_cycle", "climate")} for x in cfg.get("subfleets", [])],
                           "norms_by_subfleet": n.get("by_subfleet"), "flight_index": lifecycle.FLIGHT_INDEX,
                           "airframe_checks": lifecycle.AIRFRAME_CHECKS, "base_aircraft_needed": lifecycle.BASE_NEEDED,
                           "buffer_quantile": 0.95},
        },
        "start": base["start"], "horizon_months": H,
        "required_positions": required,
        "buffer_spares": [buffer] * H,
        "owned_engines": cfg["engines"]["owned"],
        "short_term_lease": {"cost_per_month": common["short_term_lease"]["cost_per_month"],
                             "max_engines": sp["short_lease_max"], "max_engines_peak": sp["short_lease_max_peak"]},
        "long_term_spare": {"cost_per_month": common["long_term_spare"]["cost_per_month"], "max_engines": sp["long_spare_max"]},
        "aog_tiers": base["aog_tiers"], "aog_peak_multiplier": base["aog_peak_multiplier"],
        "unscheduled_removals": {**un, "background_engines": cfg["engines"]["owned"] - len(rows)},
        "workscope_build_value": {w: v for w, v in common["workscope_build_value"].items() if w != "source"},
        "green_time_value_per_month": base["green_time_value_per_month"],
        "llp_kits": {"workscopes": ["CORE", "FULL"], "lead_time_months": common["llp_kits"]["lead_time_months"],
                     "on_hand": sp["llp_kits_on_hand"], "emergency_premium": common["llp_kits"]["emergency_premium"]},
        "service_target": base["service_target"],
        "budget": {"fiscal_year_start_month": fy_start, "by_fiscal_year": {fy: round(k, -2) for fy, k in months.items()}},
        "fx": base["fx"],
        # after the window the schedule still needs its peak positions plus the shelf buffer
        "terminal_engines": max(required) + buffer,
        "transition": {k: v for k, v in cfg["transition"].items() if k != "source"},
        "engines": [{k: r[k] for k in ("esn", "operator", "window", "allowed_workscopes", "watch", "hazard", "driver")} for r in rows],
    }
    return fleet, n


def fleet_cfg(conf: dict, name: str, fleet_key: str | None) -> tuple[dict, dict]:
    """The company's 737-800 config (fleet_key None/'737') or one of its other fleets,
    with the common assumptions overridden by that fleet's quotes, leases and LLP lives."""
    cfg, common = conf["companies"][name], conf["common"]
    if not fleet_key or fleet_key == cfg.get("fleet_key", "737"):
        return cfg, common
    f = next(x for x in cfg.get("fleets", []) if x["type"] == fleet_key)
    common = {**common, "quotes": {**f["contract"]["quotes"], "source": f["sources"]["quotes"]},
              "short_term_lease": {**common["short_term_lease"], **f["leases"]["short_term_lease"], "source": f["leases"]["source"]},
              "long_term_spare": {**common["long_term_spare"], **f["leases"]["long_term_spare"]}}
    cfg = {**f, "name": f"{cfg['name']} {f['name']}", "fleet_key": fleet_key}
    return cfg, common


def build(name: str, fleet_key: str | None = None) -> dict:
    conf = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg, common = fleet_cfg(conf, name, fleet_key)
    out = HERE / "data" / name if not fleet_key or fleet_key == "737" else HERE / "data" / name / fleet_key
    out.mkdir(parents=True, exist_ok=True)
    fleet, n = fleet_for(name, cfg, common)
    fleet["meta"]["fleet_key"] = cfg.get("fleet_key", "737")
    fleet["meta"]["fleet_type"] = cfg.get("type", "737-800")
    fleet["meta"]["engine_type"] = cfg.get("engine", "CFM56-7B")
    (out / "fleet.json").write_text(json.dumps(fleet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "shops.json").write_text(json.dumps(shops_for(name, cfg, common), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{name}: {cfg['aircraft']['total']} aircraft, {cfg['engines']['owned']} engines, {len(fleet['engines'])} due in 24 months; "
          f"norms {n['visits_per_year']:.1f} visits/yr, {n['spend_per_year_k']:,.0f} k$/yr, {n['usd_per_efh']:.0f} $/EFH; "
          f"budgets {fleet['budget']['by_fiscal_year']}")
    return fleet


def configure_for_fleet(fleet_path: Path) -> int | None:
    """Set lifecycle to the company a fleet file was built for; returns its seed (None for
    a file not built by this script, e.g. the old group-wide sample)."""
    meta = json.loads(Path(fleet_path).read_text(encoding="utf-8")).get("meta", {})
    name = meta.get("company")
    if not name:
        return None
    conf = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg, common = fleet_cfg(conf, name, meta.get("fleet_key"))
    lifecycle.configure({**cfg, "contract": {**cfg["contract"], "quotes": {w: q for w, q in common["quotes"].items() if w != "source"}}})
    return meta.get("lifecycle_seed", 7)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("companies", nargs="*", default=["jal", "ana"])
    ap.add_argument("--fleet", help="one of the company's other fleets (e.g. 787, 767); default: 737-800")
    ap.add_argument("--all-fleets", action="store_true", help="build the 737-800 and every other fleet")
    args = ap.parse_args(argv)
    conf = json.loads(CONFIG.read_text(encoding="utf-8"))
    for c in args.companies:
        keys = [None] + [f["type"] for f in conf["companies"][c].get("fleets", [])] if args.all_fleets else [args.fleet]
        for k in keys:
            build(c, k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
