"""Business-level summary of a plan, and the difference between two summaries.

The baseline (the annual figures everyone implicitly agrees on) is one summary;
every use case answers "how does this change it?" as a diff against it.
"""

from __future__ import annotations

from .data import Problem
from .evaluate import evaluate
from .model import Plan
from .scenarios import ScenarioSet

WORKSCOPES_SHOWN = ("PR", "CORE", "FULL", "GT", "PO")


def summarize(p: Problem, plan: Plan, sc: ScenarioSet) -> dict:
    ev = evaluate(p, plan, sc)
    chosen = [sc.options[i] for i in plan.chosen]
    exp = sc.cost.mean(axis=0)
    by_fy: dict[str, dict] = {}
    for i in plan.chosen:
        o = sc.options[i]
        fy = p.fiscal_year(o.month)
        row = by_fy.setdefault(fy, {"visits": 0, "spend": 0.0, **{w: 0 for w in WORKSCOPES_SHOWN}})
        row["visits"] += 1 if o.workscope not in ("PO",) else 0
        row["spend"] += float(exp[i])
        if o.workscope in row:
            row[o.workscope] += 1
    shops: dict[str, int] = {}
    for o in chosen:
        shops[o.shop.id] = shops.get(o.shop.id, 0) + 1
    return {
        "total_cost": ev.mean,
        "p90": ev.p90,
        "aog_prob": ev.aog_prob,
        "by_fiscal_year": dict(sorted(by_fy.items())),
        "shop_visits": sum(1 for o in chosen if o.workscope not in ("GT", "PO")),
        "midlife_swaps": sum(1 for o in chosen if o.workscope == "GT"),
        "partouts": sum(1 for o in chosen if o.workscope == "PO"),
        "long_spares": plan.long_spares,
        "emergency_kits": plan.emergency_kits,
        "early_months": sum(o.visit.latest - o.month for o in chosen if o.workscope != "PO"),
        "rush": sum(1 for o in chosen if o.rush),
        "shops": dict(sorted(shops.items())),
    }


def diff(base: dict, new: dict) -> dict:
    """new - base, field by field (fiscal years and shops aligned by key)."""
    out = {}
    for k in ("total_cost", "p90", "aog_prob", "shop_visits", "midlife_swaps", "partouts",
              "long_spares", "emergency_kits", "early_months", "rush"):
        out[k] = new[k] - base[k]
    fys = sorted(set(base["by_fiscal_year"]) | set(new["by_fiscal_year"]))
    zero = {"visits": 0, "spend": 0.0}
    out["by_fiscal_year"] = {
        fy: {m: new["by_fiscal_year"].get(fy, zero).get(m, 0) - base["by_fiscal_year"].get(fy, zero).get(m, 0)
             for m in ("visits", "spend")}
        for fy in fys
    }
    shops = sorted(set(base["shops"]) | set(new["shops"]))
    out["shops"] = {s: new["shops"].get(s, 0) - base["shops"].get(s, 0) for s in shops}
    return out
