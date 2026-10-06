#!/usr/bin/env python3
"""Airport layer: the hub's slots -> the slots a company can put on the trunk -> the bounds the
airline's fleet assignment must respect, and the share of each route's passengers the company's
frequencies win against the other carriers.

`data/hnd_slots.json` holds the hub's domestic slots (465 a day, 1 slot = 1 round trip), each
company's allocation, the rules (regional slots cannot fly the trunk, small-route rules, use it or
lose it, re-allocation every five years with about 5 % recovered, next in 2028), and the trunk
frequencies by company with the other carriers summed (sources in the file).

  trunk_budget(cid, delta)  round trips a day the company flies on the four hub trunk routes,
                            today's schedule + delta (a re-allocation scenario lands on the trunk)
  bounds(cid, delta)        per-route min/max round trips (today's ± flex; wider when delta is large)
  destination_caps(cid)     the airport at the other end: today's frequency + the company's headroom
                            there (data/destination_airports.json), laid over the bounds on request
  share(cid, freq)          the company's share of each route's passengers from frequencies
                            (S-curve with exponent alpha; alpha = 1 is proportional)

The airline layer (route_fleet.py) turns these into constraints: legs a day per route within the
bounds, the hub routes' round trips within the budget and at least use_min_share of it.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLOTS = HERE / "data" / "hnd_slots.json"
DEST = HERE / "data" / "destination_airports.json"
HUB_ROUTES = ("HND-CTS", "HND-ITM", "HND-FUK", "HND-OKA")


def load() -> dict:
    return json.loads(SLOTS.read_text(encoding="utf-8"))


def current_freq(S: dict, cid: str) -> dict[str, float]:
    """Today's round trips a day per trunk route for the company (2026 where known, else 2023-03)."""
    f = S["trunk_frequencies"]
    out = {r: f["as_of_2026"].get(r, {}).get(cid, f["as_of_2023_03"][r][cid]) for r in HUB_ROUTES}
    out["FUK-OKA"] = f["FUK-OKA"][cid]
    return out


def others_freq(S: dict) -> dict[str, float]:
    f = S["trunk_frequencies"]
    out = {r: f["as_of_2023_03"][r]["others"] for r in HUB_ROUTES}
    out["FUK-OKA"] = f["FUK-OKA"]["others"]
    return out


def competitor_freq(S: dict, cid: str) -> dict[str, float]:
    """Everyone else on the route: the other large company plus the others."""
    f = S["trunk_frequencies"]
    rival = "ana" if cid == "jal" else "jal"
    cur_r = current_freq(S, rival)
    oth = others_freq(S)
    return {r: cur_r[r] + oth[r] for r in cur_r}


def share(S: dict, cid: str, freq: dict[str, float], alpha: float | None = None) -> dict[str, float]:
    a = S["share_model"]["alpha"] if alpha is None else alpha
    comp = competitor_freq(S, cid)
    return {r: (freq[r] ** a) / (freq[r] ** a + comp[r] ** a) if freq[r] > 0 else 0.0 for r in freq}


def trunk_budget(S: dict, cid: str, delta: float = 0.0) -> float:
    return sum(current_freq(S, cid)[r] for r in HUB_ROUTES) + delta


def load_destinations() -> dict:
    return json.loads(DEST.read_text(encoding="utf-8"))


def destination_caps(S: dict, cid: str, dest: dict | None = None) -> dict[str, float]:
    """Per hub route, the most round trips a day the airport at the other end lets the company fly:
    today's frequency + the company's headroom there (no_source). Routes touching two capped
    airports take the tighter one."""
    dest = dest or load_destinations()
    cur = current_freq(S, cid)
    out = {}
    for a in dest["airports"].values():
        for r in a["routes"]:
            if r in HUB_ROUTES:
                out[r] = min(out.get(r, float("inf")), cur[r] + a["headroom_round_trips"])
    return out


def bounds(S: dict, cid: str, delta: float = 0.0, dest: dict | None = None) -> dict[str, tuple[float, float]]:
    """Per-route round trips a day. FUK-OKA is bounded by its own airport (today's and the seasonal).
    dest: the destination airports' caps (destination_caps) laid over the hub-side upper bounds."""
    cur = current_freq(S, cid)
    flex = S["trunk_frequencies"]["flex_round_trips"] + abs(delta) / len(HUB_ROUTES)
    out = {r: (max(1.0, cur[r] - flex), cur[r] + flex) for r in HUB_ROUTES}
    if dest:
        out = {r: (min(lo, dest.get(r, hi)), min(hi, dest.get(r, hi))) for r, (lo, hi) in out.items()}
    seasonal = S["trunk_frequencies"]["FUK-OKA"].get(f"{cid}_seasonal", cur["FUK-OKA"])
    out["FUK-OKA"] = (max(1.0, cur["FUK-OKA"] - 1), max(seasonal, cur["FUK-OKA"] + 1))
    return out


def summary(S: dict, cid: str) -> dict:
    cur = current_freq(S, cid)
    return {"allocation": S["allocation"][cid], "allocation_breakdown": S["allocation_breakdown"].get(cid),
            "trunk_round_trips": trunk_budget(S, cid), "trunk_share_of_allocation": round(trunk_budget(S, cid) / S["allocation"][cid], 3),
            "current_freq": cur, "competitor_freq": competitor_freq(S, cid), "share_now": {r: round(v, 3) for r, v in share(S, cid, cur).items()},
            "rules": S["rules"], "sources": S["sources"]}
