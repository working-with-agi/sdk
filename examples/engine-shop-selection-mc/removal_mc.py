#!/usr/bin/env python3
"""The engine removal plan by Monte Carlo (取卸し計画をシミュレーションで作る).

lifecycle.window() turns today's fleet state into the 2-year plan's input by running
every engine's *mean* deterioration forward to its limit: one removal month per engine,
a window of fixed width before it, and a failure hazard of 0.06 (watch list) or 0.01.
The removal plan -- which engines, when, how sure -- is then a single number each.

This runs the same state forward along many paths instead, with what the mean hides:
  rate       the deterioration rate is an estimate from the EGT trend, not a known value:
             lognormal error per engine and path (sigma --rate-sigma)
  flying     cycles per month vary around the sub-fleet's utilisation x the flight index
             (normal, sigma --util-sigma); a serviceable engine flies in a month with
             probability needed positions / serviceable engines (tail assignment)
  heavy      unscheduled removals that force the shop visit (bearing, bird, FOD):
             0.013 per 1,000 EFH (PRACTICE.md, 予定外の取卸し)
  light      unscheduled removals fixed by a short repair (oil leak, partial repair):
             0.017 per 1,000 EFH; the engine comes back and the planned visit stays
  limit      EGT margin < 3 degC or a stack < 1,500 cycles (lifecycle.py's rule)

Per engine: P(removal inside the horizon), removal month P10/P50/P90, the driver (EGT,
LLP or a heavy failure). For the 2-year plan:
  in scope   engines whose limit falls inside the horizon with probability >= --in-scope
  latest     the month by which the engine still has margin with probability 1 - q
             (q = --late-risk, default 20 %): the plan should induct it by then
  earliest   latest - width
  hazard     monthly probability of a forced removal (heavy failure or limit) between
             earliest and latest, from the paths; replaces the 0.06 / 0.01 constants
  watch      hazard in the top 15 %
And for the fleet: removals per month, P10/P50/P90 over paths.

The fleet state is lifecycle.py's 20-year simulation (synthetic). With real data it is
the operator's snapshot: EGT margin, trend slope and its standard error, LLP cycles left,
cycles per month.

  python removal_mc.py                                  # summary + comparison with lifecycle.window
  python removal_mc.py --fleet-out data/fleet_visits_removal_mc.json --json-out removal_mc.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import lifecycle as lc

HERE = Path(__file__).resolve().parent
HEAVY_PER_1000_EFH = 0.013
LIGHT_PER_1000_EFH = 0.017
NEVER = 10 ** 6


def simulate(state, t_now: int, horizon: int = 36, paths: int = 2000, seed: int = 0,
             rate_sigma: float = 0.2, util_sigma: float = 0.08) -> dict:
    """First limit / heavy-failure month per path and engine, counted from t_now.

    Engines in the shop at t_now are skipped (their next removal is years away)."""
    rng = np.random.default_rng(seed)
    E = lc.ENGINES
    sub = state.get("sub", np.zeros(E, dtype=int))
    since0 = state.get("since", np.full(E, 1e9))
    active = state["back"] <= t_now
    cpm = np.array([x["cycles_year"] / 12 for x in lc.SUBFLEETS])[sub]
    sev = np.array([x["severity"] for x in lc.SUBFLEETS])[sub]
    efh = np.array([x.get("fh_cycle", lc.HOURS_PER_CYCLE) for x in lc.SUBFLEETS])[sub]

    shape = (paths, E)
    rate = state["loss"] * sev * rng.lognormal(-rate_sigma ** 2 / 2, rate_sigma, shape)
    margin = np.broadcast_to(state["margin"], shape).copy()
    llp = np.broadcast_to(np.minimum(np.minimum(state["core"], state["lp"]), state["fan"]), shape).copy()
    since = np.broadcast_to(since0, shape).copy()
    limit_m = np.full(shape, NEVER)
    heavy_m = np.full(shape, NEVER)
    light_n = np.zeros((paths, horizon))
    gone = np.broadcast_to(~active, shape).copy()  # removed (or in the shop) for the rest of the path

    for t in range(horizon):
        up = ~gone
        n_up = up.sum(axis=1, keepdims=True)
        fly_p = np.minimum(1.0, lc.needed_positions(t) / np.maximum(n_up, 1))
        flying = up & (rng.random(shape) < fly_p)
        cyc = cpm * lc.FLIGHT_INDEX[lc.month_of(t)] * np.clip(rng.normal(1, util_sigma, shape), 0.5, 1.5) * flying
        early = np.clip(1000 - since, 0, None) if lc.INITIAL_DROP else np.zeros(shape)
        margin -= lc.INITIAL_DROP * np.minimum(cyc, early) / 1000 + rate * np.maximum(0, cyc - early)
        since += cyc
        llp -= cyc
        hours = cyc * efh
        heavy = flying & (rng.random(shape) < HEAVY_PER_1000_EFH * hours / 1000)
        light_n[:, t] = (flying & ~heavy & (rng.random(shape) < LIGHT_PER_1000_EFH * hours / 1000)).sum(axis=1)
        at_limit = flying & ((margin < lc.MIN_MARGIN) | (llp < lc.MIN_LLP))
        heavy_m[heavy & ~at_limit] = t
        limit_m[at_limit] = t
        gone |= heavy | at_limit
    driver = np.where(heavy_m < limit_m, 2, np.where(margin < lc.MIN_MARGIN, 0, 1))  # 0 EGT, 1 LLP, 2 heavy
    return {"limit": limit_m, "heavy": heavy_m, "driver": driver, "light": light_n, "active": active,
            "horizon": horizon, "cpm": cpm, "efh": efh, "sub": sub, "core": state["core"], "lp": state["lp"], "fan": state["fan"]}


def plan_rows(sim: dict, window_months: int = 24, in_scope: float = 0.5, late_risk: float = 0.2,
              width: int = 5) -> list[dict]:
    """Input rows for the 2-year optimisation, one per engine in scope."""
    limit, heavy = sim["limit"], sim["heavy"]
    forced = np.minimum(limit, heavy)  # the engine leaves the wing, planned or not
    run_cycles = (lc.RESTORE["PR"] - lc.INITIAL_DROP) / (lc.EGT_LOSS_PER_1000 / 1000)
    rows = []
    for e in np.nonzero(sim["active"])[0]:
        p_in = float((limit[:, e] < window_months).mean())
        if p_in < in_scope:
            continue
        lm = limit[:, e]
        latest = int(min(window_months - 1, np.quantile(lm, late_risk)))
        earliest = max(0, latest - width)
        # monthly hazard of a forced removal while the engine waits inside its window
        at_risk = np.clip(np.minimum(forced[:, e] + 1, latest + 1) - earliest, 0, None).sum()  # the event month counts
        events = ((forced[:, e] >= earliest) & (forced[:, e] <= latest)).sum()  # heavy failure or limit first
        # never below the heavy-failure rate of a flying engine (the scenario sampler needs > 0)
        floor = HEAVY_PER_1000_EFH * float(sim["cpm"][e] * sim["efh"][e]) / 1000
        hazard = max(floor, float(events / at_risk) if at_risk else 0.0)
        med = float(np.median(lm))
        cpm = float(sim["cpm"][e])
        ws = lc.workscope(sim["core"][e] - med * cpm, sim["lp"][e] - med * cpm, run_cycles, sim["fan"][e] - med * cpm)
        drv = sim["driver"][:, e]
        rows.append({
            "esn": f"{lc.ESN_PREFIX}-{101 + e:03d}",
            "operator": lc.SUBFLEETS[int(sim["sub"][e])]["name"],
            "window": [earliest, latest],
            "allowed_workscopes": {"PR": ["PR", "CORE"], "CORE": ["CORE", "FULL"], "FULL": ["FULL"]}[ws],
            "hazard": round(hazard, 4),
            "p_in_horizon": round(p_in, 3),
            "removal_p10_p50_p90": [int(np.quantile(lm, q)) if np.quantile(lm, q) < NEVER else None for q in (0.1, 0.5, 0.9)],
            "driver_share": {"EGT": round(float((drv == 0).mean()), 3), "LLP": round(float((drv == 1).mean()), 3),
                             "heavy_failure": round(float((drv == 2).mean()), 3)},
        })
    if rows:
        cut = np.quantile([r["hazard"] for r in rows], 0.85)
        for r in rows:
            r["watch"] = bool(r["hazard"] >= cut)
    return rows


def fleet_forecast(sim: dict, window_months: int = 24) -> dict:
    """Removals per month over the paths (planned-at-limit + heavy + light)."""
    limit, heavy = sim["limit"], sim["heavy"]
    forced = np.minimum(limit, heavy)
    T = window_months
    by_month = np.stack([(forced == t).sum(axis=1) for t in range(T)], axis=1) + sim["light"][:, :T]
    in_window = (forced < T).sum(axis=1)
    q = lambda a: [float(np.quantile(a, x)) for x in (0.1, 0.5, 0.9)]  # noqa: E731
    return {
        "removals_by_month_p10_p50_p90": [q(by_month[:, t]) for t in range(T)],
        "shop_visits_in_window_p10_p50_p90": q(in_window),
        "heavy_in_window_p10_p50_p90": q((heavy < np.minimum(limit, T)).sum(axis=1)),
        "light_in_window_mean": float(sim["light"][:, :T].sum(axis=1).mean()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7, help="lifecycle seed (the fleet state)")
    ap.add_argument("--mc-seed", type=int, default=0)
    ap.add_argument("--paths", type=int, default=2000)
    ap.add_argument("--rate-sigma", type=float, default=0.2, help="error of the estimated deterioration rate (no_source)")
    ap.add_argument("--util-sigma", type=float, default=0.08, help="month-to-month utilisation noise (no_source)")
    ap.add_argument("--in-scope", type=float, default=0.5, help="plan an engine if P(removal inside the window) >= this")
    # 0.1 is the natural service level, but with the sample's kits on hand it front-loads more
    # LLP visits than the kits allow (the 2-year SAA is infeasible without emergency kits)
    ap.add_argument("--late-risk", type=float, default=0.2, help="accepted chance that the engine hits its limit before 'latest'")
    ap.add_argument("--width", type=int, default=5)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--fleet-out", type=Path, help="write the 2-year window input (fleet_visits format)")
    args = ap.parse_args(argv)

    _visits, _shelf, _short, state, T = lc.simulate(args.seed)
    det = {r["esn"]: r for r in lc.window(state, T)}
    sim = simulate(state, T, horizon=36, paths=args.paths, seed=args.mc_seed,
                   rate_sigma=args.rate_sigma, util_sigma=args.util_sigma)
    rows = plan_rows(sim, 24, args.in_scope, args.late_risk, args.width)
    fc = fleet_forecast(sim, 24)
    mc = {r["esn"]: r for r in rows}

    # engines the two methods disagree on, and how the windows move
    only_det = sorted(set(det) - set(mc))
    only_mc = sorted(set(mc) - set(det))
    both = sorted(set(det) & set(mc))
    shift = [mc[e]["window"][1] - det[e]["window"][1] for e in both]
    border = [r for r in rows if r["p_in_horizon"] < 0.8]
    print(f"engines in the 2-year plan: mean-path {len(det)}, Monte Carlo {len(mc)} "
          f"(only mean-path {len(only_det)}, only MC {len(only_mc)})")
    print(f"shop visits in the window over the paths: P10/P50/P90 "
          + " / ".join(f"{x:.0f}" for x in fc["shop_visits_in_window_p10_p50_p90"])
          + f"  (heavy failures {' / '.join(f'{x:.0f}' for x in fc['heavy_in_window_p10_p50_p90'])}, "
          f"light repairs mean {fc['light_in_window_mean']:.1f})")
    if shift:
        print(f"latest month vs the mean path: earlier {sum(s < 0 for s in shift)}, same {sum(s == 0 for s in shift)}, "
              f"later {sum(s > 0 for s in shift)} (mean {np.mean(shift):+.1f} months)")
    hz = [r["hazard"] for r in rows]
    print(f"hazard per month from the paths: median {np.median(hz):.3f}, top 15 % >= {np.quantile(hz, 0.85):.3f} "
          f"(mean-path constants: 0.01 / 0.06)")
    print(f"borderline engines (P(inside window) 50-80 %): {len(border)}")
    print("\n  esn      P(in)  removal P10/P50/P90   window   hazard  driver")
    for r in sorted(rows, key=lambda r: r["window"][1])[:12]:
        d = max(r["driver_share"], key=r["driver_share"].get)
        p = "/".join("-" if x is None else str(x) for x in r["removal_p10_p50_p90"])
        dw = det.get(r["esn"], {}).get("window")
        print(f"  {r['esn']}  {r['p_in_horizon']:>5.0%}  {p:<18}  {str(r['window']):<8} {r['hazard']:.3f}  {d}"
              + (f"   (mean path {dw})" if dw else "   (not in the mean-path plan)"))

    if args.json_out:
        args.json_out.write_text(json.dumps({
            "assumptions": {"paths": args.paths, "rate_sigma": args.rate_sigma, "util_sigma": args.util_sigma,
                            "heavy_per_1000_efh": HEAVY_PER_1000_EFH, "light_per_1000_efh": LIGHT_PER_1000_EFH,
                            "in_scope": args.in_scope, "late_risk": args.late_risk, "width": args.width,
                            "no_source": ["rate_sigma", "util_sigma"]},
            "fleet": fc, "engines": rows, "only_mean_path": only_det, "only_mc": only_mc,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.fleet_out:
        base = json.loads((HERE / "data" / "fleet_visits_lifecycle.json").read_text(encoding="utf-8"))
        base["engines"] = [{k: r[k] for k in ("esn", "operator", "window", "allowed_workscopes", "watch", "hazard")} for r in rows]
        base["unscheduled_removals"]["background_engines"] = lc.ENGINES - len(rows)
        base["meta"]["description"] = (
            f"Removal plan from a Monte Carlo of the lifecycle.py fleet state ({args.paths} paths): "
            f"{len(rows)} engines with P(removal in 24 months) >= {args.in_scope:.0%}, windows end where the "
            f"chance of reaching the limit first is {args.late_risk:.0%}."
        )
        base["meta"]["generator"] = "removal_mc.py"
        args.fleet_out.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
