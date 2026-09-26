"""Two-stage stochastic MILP, solved by sample average approximation (SAA).

First stage (decided now, before uncertainty is revealed):
  x[i]  in {0,1}  option i = (engine, shop, workscope, induction month, expedite)
  S     in Z+     long-term spare engines leased for the whole horizon
  q[k]  >= 0      shortfall against shop k's contracted volume

Second stage (per scenario s and month t, after costs / delays / removals are known):
  l[s,t] >= 0     short-term lease engines (<= cap_t, tighter in peak months)
  a[s,t] >= 0     uncovered positions (AOG), cost c_aog,t higher in peak months

  min  c_S*S*T + sum_i F_i x[i] + sum_k pen_k q[k]
       + 1/N sum_s ( sum_i cost[s,i] x[i] + sum_t (c_l l[s,t] + c_aog,t a[s,t]) )
       [+ lambda * CVaR_alpha(total cost)]
       F_i = green_time_value * (latest - month)   (life thrown away by removing early)
             - build_value(workscope)              (life the visit builds)
  s.t. sum_{i of engine e} x[i] = 1                                   (each visit planned once)
       sum_{i at shop k, in shop at t} x[i] <= slots_k                (planned capacity)
       sum_{i needing an LLP kit, month < kit lead time} x[i] <= kits on hand
       sum_{i inducted in fiscal year y} E[cost_i] x[i] <= budget_y
       q[k] >= min_visits_k - sum_{i at shop k} x[i]                  (take-or-pay)
       owned - sum_i A[s,i,t] x[i] - U[s,t] + S + l[s,t] + a[s,t] >= D  (coverage)

A[s,i,t] = 1 if option i keeps its engine off-wing at month t in scenario s.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pulp

from .data import Option, Problem
from .scenarios import ScenarioSet


def fixed_cost(p: Problem, o: Option) -> float:
    """Scenario-independent first-stage cost of choosing option o."""
    return o.visit.green_time_value * (o.visit.latest - o.month) - p.build_value.get(o.workscope, 0.0)


class InfeasibleError(RuntimeError):
    pass


@dataclass
class Plan:
    chosen: list[int]
    """Indices into ScenarioSet.options."""
    long_spares: int
    objective: float
    """In-sample SAA objective."""
    status: str
    dual_bound: float | None = None


def solve_saa(
    p: Problem,
    sc: ScenarioSet,
    cvar_weight: float = 0.0,
    cvar_alpha: float = 0.9,
    time_limit: int = 120,
    gap: float = 1e-4,
    threads: int | None = None,
    msg: bool = False,
) -> Plan:
    T, N = p.horizon, sc.n
    opts = sc.options
    prob = pulp.LpProblem("shop_selection_saa", pulp.LpMinimize)

    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(len(opts))]
    S = pulp.LpVariable("long_spares", 0, p.long_spare_max, cat="Integer")
    l = {(s, t): pulp.LpVariable(f"l_{s}_{t}", 0, p.lease_cap_at(t)) for s in range(N) for t in range(T)}
    a = {(s, t): pulp.LpVariable(f"a_{s}_{t}", 0) for s in range(N) for t in range(T)}
    q = {k.id: pulp.LpVariable(f"shortfall_{k.id}", 0) for k in p.shops if k.min_visits}

    # each planned visit happens exactly once
    for v in p.visits:
        prob += pulp.lpSum(x[i] for i, o in enumerate(opts) if o.visit is v) == 1, f"visit_{v.esn}"

    # planned shop capacity (quoted, possibly expedited TAT)
    for k in p.shops:
        for t in range(T):
            occ = [x[i] for i, o in enumerate(opts) if o.shop is k and o.month <= t < o.month + o.tat()]
            if occ:
                prob += pulp.lpSum(occ) <= k.slots, f"cap_{k.id}_{t}"

    # LLP kits: only the kits on hand can be used before new orders arrive
    early_llp = [
        x[i] for i, o in enumerate(opts)
        if o.workscope in p.llp_workscopes and o.month < p.llp_kit_lead_months
    ]
    if early_llp:
        prob += pulp.lpSum(early_llp) <= p.llp_kits_on_hand, "llp_kits"

    # fiscal-year budget on expected shop-visit spend
    exp_cost = sc.cost.mean(axis=0)
    for fy, budget in p.budget_by_fy.items():
        spend = [exp_cost[i] * x[i] for i, o in enumerate(opts) if p.fiscal_year(o.month) == fy]
        if spend:
            prob += pulp.lpSum(spend) <= budget, f"budget_{fy}"

    # take-or-pay volume commitments
    for k in p.shops:
        if k.min_visits:
            prob += q[k.id] >= k.min_visits - pulp.lpSum(x[i] for i, o in enumerate(opts) if o.shop is k), f"volume_{k.id}"

    # coverage per scenario and month
    start = np.array([o.month for o in opts])
    for s in range(N):
        end = start + sc.down[s]
        for t in range(T):
            off = np.nonzero((start <= t) & (t < end))[0]
            prob += (
                p.owned_engines - pulp.lpSum(x[i] for i in off) - sc.unsched[s, t]
                + S + l[s, t] + a[s, t] >= p.installed_positions
            ), f"cover_{s}_{t}"

    first_stage = (
        p.long_spare_cost * T * S
        + pulp.lpSum(fixed_cost(p, o) * x[i] for i, o in enumerate(opts))
        + pulp.lpSum(k.shortfall_penalty * q[k.id] for k in p.shops if k.min_visits)
    )
    aog = [p.aog_cost_at(t) for t in range(T)]
    scen_cost = [
        pulp.lpSum(sc.cost[s, i] * x[i] for i in range(len(opts)))
        + pulp.lpSum(p.short_lease_cost * l[s, t] + aog[t] * a[s, t] for t in range(T))
        for s in range(N)
    ]
    objective = first_stage + pulp.lpSum(scen_cost) / N

    if cvar_weight > 0:
        eta = pulp.LpVariable("var_eta")
        z = [pulp.LpVariable(f"cvar_z_{s}", 0) for s in range(N)]
        for s in range(N):
            # CVaR of the *total* cost: the first-stage part is the same in every scenario
            prob += z[s] >= first_stage + scen_cost[s] - eta, f"cvar_{s}"
        objective += cvar_weight * (eta + pulp.lpSum(z) / ((1 - cvar_alpha) * N))

    prob += objective
    prob.solve(pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads))
    h = prob.solverModel
    if pulp.value(prob.objective) is None or "nfeasible" in h.modelStatusToString(h.getModelStatus()):
        raise InfeasibleError(
            f"no feasible plan ({h.modelStatusToString(h.getModelStatus())}): "
            "check budgets, LLP kits on hand and shop slots"
        )
    return Plan(
        chosen=[i for i in range(len(opts)) if (x[i].value() or 0) > 0.5],
        long_spares=round(S.value() or 0),
        objective=pulp.value(prob.objective),
        status=h.modelStatusToString(h.getModelStatus()),
        dual_bound=h.getInfo().mip_dual_bound,
    )
