#!/usr/bin/env python3
"""20-year life-cycle simulation of one engine fleet, month by month.

Why: a 2-year plan is a window inside a much longer life cycle. This simulation
  1. gives the "normal state" norms: shop visits per year by workscope, spend per year,
     $/EFH, spares on the shelf, how often the shelf runs dry -- the rough annual
     figures everyone implicitly agrees on;
  2. produces a realistic *current* fleet: engines at every stage of their run, so the
     2-year window starts from a state the past actually produces (and the number of
     visits in the window comes out of the simulation instead of being assumed).

The first WARMUP years are discarded: every engine starts new, which no real fleet does.

Baseline = stationary: every parameter is constant over time. Trends (aging, price
escalation) are parameters that default to zero and are compared as deltas later.

Engine physics (per engine)
  cycles        ~2,000 per aircraft-year when on wing (seasonal: flights follow the
                flight index)
  EGT margin    lost at ~5 degC / 1,000 cycles, engine-specific (lognormal spread)
  LLP           core stack 20,000 cycles, LP stack 25,000 cycles
Removal policy (simple, stationary)
  remove when EGT margin < 3 degC or a stack has < 1,500 cycles left
  workscope     a stack is replaced if it would not last 60 % of a typical run;
                LP stack -> FULL, core stack only -> CORE, neither -> PR
Start         engine ages are scattered at random (a fleet is never new all at once);
              the warm-up removes the rest of the artificial start
  unscheduled   0.004 removals per engine-month -> PR-level visit (or CORE if due soon)
Shop
  TAT 3 months (+0-2 random), costs PR 2,500 / CORE 5,900 / FULL 9,900 k$

  python lifecycle.py                          # norms + snapshot -> lifecycle.json
  python lifecycle.py --fleet-out data/fleet_visits_lifecycle.json   # 2-year window input
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

YEARS, WARMUP = 20, 5
AIRCRAFT, ENGINES = 76, 166
START_MONTH = 10  # calendar month of the snapshot month (t = 0 of the 2-year window)
FLIGHT_INDEX = {1: 0.90, 2: 0.88, 3: 1.06, 4: 0.97, 5: 1.02, 6: 0.90,
                7: 1.02, 8: 1.12, 9: 0.98, 10: 1.00, 11: 0.96, 12: 1.03}
AIRFRAME_CHECKS = {1: 6, 2: 6, 3: 2, 4: 4, 5: 2, 6: 6, 7: 3, 8: 2, 9: 4, 10: 4, 11: 6, 12: 2}
BASE_NEEDED = 68

CYCLES_PER_MONTH = 2000 / 12
EGT_LOSS_PER_1000 = 5.0
EGT_SPREAD = 0.25            # lognormal sigma of engine-specific deterioration
RESTORE = {"PR": 55.0, "CORE": 58.0, "FULL": 62.0}
CORE_LIFE, LP_LIFE = 20000, 25000
MIN_MARGIN, MIN_LLP = 3.0, 1500
COST = {"PR": 2500, "CORE": 5900, "FULL": 9900}
TAT = 3
UNSCHED_RATE = 0.004
HOURS_PER_CYCLE = 1.6


def month_of(t: int) -> int:
    return (START_MONTH - 1 + t) % 12 + 1


def needed_positions(t: int) -> int:
    m = month_of(t)
    return 2 * min(AIRCRAFT - AIRFRAME_CHECKS[m], math.ceil(BASE_NEEDED * FLIGHT_INDEX[m]))


STUB_TOLERANCE = 0.6  # replace a stack only if it would not last 60 % of a typical run


def workscope(core_left: float, lp_left: float, margin_run_cycles: float) -> str:
    core_low = core_left < MIN_LLP + STUB_TOLERANCE * margin_run_cycles
    lp_low = lp_left < MIN_LLP + STUB_TOLERANCE * margin_run_cycles
    if core_low and lp_low:
        return "FULL"
    if lp_low:
        return "FULL"
    if core_low:
        return "CORE"
    return "PR"


def simulate(seed: int = 7, years: int = YEARS, aging: float = 0.0, unsched_growth: float = 0.0):
    """aging: yearly growth of the deterioration rate (0 = stationary baseline)."""
    rng = np.random.default_rng(seed)
    T = years * 12
    # engine state
    loss = EGT_LOSS_PER_1000 / 1000 * rng.lognormal(-EGT_SPREAD**2 / 2, EGT_SPREAD, ENGINES)  # degC per cycle
    # start from scattered ages (no real fleet is new all at once); the warm-up then
    # removes what is left of the artificial start
    margin = rng.uniform(MIN_MARGIN + 1, RESTORE["FULL"], ENGINES)
    core = rng.uniform(MIN_LLP + 500, CORE_LIFE, ENGINES)
    lp = rng.uniform(MIN_LLP + 500, LP_LIFE, ENGINES)
    back = np.zeros(ENGINES, dtype=int)   # month the engine returns from the shop (0 = serviceable)
    visits, shelf, short = [], [], []
    run_cycles = RESTORE["PR"] / (EGT_LOSS_PER_1000 / 1000)  # typical run length in cycles

    for t in range(T):
        serviceable = np.nonzero(back <= t)[0]
        need = needed_positions(t)
        # fly the engines with the most margin left first? no: fly by index (random order) --
        # the operator cannot pick freely; a random permutation stands in for tail assignment
        order = rng.permutation(serviceable)
        flying = order[:need]
        shelf.append(len(serviceable) - len(flying))
        short.append(max(0, need - len(serviceable)))
        idx = FLIGHT_INDEX[month_of(t)]
        cyc = CYCLES_PER_MONTH * idx
        grow = (1 + aging) ** (t / 12)
        margin[flying] -= loss[flying] * cyc * grow
        core[flying] -= cyc
        lp[flying] -= cyc
        # removals
        due = flying[(margin[flying] < MIN_MARGIN) | (core[flying] < MIN_LLP) | (lp[flying] < MIN_LLP)]
        rate = UNSCHED_RATE * (1 + unsched_growth) ** (t / 12)
        failed = flying[rng.random(len(flying)) < rate]
        for e in set(due.tolist()) | set(failed.tolist()):
            ws = workscope(core[e], lp[e], run_cycles)
            unscheduled = e not in set(due.tolist())
            visits.append({"t": t, "engine": int(e), "ws": ws, "unscheduled": bool(unscheduled)})
            margin[e] = RESTORE[ws]
            if ws in ("CORE", "FULL"):
                core[e] = CORE_LIFE
            if ws == "FULL":
                lp[e] = LP_LIFE
            back[e] = t + TAT + int(rng.integers(0, 3))
    state = {"margin": margin, "core": core, "lp": lp, "back": back, "loss": loss}
    return visits, np.array(shelf), np.array(short), state, T


def norms(visits, shelf, short, T):
    t0 = WARMUP * 12
    v = [x for x in visits if x["t"] >= t0]
    yrs = (T - t0) / 12
    by_ws = {w: sum(1 for x in v if x["ws"] == w) / yrs for w in COST}
    spend = sum(COST[x["ws"]] for x in v) / yrs
    efh = ENGINES * 0 + sum(needed_positions(t) for t in range(t0, T)) / (T - t0) * 12 * CYCLES_PER_MONTH * HOURS_PER_CYCLE
    per_year = {}
    for x in v:
        y = (x["t"] - t0) // 12
        per_year[y] = per_year.get(y, 0) + 1
    counts = np.array([per_year.get(y, 0) for y in range(int(yrs))])
    return {
        "visits_per_year": sum(by_ws.values()),
        "visits_per_year_by_workscope": by_ws,
        "visits_per_year_min_max": [int(counts.min()), int(counts.max())],
        "unscheduled_share": sum(x["unscheduled"] for x in v) / max(1, len(v)),
        "spend_per_year_k": spend,
        "usd_per_efh": spend * 1000 / efh,
        "mean_run_months": 12 * ENGINES / max(1e-9, sum(by_ws.values())),
        "shelf_mean": float(shelf[t0:].mean()),
        "shelf_p5": float(np.percentile(shelf[t0:], 5)),
        "short_month_share": float((short[t0:] > 0).mean()),
    }


def window(state, t_now: int, horizon: int = 24, width: int = 5):
    """Engines due within the window, as input rows for the 2-year optimisation."""
    margin, core, lp, loss = state["margin"], state["core"], state["lp"], state["loss"]
    rows = []
    run_cycles = RESTORE["PR"] / (EGT_LOSS_PER_1000 / 1000)
    for e in range(ENGINES):
        if state["back"][e] > t_now:
            continue  # in the shop right now
        # months until a hard limit, assuming average utilisation
        m_egt = (margin[e] - MIN_MARGIN) / (loss[e] * CYCLES_PER_MONTH) if loss[e] > 0 else 1e9
        m_llp = (min(core[e], lp[e]) - MIN_LLP) / CYCLES_PER_MONTH
        latest = int(max(0, min(m_egt, m_llp)))
        if latest >= horizon:
            continue
        ws = workscope(core[e] - latest * CYCLES_PER_MONTH, lp[e] - latest * CYCLES_PER_MONTH, run_cycles)
        allowed = {"PR": ["PR", "CORE"], "CORE": ["CORE", "FULL"], "FULL": ["FULL"]}[ws]
        rows.append({
            "esn": f"896-{101 + e:03d}",
            "window": [max(0, latest - width), latest],
            "allowed_workscopes": allowed,
            "watch": bool(loss[e] > np.quantile(loss, 0.85)),
            "hazard": 0.06 if loss[e] > np.quantile(loss, 0.85) else 0.01,
            "operator": "mainline",
            "egt_margin": round(float(margin[e]), 1),
            "llp_remaining": {"core": int(core[e]), "lp": int(lp[e])},
        })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--aging", type=float, default=0.0, help="yearly growth of deterioration (0 = stationary)")
    ap.add_argument("--unsched-growth", type=float, default=0.0)
    ap.add_argument("--json-out", type=Path, default=Path("lifecycle.json"))
    ap.add_argument("--fleet-out", type=Path, help="write the 2-year window input (fleet_visits format)")
    args = ap.parse_args(argv)

    visits, shelf, short, state, T = simulate(args.seed, aging=args.aging, unsched_growth=args.unsched_growth)
    n = norms(visits, shelf, short, T)
    rows = window(state, T)
    out = {"assumptions": {"stationary": args.aging == 0 and args.unsched_growth == 0, "aging": args.aging,
                           "unsched_growth": args.unsched_growth, "years": YEARS, "warmup_years": WARMUP},
           "norms": n, "window_visits": len(rows),
           "window_by_workscope": {w: sum(1 for r in rows if r["allowed_workscopes"][0] == w) for w in COST}}
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.fleet_out:
        base = json.loads((HERE / "data" / "fleet_visits.json").read_text(encoding="utf-8"))
        base["engines"] = [{k: r[k] for k in ("esn", "operator", "window", "allowed_workscopes", "watch", "hazard")} for r in rows]
        base["unscheduled_removals"]["background_engines"] = ENGINES - len(rows)
        # after the window the schedule still needs its peak positions plus the shelf
        # buffer: the fleet may not shrink below that (end-of-window condition)
        base["terminal_engines"] = max(base["required_positions"]) + max(base["buffer_spares"])
        # budgets = the normal-state annual spend (the implicit annual agreement), pro rata
        # for the months of each fiscal year inside the window
        months = {}
        y0, m0 = map(int, base["start"].split("-"))
        fy_start = base["budget"]["fiscal_year_start_month"]
        for t in range(base["horizon_months"]):
            y, m = y0 + (m0 - 1 + t) // 12, (m0 - 1 + t) % 12 + 1
            fy = f"FY{y if m >= fy_start else y - 1}"
            months[fy] = months.get(fy, 0) + 1
        base["budget"]["by_fiscal_year"] = {fy: round(n["spend_per_year_k"] * k / 12, -2) for fy, k in months.items()}
        base["meta"]["description"] = (
            f"Current fleet state from a {YEARS}-year life-cycle simulation (first {WARMUP} years discarded, "
            f"{'stationary' if out['assumptions']['stationary'] else 'with trends'}); {len(rows)} engines due in the next 24 months."
        )
        base["meta"]["generator"] = "lifecycle.py"
        args.fleet_out.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
