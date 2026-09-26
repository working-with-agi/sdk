"""Should we hurry? Decision deadlines and cost-of-timing curves per engine.

For a given plan, each engine gets
  deadline   the last month the decision can wait: induction month minus the
             longest lead time it depends on (shop slot booking, LLP kit order
             when the kits on hand are already committed to earlier visits)
  curve      expected total cost / AOG probability if the engine is inducted in
             month t instead (other engines fixed; shop, workscope and expedite
             re-chosen among options that keep capacity, kit and budget limits)
  hurry      extra cost of inducting at the earliest month
  wait       extra cost of inducting at the latest month
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from .data import Option, Problem  # noqa: F401
from .evaluate import evaluate
from .model import Plan
from .scenarios import ScenarioSet


def _blocker(p: Problem, sc: ScenarioSet, idx: list[int], exp_cost: np.ndarray) -> str | None:
    """None if the plan keeps every company constraint, else the first one it breaks."""
    chosen = [sc.options[i] for i in idx]
    for k in p.shops:
        for t in range(p.horizon):
            if sum(1 for o in chosen if o.shop is k and o.month <= t < o.month + o.tat()) > k.slots:
                return "工場枠"
    early = sum(1 for o in chosen if o.workscope in p.llp_workscopes and o.month < p.llp_kit_lead_months)
    if early > p.llp_kits_on_hand:
        return "LLP キット"
    for fy, budget in p.budget_by_fy.items():
        if sum(exp_cost[i] for i in idx if p.fiscal_year(sc.options[i].month) == fy) > budget + 1e-6:
            return f"{fy} 予算"
    return None


def lead_times(p: Problem, chosen: list[Option]) -> dict[str, list[tuple[str, int]]]:
    """Lead times each engine's decision depends on: [(reason, months)]."""
    llp = sorted((o for o in chosen if o.workscope in p.llp_workscopes), key=lambda o: o.month)
    stock_users = {o.visit.esn for o in llp[: p.llp_kits_on_hand]}
    out = {}
    for o in chosen:
        leads = [("工場の枠予約", o.shop.booking_lead_months)]
        if o.workscope in p.llp_workscopes and o.visit.esn not in stock_users:
            leads.append(("LLP キット発注", p.llp_kit_lead_months))
        out[o.visit.esn] = leads
    return out


def analyse(p: Problem, plan: Plan, sc: ScenarioSet) -> dict:
    exp_cost = sc.cost.mean(axis=0)
    chosen = [sc.options[i] for i in plan.chosen]
    base = evaluate(p, plan, sc)
    leads = lead_times(p, chosen)
    engines = []
    for i_star in sorted(plan.chosen, key=lambda i: sc.options[i].month):
        o_star = sc.options[i_star]
        v = o_star.visit
        others = [i for i in plan.chosen if i != i_star]
        curve = []
        for t in range(v.earliest, min(v.latest, p.horizon - 1) + 1):
            best, blockers = None, set()
            for i, o in enumerate(sc.options):
                if o.visit is not v or o.month != t:
                    continue
                trial = others + [i]
                why = _blocker(p, sc, trial, exp_cost)
                if why:
                    blockers.add(why)
                    continue
                ev = evaluate(p, replace(plan, chosen=trial), sc)
                if best is None or ev.mean < best[0].mean:
                    best = (ev, o)
            curve.append({
                "month": t,
                "label": p.month_label(t),
                "feasible": best is not None,
                "mean": best[0].mean if best else None,
                "aog_prob": best[0].aog_prob if best else None,
                "choice": f"{best[1].workscope}@{best[1].shop.id}{'+特急' if best[1].rush else ''}" if best else None,
                "peak": p.is_peak(t),
                "blocked_by": None if best else "・".join(sorted(blockers)),
            })
        lead_reason, lead = max(leads[v.esn], key=lambda r: r[1])
        deadline = o_star.month - lead
        feasible = [c for c in curve if c["feasible"]]
        first, last = feasible[0], feasible[-1]
        engines.append({
            "esn": v.esn,
            "window": [v.earliest, v.latest],
            "window_labels": [p.month_label(v.earliest), p.month_label(v.latest)],
            "planned_month": o_star.month,
            "planned_label": p.month_label(o_star.month),
            "planned_choice": f"{o_star.workscope}@{o_star.shop.id}{'+特急' if o_star.rush else ''}",
            "leads": [{"reason": r, "months": m} for r, m in leads[v.esn]],
            "binding_lead": {"reason": lead_reason, "months": lead},
            "deadline": deadline,
            "deadline_label": p.month_label(max(0, deadline)),
            "months_to_deadline": deadline,
            "status": "now" if deadline <= 0 else ("soon" if deadline <= 3 else "can_wait"),
            "slack_to_limit": v.latest - o_star.month,
            "hurry_cost": first["mean"] - base.mean,
            "hurry_month": first["label"],
            "wait_cost": last["mean"] - base.mean,
            "wait_month": last["label"],
            "curve": curve,
        })
    return {
        "base_mean": base.mean,
        "now_count": sum(1 for e in engines if e["status"] == "now"),
        "engines": engines,
    }
