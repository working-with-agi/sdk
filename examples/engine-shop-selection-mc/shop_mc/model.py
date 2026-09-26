"""Two-stage stochastic MILP, solved by sample average approximation (SAA).

First stage (decided now, before uncertainty is revealed):
  x[i]  in {0,1}  option i = (engine, shop, workscope, induction month)
  S     in Z+     long-term spare engines leased for the whole horizon

Second stage (per scenario s and month t, after costs / delays / removals are known):
  l[s,t] >= 0     short-term lease engines (<= cap)
  a[s,t] >= 0     uncovered positions (AOG)

  min  c_S*S*T - sum_i V_w(i) x[i]
       + 1/N sum_s ( sum_i cost[s,i] x[i] + sum_t (c_l l[s,t] + c_aog a[s,t]) )
       [+ lambda * CVaR_alpha(total cost)]
  s.t. sum_{i of engine e} x[i] = 1                                   (each visit planned once)
       sum_{i at shop k, in shop at t (quoted TAT)} x[i] <= slots_k   (planned capacity)
       owned - sum_i A[s,i,t] x[i] - U[s,t] + S + l[s,t] + a[s,t] >= D  (coverage)

A[s,i,t] = 1 if option i keeps its engine off-wing at month t in scenario s.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pulp

from .data import Problem
from .scenarios import ScenarioSet


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
    l = {(s, t): pulp.LpVariable(f"l_{s}_{t}", 0, p.short_lease_max) for s in range(N) for t in range(T)}
    a = {(s, t): pulp.LpVariable(f"a_{s}_{t}", 0) for s in range(N) for t in range(T)}

    # each planned visit happens exactly once
    for v in p.visits:
        prob += pulp.lpSum(x[i] for i, o in enumerate(opts) if o[0] is v) == 1, f"visit_{v.esn}"

    # planned shop capacity (quoted TAT)
    for k in p.shops:
        for t in range(T):
            occ = [
                x[i]
                for i, (v, kk, w, t0) in enumerate(opts)
                if kk is k and t0 <= t < t0 + kk.quotes[w].tat
            ]
            if occ:
                prob += pulp.lpSum(occ) <= k.slots, f"cap_{k.id}_{t}"

    # coverage per scenario and month
    start = np.array([o[3] for o in opts])
    for s in range(N):
        end = start + sc.down[s]
        for t in range(T):
            off = np.nonzero((start <= t) & (t < end))[0]
            prob += (
                p.owned_engines - pulp.lpSum(x[i] for i in off) - sc.unsched[s, t]
                + S + l[s, t] + a[s, t] >= p.installed_positions
            ), f"cover_{s}_{t}"

    first_stage = p.long_spare_cost * T * S - pulp.lpSum(
        p.build_value.get(o[2], 0.0) * x[i] for i, o in enumerate(opts)
    )
    scen_cost = [
        pulp.lpSum(sc.cost[s, i] * x[i] for i in range(len(opts)))
        + pulp.lpSum(p.short_lease_cost * l[s, t] + p.aog_cost * a[s, t] for t in range(T))
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
    return Plan(
        chosen=[i for i in range(len(opts)) if (x[i].value() or 0) > 0.5],
        long_spares=round(S.value() or 0),
        objective=pulp.value(prob.objective),
        status=h.modelStatusToString(h.getModelStatus()),
        dual_bound=h.getInfo().mip_dual_bound,
    )
