#!/usr/bin/env python3
"""Past plan versions against what happened, and how well the risks were judged.

The company would have made the same kind of 2-year plan two years ago and one year ago.
We rebuild those versions from the same simulated history cut earlier, solve them the
same way, and compare with what the history then did:

  removal forecast   each engine's forecast limit month against its actual removal
  volume             shop visits planned per fiscal year against actual ones
  risk fit           the forecast range of removals per fiscal year (planned ones plus
                     unscheduled ones at the assumed rate) -- did the actual count fall in
                     the 10-90 % range? -- and the unscheduled removals assumed vs seen
  stability          how much of one version's second year survives into the next
                     version's first year (same engine, same month +-1), moved, dropped,
                     or added

  python history.py jal ana
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

import baseline
import company
import lifecycle

HERE = Path(__file__).resolve().parent
VERSIONS = (2, 1, 0)   # years before now


def label(start: str, t: int) -> str:
    y, m = map(int, start.split("-"))
    k = m - 1 + t
    return f"{y + k // 12}-{k % 12 + 1:02d}"


def fy_of(start: str, t: int, fy_start: int = 4) -> str:
    y, m = map(int, label(start, t).split("-"))
    return f"FY{y if m >= fy_start else y - 1}"


def build(name: str, scenarios: int = 40, seed: int = 42) -> dict:
    conf = json.loads((HERE / "data" / "companies.json").read_text(encoding="utf-8"))
    cfg, common = conf["companies"][name], conf["common"]
    shops = HERE / "data" / name / "shops.json"
    # the full history up to now (the truth the past versions are checked against)
    company.configure_for_fleet(HERE / "data" / name / "fleet.json")
    visits, *_ = lifecycle.simulate(cfg["lifecycle_seed"])
    T_now = lifecycle.YEARS * 12
    now_start = json.loads((HERE / "data" / name / "fleet.json").read_text(encoding="utf-8"))["start"]
    esn = lambda e: f"{cfg['esn_prefix']}-{101 + e:03d}"  # noqa: E731
    versions = []
    with tempfile.TemporaryDirectory() as tmp:
        for back in VERSIONS:
            fleet, _n = company.fleet_for(name, cfg, common, years_back=back)
            path = Path(tmp) / f"fleet_{back}.json"
            path.write_text(json.dumps(fleet, ensure_ascii=False), encoding="utf-8")
            _a, _c, summ, rows = baseline.solve_summary(((), "base", str(path), str(shops), scenarios, seed, 500, 60, ("budget",)))
            T0 = T_now - 12 * back
            un = fleet["unscheduled_removals"]
            versions.append({"back": back, "start": fleet["start"], "T0": T0, "rows": rows, "summary": summ,
                             "unsched_rate": un["rate_per_engine_month"], "engines": fleet["owned_engines"],
                             "hazards": {e["esn"]: e["hazard"] for e in fleet["engines"]},
                             "budget": fleet["budget"]["by_fiscal_year"]})
    actual = [{"esn": esn(v["engine"]), "T": v["t"], "ws": v["ws"], "unscheduled": v["unscheduled"]} for v in visits]
    cost = lifecycle.COST

    out = {"company": name, "now": now_start, "versions": []}
    rng = np.random.default_rng(seed)
    for v in versions:
        T0, start = v["T0"], v["start"]
        realised = min(24, T_now - T0)   # months of this version that are history now
        seen = [a for a in actual if T0 <= a["T"] < T0 + realised]
        first = {}
        for a in seen:
            first.setdefault(a["esn"], a)
        # removal forecast: forecast limit vs the actual removal month
        timing = []
        for r in v["rows"]:
            a = first.get(r["esn"])
            lim_rel = _months_between(start, r["limit"])
            if lim_rel >= realised and a is None:
                continue  # not due yet
            timing.append({"esn": r["esn"], "forecast": lim_rel, "planned": r["t"],
                           "actual": None if a is None else a["T"] - T0, "unscheduled": bool(a and a["unscheduled"])})
        planned_esn = {r["esn"] for r in v["rows"]}
        unplanned = [a for a in seen if a["esn"] not in planned_esn]
        # volume and risk fit per fiscal year (only fiscal years fully or partly in history)
        fys = []
        for fy in sorted({fy_of(start, t) for t in range(realised)}):
            ts = [t for t in range(realised) if fy_of(start, t) == fy]
            plan_n = sum(1 for r in v["rows"] if fy_of(start, r["t"]) == fy and r["t"] < realised)
            plan_spend = sum(r["exp_cost"] for r in v["rows"] if fy_of(start, r["t"]) == fy and r["t"] < realised)
            act = [a for a in seen if fy_of(start, a["T"] - T0) == fy]
            # forecast range: planned removals (each may move out of the year: 15 %) plus
            # unscheduled removals of the other engines (Poisson at the assumed rate)
            lam = v["unsched_rate"] * (v["engines"] - len(v["rows"])) * len(ts)
            sims = rng.binomial(plan_n, 0.85, 4000) + rng.poisson(lam, 4000)
            fys.append({"fy": fy, "months": len(ts), "planned": plan_n, "actual": len(act),
                        "planned_spend": plan_spend, "actual_spend": sum(cost[a["ws"]] for a in act),
                        "p10": int(np.percentile(sims, 10)), "p90": int(np.percentile(sims, 90)),
                        "inside": bool(np.percentile(sims, 10) <= len(act) <= np.percentile(sims, 90)),
                        "unsched_expected": lam, "unsched_actual": sum(1 for a in act if a["unscheduled"]),
                        "budget": v["budget"].get(fy, 0)})
        out["versions"].append({"version": start, "back": v["back"], "realised_months": realised,
                                "planned": len(v["rows"]), "timing": timing, "unplanned": len(unplanned),
                                "fiscal_years": fys, "rows": [{k: r[k] for k in ("esn", "t", "workscope", "limit")} for r in v["rows"]]})
    # stability: version k's months 12-23 against version k+1's months 0-11
    stab = []
    for a, b in zip(out["versions"], out["versions"][1:]):
        old = {r["esn"]: r["t"] - 12 for r in a["rows"] if r["t"] >= 12}
        new = {r["esn"]: r["t"] for r in b["rows"] if r["t"] < 12}
        cats = {"same": 0, "moved": 0, "moved_far": 0, "dropped": 0, "added": 0}
        for e, t in old.items():
            if e not in new:
                cats["dropped"] += 1
            elif abs(new[e] - t) <= 1:
                cats["same"] += 1
            elif abs(new[e] - t) <= 3:
                cats["moved"] += 1
            else:
                cats["moved_far"] += 1
        cats["added"] = sum(1 for e in new if e not in old)
        stab.append({"from": a["version"], "to": b["version"], **cats,
                     "kept_share": cats["same"] / max(1, len(old))})
    out["stability"] = stab
    return out


def _months_between(start: str, lab: str) -> int:
    y0, m0 = map(int, start.split("-"))
    y1, m1 = map(int, lab.split("-"))
    return (y1 - y0) * 12 + (m1 - m0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("companies", nargs="*", default=["jal", "ana"])
    ap.add_argument("--out-dir", type=Path, default=Path("."))
    args = ap.parse_args(argv)
    for c in args.companies:
        h = build(c)
        (args.out_dir / f"{c}-history.json").write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
        for v in h["versions"]:
            err = [t["actual"] - t["forecast"] for t in v["timing"] if t["actual"] is not None]
            print(f"{c} {v['version']}: {v['planned']} planned, realised {v['realised_months']} m, "
                  f"timing error mean {np.mean(err) if err else float('nan'):+.1f} m (n={len(err)}), unplanned {v['unplanned']}, "
                  + ", ".join(f"{f['fy']} {f['planned']}->{f['actual']} [{f['p10']}-{f['p90']}]" for f in v["fiscal_years"]))
        for s in h["stability"]:
            print(f"  {s['from']} -> {s['to']}: kept {s['same']}, moved {s['moved']}+{s['moved_far']}, dropped {s['dropped']}, added {s['added']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
