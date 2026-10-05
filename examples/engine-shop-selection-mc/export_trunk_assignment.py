#!/usr/bin/env python3
"""fleet/<company>.json -> trunk_assignment.json for a browser demo that reads answers instead of solving.

The page shows, month by month and for p10/p50/p90, which aircraft type flies which day pattern on
the trunk routes, the slots used, the load factors, the passengers left behind and the money; the
fleet assignment itself is solved here (route_fleet.py). The label is what the page calls the
company (the file carries no other company name).

  python export_trunk_assignment.py jal --label "Company A" --out trunk_assignment.json
"""
import argparse
import json
from pathlib import Path

import route_fleet as rf

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("company"); ap.add_argument("--label", default="Company"); ap.add_argument("--out", type=Path, default=Path("trunk_assignment.json"))
a = ap.parse_args()
cid, label, out = a.company, a.label, a.out
J = json.load(open(HERE / "fleet" / f"{cid}.json", encoding="utf-8")); tr = J['trunk']; R = rf.load()
types = rf.types_of(R, cid)
A = tr["airport"]
doc = {"schema": "trunk_assignment/2", "company": label, "start": J["start"], "fy_start_month": 4,
       "unit": {"pax": "千人（往復合計）", "money": "億円", "usd_jpy": 157, "frequency": "1 日の往復便数"},
       "assumptions": {"spill_model": R["spill_model"], "fare_taper": R.get("fare_taper"), "cost_model": R.get("cost_model"), "lease_k_per_aircraft_month": R["lease"]["k_per_aircraft_month"], "sources": R.get("sources")},
       "airport": {"hub_trunk_round_trips": A["budget"], "use_min": A["use_min"], "bounds": A["bounds"], "share_now": A["share_now"], "competitor_freq": A["competitor_freq"]},
       "types": [{k: t.get(k) for k in ("type", "name", "seats", "engine", "fleet_total", "trunk_aircraft", "cost_per_block_h_k", "turnaround_h")} for t in types],
       "routes": [{k: r[k] for k in ("id", "name", "km", "block_h", "market_pax_2024", "market_lf_2024", "slot_airport")} for r in R["routes"]],
       "patterns": [{"id": p["id"], "name": p["name"], "legs": next(x["legs"] for x in R["patterns"] if x["id"] == p["id"]), "cycles_per_day": p["cycles_per_day"], "types": p["types"]} for p in tr["patterns"]],
       "version": {"by_type_pattern": tr["version"]["by_type_pattern"], "round_trips": tr["version"]["round_trips"], "share": tr["version"]["share"]},
       "months": []}
for r, d, o, x in zip(tr["rows"], tr["demand"], tr["others"], tr["reconciliation"]["rows"]):
    doc["months"].append({"t": r["t"], "label": r["label"], "fy": r["fy"], "fy_month": (int(r["label"][5:]) - 4) % 12 + 1,
        "demand": d["routes"], "market": d["market_p50"],
        "available": r["available"], "regional_737": o["need_p50"], "checks_737": x["in_checks"],
        "q": {q: {"used": r[f"used_{q}"], "lease": r[f"lease_{q}"], "spill_pax": r[f"spill_{q}_pax_k"]} for q in ("p10", "p50", "p90")},
        "p50": {"by_type_pattern": r["by_type_pattern_p50"], "round_trips": r["round_trips_p50"], "avg_seats": r["avg_seats_p50"], "lf": r["lf_p50"],
                "legs_by_type": r["legs_by_type_p50"], "legs_by_band": r["legs_band_p50"],
                "spill_by_route": r["spill_by_route_p50"], "lost_revenue_oku": round(r["cost_k_p50"]["lost_revenue"] * 157 / 1e5, 2),
                "lease_cost_oku": round(r["cost_k_p50"]["lease"] * 157 / 1e5, 2), "no_lease_lost_revenue_oku": round(r["no_lease_p50"]["lost_revenue_k"] * 157 / 1e5, 2)}})
doc["year_end"] = tr["decisions"]["year_end"]
doc["slot_scenarios"] = [{k: x[k] for k in ("delta_round_trips", "budget", "version_round_trips", "share", "pax_k", "revenue_oku", "lost_revenue_oku", "operating_cost_oku", "aircraft_used_avg", "vs_base")}
                         | {"engine_737": {k: x["engine_737"].get(k) for k in ("trunk_cycles_per_aircraft_day", "utilisation_multiplier", "windows")}} for x in tr["slot_scenarios"]["rows"]]
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(out, len(json.dumps(doc)) // 1024, "KB")
