"""Human- and agent-readable reporting of a Solution."""

from __future__ import annotations

import json
from dataclasses import asdict

from .data import FleetData
from .model import Solution

COST_LABELS = {
    "shop_visits": "Shop visits",
    "spare_lease": "Spare engine lease",
    "engine_changes": "Engine changes (install)",
    "aog": "AOG penalty",
    "fuel_deterioration": "Fuel burn (EGT deterioration)",
    "terminal_value": "Terminal asset value (credit)",
}


def gantt(data: FleetData, sol: Solution) -> str:
    """One row per engine. '=' flying, '.' spare, workscope letter in shop, '#' pre-existing visit."""
    T = data.horizon
    rows = []
    ruler = "".join(str((t // 10) % 10) if t % 10 == 0 else " " for t in range(T))
    rows.append(f"{'month':>8} |{ruler}|")
    for e in data.engines:
        line = ["=" if sol.operating[e.esn][t] else "." for t in range(T)]
        for t in range(min(e.in_shop_until, T)):
            line[t] = "#"
        for v in sol.visits:
            if v.esn != e.esn:
                continue
            for t in range(v.start, min(v.start + v.tat, T)):
                line[t] = v.workscope[0]
        rows.append(f"{e.esn:>8} |{''.join(line)}|")
    lease = "".join(str(n) if n else " " for n in sol.lease)
    rows.append(f"{'lease':>8} |{lease}|")
    rows.append("legend: = flying  . spare  P/C/L/F shop visit (workscope)  # already in shop")
    return "\n".join(rows)


def text_report(data: FleetData, sol: Solution) -> str:
    out = [f"status: {sol.status}", f"objective (NPV, k$): {sol.objective:,.0f}"]
    if sol.dual_bound is not None:
        out.append(
            f"lower bound (k$): {sol.dual_bound:,.0f}   gap: {sol.abs_gap:,.0f} k$"
            + (f" ({sol.mip_gap:.1%} of net objective)" if sol.mip_gap is not None else "")
        )
    out.append("")
    out.append("cost breakdown (discounted, k$)")
    for k, v in sol.cost_breakdown.items():
        out.append(f"  {COST_LABELS.get(k, k):<34}{v:>12,.0f}")
    out.append("")
    out.append("shop visits")
    out.append(f"  {'month':>5}  {'ESN':<7} {'WS':<5} {'TAT':>3}  {'EGT':>5}  LLP remaining at removal")
    for v in sol.visits:
        llp = " ".join(f"{m}={int(c):>5}" for m, c in v.llp_before.items())
        out.append(
            f"  {v.start:>5}  {v.esn:<7} {v.workscope:<5} {v.tat:>3}  {v.egt_before:>5.1f}  {llp}"
        )
    out.append("")
    lease_months = sum(sol.lease)
    out.append(
        f"KPIs: shop visits={len(sol.visits)}  lease engine-months={lease_months}  "
        f"AOG engine-months={sum(sol.aog):.1f}"
    )
    out.append("")
    out.append(gantt(data, sol))
    return "\n".join(out)


def to_json(sol: Solution) -> str:
    payload = asdict(sol)
    payload.update(abs_gap=sol.abs_gap, mip_gap=sol.mip_gap)
    return json.dumps(payload, indent=2, ensure_ascii=False)
