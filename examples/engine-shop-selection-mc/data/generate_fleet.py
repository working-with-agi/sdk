#!/usr/bin/env python3
"""Generate a major-airline-scale sample for one engine type (CFM56-7B on a 737-800 fleet).

Shop visits are planned per engine type, so the sample models one type at the
scale of a large Japanese network carrier. Every number is an estimate from
public information, not operator data:

  aircraft         62 x 737-800 (JAL mainline, Wikipedia "Japan Airlines fleet", Mar 2026)
  installed        62 x 2 = 124 engine positions
  owned engines    ~9 % spares  -> 136
  utilisation      ~2,000 cycles / aircraft-year on domestic / regional routes
  shop visit run   ~10,000-15,000 cycles for mature CFM56-7B runs (Aircraft Commerce
                   CFM56-7B guides) -> one visit every ~5-7 years per engine
  visits           136 / 6 years ~ 22 per year -> 44 in a 24-month horizon
  costs            performance restoration ~$2.1-2.8M, LLP stack $2.5-6M
                   (public 2026 shop-visit benchmarks); shop quotes in data/shop_quotes.json

Run:  python data/generate_fleet.py > data/fleet_visits.json
"""

from __future__ import annotations

import json
import sys

import numpy as np

N_VISITS = 44
HORIZON = 24

# engine condition classes -> allowed workscopes (share of fleet)
CLASSES = [
    (("PR", "CORE"), 0.40),          # EGT margin driven, core LLPs have some life left
    (("CORE", "FULL"), 0.30),        # core LLPs near limit
    (("FULL",), 0.12),               # all LLP stacks near limit / AD-driven full overhaul
    (("PR", "CORE", "FULL"), 0.18),  # flexible
]


def main() -> None:
    rng = np.random.default_rng(2026)
    classes = rng.choice(len(CLASSES), size=N_VISITS, p=[c[1] for c in CLASSES])
    # removal windows spread over the horizon; ~5-month windows (earliest removal
    # when the engine becomes a candidate, latest = hard limit)
    earliest = np.sort(rng.integers(0, HORIZON - 3, size=N_VISITS))
    width = rng.integers(3, 7, size=N_VISITS)
    engines = []
    for j in range(N_VISITS):
        e0 = int(earliest[j])
        e1 = int(min(HORIZON - 1, e0 + width[j]))
        engines.append({
            "esn": f"896-{101 + j:03d}",
            "window": [e0, e1],
            "allowed_workscopes": list(CLASSES[classes[j]][0]),
        })
    fleet = {
        "meta": {
            "description": (
                "Major-airline-scale synthetic sample: one engine type (CFM56-7B class) on a "
                "62-aircraft 737-800 fleet, 124 installed positions, 136 owned engines (~9% spares), "
                "44 planned shop visits over 24 months from 2026-10. Estimates from public "
                "information; not operator data."
            ),
            "units": {"money": "k$ (home-currency equivalent at today's FX rate)", "time": "month"},
            "generator": "data/generate_fleet.py",
        },
        "start": "2026-10",
        "horizon_months": HORIZON,
        "installed_positions": 124,
        "owned_engines": 136,
        "short_term_lease": {"cost_per_month": 190, "max_engines": 4, "max_engines_peak": 2},
        "long_term_spare": {"cost_per_month": 120, "max_engines": 6},
        "aog_cost_per_month": 1500,
        "aog_peak_multiplier": {"12": 1.4, "1": 1.4, "3": 1.2, "5": 1.3, "7": 1.6, "8": 1.8},
        "unscheduled_removals": {"rate_per_engine_month": 0.004, "tat_months": [2, 3, 4], "tat_probs": [0.3, 0.5, 0.2]},
        "workscope_build_value": {"PR": 0, "CORE": 2400, "FULL": 6200},
        "green_time_value_per_month": 45,
        "llp_kits": {"workscopes": ["CORE", "FULL"], "lead_time_months": 8, "on_hand": 6, "emergency_premium": 900},
        "service_target": {"max_aog_prob": 0.05},
        "budget": {
            "fiscal_year_start_month": 4,
            # the cost-minimal plan without a budget spends ~17k / 115k / 69k (FY2026 is only
            # Oct-Mar); FY2027-28 budgets are set a few % tighter than that, as budgets usually are
            "by_fiscal_year": {"FY2026": 30000, "FY2027": 110000, "FY2028": 62000},
        },
        "fx": {"volatility": 0.10},
        "engines": engines,
    }
    json.dump(fleet, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
