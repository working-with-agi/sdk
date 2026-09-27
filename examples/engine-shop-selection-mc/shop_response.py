#!/usr/bin/env python3
"""Shop capacity response to the airline's committed volume (three scenarios).

Question: 何基を長期契約に出すと、何年後に枠がいくつ増え、単価がどう動くか。

    python3 shop_response.py jal --commit 20 --out shop_response/jal.json
    python3 shop_response.py ana --commit 10

Parameters and their sources live in data/shop_response.json. Airline volume and
shop TAT come from baselines/<airline>-2026-10.json and data/<airline>/shops.json.
Concurrent slots = visits/yr x TAT months / 12.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS_PATH = os.path.join(HERE, "data", "shop_response.json")


def load_params(path=PARAMS_PATH):
    with open(path) as f:
        return json.load(f)


def airline_inputs(airline):
    """Baseline visits/yr, visit-weighted TAT [months], contracted shop slots."""
    with open(os.path.join(HERE, "baselines", f"{airline}-2026-10.json")) as f:
        norms = json.load(f)["norms"]
    with open(os.path.join(HERE, "data", airline, "shops.json")) as f:
        shop = json.load(f)["shops"][0]
    by_ws = norms["visits_per_year_by_workscope"]
    total = sum(by_ws.values())
    tat = sum(n * shop["quotes"][ws]["tat"] for ws, n in by_ws.items()) / total
    return {
        "airline": airline,
        "visits_per_year": norms["visits_per_year"],
        "tat_months": tat,
        "shop_id": shop["id"],
        "shop_name": shop["name"],
        "slots": shop["slots"],
    }


def concurrent(visits_per_year, tat_months):
    return visits_per_year * tat_months / 12.0


def scenario_rows(key, commit, base, p, horizon):
    a = {k: v["value"] for k, v in p["assumptions"].items()}
    thr = a["commit_threshold_visits_per_year"]
    lag = a["expansion_lag_years"]
    step = a["expansion_step_visits_per_year"]
    share = commit / a["shop_total_visits_per_year"]
    extra_visits = share * step if commit >= thr else 0.0
    tat0 = base["tat_months"]
    slots0 = base["slots"]
    util_shop = util_shop_prev = a["shop_utilisation_year0"]
    price = 1.0
    rows = []
    for y in range(horizon + 1):
        tat = tat0
        extra = 0.0
        if key == "B":
            if y >= 1:
                price = 1.0 - a["long_term_price_discount"]
            if extra_visits > 0 and y >= lag:
                extra = extra_visits
        elif key == "C":
            tat = max(tat0 * (1 - a["tat_improvement_per_year"]) ** y,
                      tat0 * a["tat_floor_share"])
            util_shop = a["shop_utilisation_year0"] * tat / tat0
            if y >= 1 and util_shop_prev > a["congestion_utilisation_threshold"]:
                price *= 1 + a["congestion_price_step_per_year"]
        util_shop_prev = util_shop
        slots = slots0 + concurrent(extra, tat)
        cap_visits = slots * 12.0 / tat
        rows.append({
            "year": y,
            "airline_slots_concurrent": round(slots, 2),
            "extra_visits_per_year": round(extra, 2),
            "capacity_visits_per_year": round(cap_visits, 1),
            "tat_months": round(tat, 2),
            "price_index": round(price, 3),
            "airline_utilisation": round(concurrent(commit, tat) / slots, 3),
            "shop_utilisation": round(util_shop, 3),
        })
    return rows, extra_visits


def run(airline, commit=None, horizon=None, params=None):
    p = params or load_params()
    base = airline_inputs(airline)
    if commit is None:
        commit = round(base["visits_per_year"])
    if float(commit).is_integer():
        commit = int(commit)
    horizon = horizon or p["meta"]["horizon_years"]
    a = {k: v["value"] for k, v in p["assumptions"].items()}
    thr = a["commit_threshold_visits_per_year"]
    out = {
        "airline": airline,
        "shop": {"id": base["shop_id"], "name": base["shop_name"]},
        "inputs": {
            "baseline_visits_per_year": round(base["visits_per_year"], 2),
            "committed_visits_per_year": commit,
            "tat_months_visit_weighted": round(base["tat_months"], 2),
            "slots_concurrent_today": base["slots"],
        },
        "commit_needed_for_B": {
            "threshold_visits_per_year": thr,
            "gap_visits_per_year": max(0, thr - commit),
            "triggered": commit >= thr,
        },
        "scenarios": {},
        "commit_sweep": [],
        "params": p,
    }
    for key in ("A", "B", "C"):
        rows, extra = scenario_rows(key, commit, base, p, horizon)
        out["scenarios"][key] = {
            "name": p["scenarios"][key]["name"],
            "years": rows,
        }
    for v in (10, 15, 20, 25):
        rows, extra = scenario_rows("B", v, base, p, horizon)
        arrival = next((r["year"] for r in rows if r["extra_visits_per_year"] > 0), None)
        out["commit_sweep"].append({
            "committed_visits_per_year": v,
            "year_extra_slots_arrive": arrival,
            "extra_visits_per_year": round(extra, 2),
            "extra_slots_concurrent": round(concurrent(extra, base["tat_months"]), 2),
        })
    return out


def print_table(out):
    i = out["inputs"]
    print(f"{out['airline'].upper()}  shop={out['shop']['id']}  baseline {i['baseline_visits_per_year']} visits/yr, "
          f"commit {i['committed_visits_per_year']}/yr, TAT {i['tat_months_visit_weighted']} mo, "
          f"slots {i['slots_concurrent_today']}")
    n = out["commit_needed_for_B"]
    print(f"B trigger: threshold {n['threshold_visits_per_year']}/yr -> "
          f"{'triggered' if n['triggered'] else 'need +%d/yr' % n['gap_visits_per_year']}")
    print()
    print("year | " + " | ".join(f"{k} {out['scenarios'][k]['name']}: slots/TAT/price" for k in "ABC"))
    for y in range(len(out["scenarios"]["A"]["years"])):
        cells = []
        for k in "ABC":
            r = out["scenarios"][k]["years"][y]
            cells.append(f"{r['airline_slots_concurrent']:5.2f} / {r['tat_months']:4.2f} / {r['price_index']:.3f}")
        print(f"{y:4d} | " + " | ".join(cells))
    print()
    print("commit V | arrival year | +visits/yr | +slots (concurrent)")
    for s in out["commit_sweep"]:
        arr = s["year_extra_slots_arrive"]
        print(f"{s['committed_visits_per_year']:8d} | {str(arr) if arr is not None else 'never':12s} | "
              f"{s['extra_visits_per_year']:10.2f} | {s['extra_slots_concurrent']:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("airline", choices=["jal", "ana"])
    ap.add_argument("--commit", type=float, default=None, help="committed visits/yr (default: baseline)")
    ap.add_argument("--horizon", type=int, default=None)
    ap.add_argument("--out", default=None, help="write JSON here")
    args = ap.parse_args()
    out = run(args.airline, args.commit, args.horizon)
    print_table(out)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
