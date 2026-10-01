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
doc = {"schema": "trunk_assignment/1", "company": label, "start": J["start"], "fy_start_month": 4, "unit": {"pax": "千人（往復合計）", "money": "億円", "usd_jpy": 157},
       "assumptions": {"lf_plan": 0.85, "lf_max": rf.LF_MAX, "lease_k_per_aircraft_month": R["lease"]["k_per_aircraft_month"], "no_source": True},
       "types": [{k: t[k] for k in ("type", "name", "seats", "engine", "trunk_aircraft", "cost_per_block_h_k", "turnaround_h")} for t in types],
       "routes": [{**{k: r[k] for k in ("id", "name", "km", "block_h")}, "slots_legs_per_day": r["slots_legs_per_day"]} for r in R["routes"]],
       "patterns": [{"id": p["id"], "name": p["name"], "legs": next(x["legs"] for x in R["patterns"] if x["id"] == p["id"]), "cycles_per_day": p["cycles_per_day"], "types": p["types"]} for p in tr["patterns"]],
       "version": tr["version"]["by_type_pattern"],
       "months": []}
for r, d, o, x in zip(tr["rows"], tr["demand"], tr["others"], tr["reconciliation"]["rows"]):
    doc["months"].append({"t": r["t"], "label": r["label"], "fy": r["fy"], "fy_month": (int(r["label"][5:]) - 4) % 12 + 1,
        "demand": d["routes"],
        "available": r["available"], "regional_737": o["need_p50"], "checks_737": x["in_checks"],
        "q": {q: {"used": r[f"used_{q}"], "lease": r[f"lease_{q}"]} for q in ("p10", "p50", "p90")},
        "p50": {"by_type_pattern": r["by_type_pattern_p50"], "lf": r["lf_p50"], "slots_used": r["slots_used_p50"], "spill_pax": r["spill_p50_pax_k"],
                "lost_revenue_oku": round(r["cost_k_p50"]["lost_revenue"] * 157 / 1e5, 2), "lease_cost_oku": round(r["cost_k_p50"]["lease"] * 157 / 1e5, 2),
                "no_lease_lost_revenue_oku": round(r["no_lease_p50"]["lost_revenue_k"] * 157 / 1e5, 2)},
        "p90": {"spill_pax": r["spill_p90_pax_k"]}})
doc["year_end"] = tr["decisions"]["year_end"]
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(out, len(json.dumps(doc)) // 1024, "KB")
