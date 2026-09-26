#!/usr/bin/env python3
"""Generate a group-wide sample for one engine type: CFM56-7B on the 737-800 fleets of a
major Japanese airline group (mainline + regional subsidiary), derived from public figures.

Shop visits are planned per engine type, and within a group the same type's engines can be
pooled across operating companies, so the sample covers every 737-800 in the group.
Every number is an estimate from public information, not operator data.

Fleet
  737-800        62 mainline (Wikipedia "Japan Airlines fleet", Mar 2026)
                 14 regional subsidiary (Wikipedia "Japan Transocean Air", Nov 2025)
  positions      76 x 2 = 152
  owned engines  ~9 % spares -> 166

What the schedule needs ("normal state")
  flights        domestic demand peaks in August (Obon), March, year-end and Golden Week;
                 January-February, June and November are troughs (MLIT air transport
                 statistics; JAL Aug-2025 load factor 87 %). FLIGHT_INDEX below is an
                 estimate of that seasonal shape.
  aircraft       needed_t = min(fleet - airframe checks_t, ceil(BASE_NEEDED * index_t));
                 heavy airframe checks are concentrated in trough months.
  positions      required_t = 2 * needed_t
  shelf buffer   unscheduled removals ~ Poisson(rate * engines * mean unscheduled TAT);
                 buffer = its 95 % quantile, kept as serviceable spares on the shelf.

Shop visits
  run length     mature CFM56-7B runs ~10,000-15,000 cycles at ~2,000 cycles/aircraft-year
                 -> one visit per engine every ~5-7 years -> 166 / 6 ~ 28 a year -> 54 in 24 months
  risk           each engine may fail in service once it is past its earliest removal month
                 (monthly hazard); ~15 % are on the watch list with a much higher hazard.

Run:  python data/generate_fleet.py > data/fleet_visits.json
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np

START_YEAR, START_MONTH = 2026, 10
HORIZON = 24
FLEET = {"mainline": 62, "regional": 14}
AIRCRAFT = sum(FLEET.values())
OWNED_ENGINES = 166
N_VISITS = 54

# seasonal flight index by calendar month (1.00 = average month)
FLIGHT_INDEX = {1: 0.90, 2: 0.88, 3: 1.06, 4: 0.97, 5: 1.02, 6: 0.90,
                7: 1.02, 8: 1.12, 9: 0.98, 10: 1.00, 11: 0.96, 12: 1.03}
# aircraft in heavy airframe checks, by calendar month (done in troughs)
AIRFRAME_CHECKS = {1: 6, 2: 6, 3: 2, 4: 4, 5: 2, 6: 6, 7: 3, 8: 2, 9: 4, 10: 4, 11: 6, 12: 2}
BASE_NEEDED = 68  # aircraft the schedule needs in an average month, incl. operational spares

UNSCHED_RATE = 0.004         # unscheduled removals per engine-month (MTBUR ~ 250 months)
UNSCHED_TAT = ([2, 3, 4], [0.3, 0.5, 0.2])
DEFAULT_HAZARD = 0.01        # monthly failure probability past the earliest removal month
WATCH_HAZARD = 0.06
WATCH_SHARE = 0.15

# Budgets by fiscal year (April start). Set a few % below what the cost-minimal plan
# without a budget would spend (~40.7k / 104k / 108k); the total (254k) is above the
# lowest achievable spend (~251.5k), so the budget can be met only by moving visits
# between fiscal years, which costs green time and buffer.
BUDGETS = {"FY2026": 40000, "FY2027": 108000, "FY2028": 106000}

CLASSES = [
    (("PR", "CORE"), 0.40),
    (("CORE", "FULL"), 0.30),
    (("FULL",), 0.12),
    (("PR", "CORE", "FULL"), 0.18),
]


def month_of(t: int) -> int:
    return (START_MONTH - 1 + t) % 12 + 1


def poisson_quantile(mean: float, q: float) -> int:
    k, term = 0, math.exp(-mean)
    cdf = term
    while cdf < q:
        k += 1
        term *= mean / k
        cdf += term
    return k


def main() -> None:
    rng = np.random.default_rng(2026)

    needed = [
        min(AIRCRAFT - AIRFRAME_CHECKS[month_of(t)], math.ceil(BASE_NEEDED * FLIGHT_INDEX[month_of(t)]))
        for t in range(HORIZON)
    ]
    required = [2 * n for n in needed]
    mean_tat = sum(d * p for d, p in zip(*UNSCHED_TAT))
    mean_out = UNSCHED_RATE * OWNED_ENGINES * mean_tat
    buffer = poisson_quantile(mean_out, 0.95)

    classes = rng.choice(len(CLASSES), size=N_VISITS, p=[c[1] for c in CLASSES])
    earliest = np.sort(rng.integers(0, HORIZON - 3, size=N_VISITS))
    width = rng.integers(3, 7, size=N_VISITS)
    watch = rng.random(N_VISITS) < WATCH_SHARE
    regional = rng.random(N_VISITS) < FLEET["regional"] / AIRCRAFT
    engines = []
    for j in range(N_VISITS):
        e0 = int(earliest[j])
        engines.append({
            "esn": f"896-{101 + j:03d}",
            "operator": "regional" if regional[j] else "mainline",
            "window": [e0, int(min(HORIZON - 1, e0 + width[j]))],
            "allowed_workscopes": list(CLASSES[classes[j]][0]),
            "watch": bool(watch[j]),
            "hazard": WATCH_HAZARD if watch[j] else DEFAULT_HAZARD,
        })

    fleet = {
        "meta": {
            "description": (
                "Group-wide synthetic sample for one engine type (CFM56-7B class): 76 x 737-800 "
                "(62 mainline + 14 regional), 152 positions, 166 owned engines (~9% spares), 54 planned "
                "shop visits over 24 months from 2026-10. Demand, buffer and risks derived from public "
                "figures; not operator data."
            ),
            "units": {"money": "k$ (home-currency equivalent at today's FX rate)", "time": "month"},
            "generator": "data/generate_fleet.py",
            "derivation": {
                "aircraft": FLEET,
                "flight_index": FLIGHT_INDEX,
                "airframe_checks": AIRFRAME_CHECKS,
                "base_aircraft_needed": BASE_NEEDED,
                "aircraft_needed_by_month": needed,
                "unscheduled_mean_engines_out": round(mean_out, 2),
                "buffer_quantile": 0.95,
            },
        },
        "start": f"{START_YEAR}-{START_MONTH:02d}",
        "horizon_months": HORIZON,
        "required_positions": required,
        "buffer_spares": [buffer] * HORIZON,
        "owned_engines": OWNED_ENGINES,
        "short_term_lease": {"cost_per_month": 190, "max_engines": 4, "max_engines_peak": 2},
        "long_term_spare": {"cost_per_month": 120, "max_engines": 6},
        # uncovered engine positions cancel the lowest-margin flying first
        # (cost per engine-month = half an aircraft's lost contribution)
        "aog_tiers": [
            {"engines": 2, "cost_per_month": 700, "what": "extra sections / low-margin off-peak flights"},
            {"engines": 4, "cost_per_month": 1400, "what": "regional and leisure routes"},
            {"engines": None, "cost_per_month": 2600, "what": "trunk routes"},
        ],
        "aog_peak_multiplier": {"12": 1.4, "1": 1.4, "3": 1.2, "5": 1.3, "7": 1.6, "8": 1.8},
        "unscheduled_removals": {
            "rate_per_engine_month": UNSCHED_RATE,
            "background_engines": OWNED_ENGINES - N_VISITS,
            "tat_months": UNSCHED_TAT[0],
            "tat_probs": UNSCHED_TAT[1],
            "failure_cost_factor": 1.3,
            "failure_extra_months": 1,
        },
        "workscope_build_value": {"PR": 0, "CORE": 2400, "FULL": 6200},
        "green_time_value_per_month": 45,
        "llp_kits": {"workscopes": ["CORE", "FULL"], "lead_time_months": 8, "on_hand": 8, "emergency_premium": 900},
        "service_target": {"max_aog_prob": 0.05},
        "budget": {"fiscal_year_start_month": 4, "by_fiscal_year": BUDGETS},
        "fx": {"volatility": 0.10},
        "engines": engines,
    }
    json.dump(fleet, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
