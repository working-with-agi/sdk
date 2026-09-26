"""Integrated engine removal / workscope / spare-engine planning as a MILP.

Decisions (per engine e, month t, workscope w):
  x[e,t,w] in {0,1}  induct engine e into the shop at the start of month t with workscope w
  u[e,t]   in {0,1}  engine e is on-wing and flying during month t
  L[t]     in Z+     short-term spare engines leased in month t
  s[t]     >= 0      uncovered engine positions (AOG) in month t

States (start of month t, t = 0..T):
  g[e,t]   EGT margin [degC]
  r[e,m,t] remaining LLP life of module m [cycles]

States carry only upper bounds that tighten with wear and reset on a shop
visit; together with g, r >= 0 this is the standard "reset" linearisation.
Every term in the objective rewards larger g / r, so the solver always
pushes the states to their physical maximum and the relaxation is exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pulp

from .data import FleetData


@dataclass
class ShopVisit:
    esn: str
    start: int
    workscope: str
    tat: int
    egt_before: float
    llp_before: dict[str, float]


@dataclass
class Solution:
    status: str
    objective: float
    visits: list[ShopVisit]
    operating: dict[str, list[int]]
    """esn -> 0/1 per month."""
    egt: dict[str, list[float]]
    llp: dict[str, dict[str, list[float]]]
    lease: list[int]
    aog: list[float]
    cost_breakdown: dict[str, float]
    dual_bound: float | None = None
    has_solution: bool = True
    """Best proven lower bound on the objective (None if the solver does not report it)."""

    @property
    def abs_gap(self) -> float | None:
        return None if self.dual_bound is None else self.objective - self.dual_bound

    @property
    def mip_gap(self) -> float | None:
        """Relative gap (primal - dual) / |primal|, as reported by MIP solvers.

        The objective is net of a large terminal-value credit, so this ratio
        overstates the error; read it together with ``abs_gap``.
        """
        if self.abs_gap is None or self.objective == 0:
            return None
        return self.abs_gap / abs(self.objective)


class EngineMroModel:
    def __init__(self, data: FleetData):
        self.d = data
        self.prob = pulp.LpProblem("engine_mro_integrated_plan", pulp.LpMinimize)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        d = self.d
        T = range(d.horizon)
        TS = range(d.horizon + 1)
        E = d.engines
        W = d.workscopes
        M = d.modules
        p = self.prob

        # --- variables -------------------------------------------------
        self.x = {
            (e.esn, t, w.code): pulp.LpVariable(f"x_{e.esn}_{t}_{w.code}", cat="Binary")
            for e in E
            for t in T
            if t >= e.in_shop_until
            for w in W
        }
        self.u = {
            (e.esn, t): pulp.LpVariable(f"u_{e.esn}_{t}", cat="Binary")
            for e in E
            for t in T
        }
        self.g = {
            (e.esn, t): pulp.LpVariable(f"g_{e.esn}_{t}", 0, d.egt_margin_max)
            for e in E
            for t in TS
        }
        self.r = {
            (e.esn, m.name, t): pulp.LpVariable(f"r_{e.esn}_{m.name}_{t}", 0, m.llp_life)
            for e in E
            for m in M
            for t in TS
        }
        # fuel-burn penalty of a deteriorated engine that is flying
        self.f = {
            (e.esn, t): pulp.LpVariable(f"f_{e.esn}_{t}", 0) for e in E for t in T
        }
        self.L = {
            t: pulp.LpVariable(f"lease_{t}", 0, d.max_lease_engines, cat="Integer")
            for t in T
        }
        self.s = {t: pulp.LpVariable(f"aog_{t}", 0) for t in T}
        # engine installed on an aircraft in month t (start of an on-wing run)
        self.y = {
            (e.esn, t): pulp.LpVariable(f"y_{e.esn}_{t}", 0, 1) for e in E for t in T
        }

        x, u, g, r, f, L, s, y = self.x, self.u, self.g, self.r, self.f, self.L, self.s, self.y

        def xv(esn: str, t: int, code: str):
            return x.get((esn, t, code), 0)

        # engine in shop during month t (own visits + pre-existing shop time)
        def in_shop(e, t):
            expr = pulp.lpSum(
                xv(e.esn, tau, w.code)
                for w in W
                for tau in range(max(0, t - w.tat + 1), t + 1)
            )
            return expr + (1 if t < e.in_shop_until else 0)

        self._in_shop = in_shop

        # --- initial states -------------------------------------------
        for e in E:
            p += g[e.esn, 0] == e.egt_margin, f"g0_{e.esn}"
            for m in M:
                p += r[e.esn, m.name, 0] == e.llp_remaining[m.name], f"r0_{e.esn}_{m.name}"

        for e in E:
            dg = d.egt_loss_per_month(e)
            cyc = d.cycles(e)
            for t in T:
                # (1) an engine is either flying, in the shop, or a spare on the shelf;
                #     this also forbids overlapping shop visits.
                p += u[e.esn, t] + in_shop(e, t) <= 1, f"avail_{e.esn}_{t}"

                # engine change: installing an engine that was not flying last month
                prev = u[e.esn, t - 1] if t > 0 else int(e.installed)
                p += y[e.esn, t] >= u[e.esn, t] - prev, f"install_{e.esn}_{t}"

                # (2) EGT margin: wear while flying, reset by restoring workscopes
                restoring = [w for w in W if w.egt_restore_to is not None]
                p += (
                    g[e.esn, t + 1]
                    <= g[e.esn, t]
                    - dg * u[e.esn, t]
                    + pulp.lpSum(w.egt_restore_to * xv(e.esn, t, w.code) for w in restoring)
                ), f"egt_{e.esn}_{t}"
                for w in restoring:
                    if (e.esn, t, w.code) in x:
                        p += (
                            g[e.esn, t + 1]
                            <= w.egt_restore_to
                            + (d.egt_margin_max - w.egt_restore_to) * (1 - x[e.esn, t, w.code])
                        ), f"egt_reset_{e.esn}_{t}_{w.code}"

                # (3) LLP life: consume cycles while flying, reset when the stack is replaced
                for m in M:
                    replacing = [w for w in W if m.name in w.llp_replace]
                    p += (
                        r[e.esn, m.name, t + 1]
                        <= r[e.esn, m.name, t]
                        - cyc * u[e.esn, t]
                        + m.llp_life * pulp.lpSum(xv(e.esn, t, w.code) for w in replacing)
                    ), f"llp_{e.esn}_{m.name}_{t}"

                # (4) fuel penalty f >= phi * (Gmax - g) when flying
                phi = d.fuel_penalty_per_degC_month
                p += (
                    f[e.esn, t]
                    >= phi * (d.egt_margin_max - g[e.esn, t])
                    - phi * d.egt_margin_max * (1 - u[e.esn, t])
                ), f"fuel_{e.esn}_{t}"

        for t in T:
            # (5) every installed position is covered by an own engine, a lease or is AOG
            p += (
                pulp.lpSum(u[e.esn, t] for e in E) + L[t] + s[t] >= d.installed_positions
            ), f"demand_{t}"
            # (6) shop capacity
            p += pulp.lpSum(in_shop(e, t) for e in E) <= d.shop_slots, f"shop_cap_{t}"

        # --- objective -------------------------------------------------
        disc = {t: d.discount(t) for t in TS}
        self.cost_terms = {
            "shop_visits": pulp.lpSum(
                disc[t] * w.cost * x[e.esn, t, w.code]
                for e in E
                for t in T
                for w in W
                if (e.esn, t, w.code) in x
            ),
            "spare_lease": pulp.lpSum(disc[t] * d.lease_cost_per_month * L[t] for t in T),
            "engine_changes": pulp.lpSum(
                disc[t] * d.engine_change_cost * y[e.esn, t] for e in E for t in T
            ),
            "aog": pulp.lpSum(disc[t] * d.aog_cost_per_month * s[t] for t in T),
            "fuel_deterioration": pulp.lpSum(disc[t] * f[e.esn, t] for e in E for t in T),
            "terminal_value": -d.terminal_value_factor
            * disc[d.horizon]
            * (
                pulp.lpSum(d.terminal_egt_value_per_degC * g[e.esn, d.horizon] for e in E)
                + pulp.lpSum(
                    m.llp_value_per_cycle * r[e.esn, m.name, d.horizon] for e in E for m in M
                )
            ),
        }
        p += pulp.lpSum(self.cost_terms.values())

    # ------------------------------------------------------------------
    def solve(
        self,
        solver: str = "highs",
        time_limit: int = 120,
        gap: float = 0.005,
        threads: int | None = None,
        msg: bool = False,
    ) -> Solution:
        """Solve and return the plan.

        highs : HiGHS via PuLP (default). ``threads`` enables parallel search.
        cbc   : CBC bundled with PuLP.
        scip  : SCIP via OR-Tools (``pip install ortools``); usually the
                strongest dual bound on this model.
        """
        if solver == "highs":
            s = pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)
            self.prob.solve(s)
            h = self.prob.solverModel
            status = h.modelStatusToString(h.getModelStatus())
            # PuLP reports "Optimal" even when the time limit stopped the search
            dual_bound = h.getInfo().mip_dual_bound
        elif solver == "cbc":
            s = pulp.PULP_CBC_CMD(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)
            self.prob.solve(s)
            status, dual_bound = pulp.LpStatus[self.prob.status], None
        elif solver == "scip":
            status, dual_bound = self._solve_ortools("scip", time_limit, gap, threads, msg)
        else:
            raise ValueError(f"unknown solver: {solver}")
        return self._extract(status, dual_bound)

    def _solve_ortools(self, name, time_limit, gap, threads, msg):
        import json
        import subprocess
        import sys
        import tempfile

        params = [f"limits/gap = {gap}"]
        if threads:
            params.append(f"parallel/maxnthreads = {threads}")
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/model.mps"
            self.prob.writeMPS(path)
            # run the worker as a plain script so this package (and highspy) is not imported
            worker = Path(__file__).with_name("_ortools_worker.py")
            proc = subprocess.run(
                [sys.executable, str(worker), path, name,
                 str(time_limit), "\n".join(params), "1" if msg else "0"],
                capture_output=True, text=True,
            )
        if proc.returncode != 0:
            raise RuntimeError(f"OR-Tools worker failed:\n{proc.stderr}")
        if msg:
            print(proc.stderr, file=sys.stderr)
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        if out["values"] is None:
            return out["status"], None
        for var in self.prob.variables():
            var.varValue = out["values"].get(var.name)
        status = "Optimal" if out["status"] == "OPTIMAL" else "Feasible (limit reached)"
        return status, out["bound"]

    def _extract(self, status: str, dual_bound: float | None) -> Solution:
        d = self.d
        val = lambda v: pulp.value(v) or 0.0  # noqa: E731
        visits = []
        for (esn, t, code), var in self.x.items():
            if val(var) > 0.5:
                w = next(w for w in d.workscopes if w.code == code)
                visits.append(
                    ShopVisit(
                        esn=esn,
                        start=t,
                        workscope=code,
                        tat=w.tat,
                        egt_before=val(self.g[esn, t]),
                        llp_before={m.name: val(self.r[esn, m.name, t]) for m in d.modules},
                    )
                )
        visits.sort(key=lambda v: (v.start, v.esn))
        T = range(d.horizon)
        TS = range(d.horizon + 1)
        return Solution(
            status=status,
            objective=val(self.prob.objective),
            visits=visits,
            operating={e.esn: [round(val(self.u[e.esn, t])) for t in T] for e in d.engines},
            egt={e.esn: [val(self.g[e.esn, t]) for t in TS] for e in d.engines},
            llp={
                e.esn: {m.name: [val(self.r[e.esn, m.name, t]) for t in TS] for m in d.modules}
                for e in d.engines
            },
            lease=[round(val(self.L[t])) for t in T],
            aog=[val(self.s[t]) for t in T],
            cost_breakdown={k: val(v) for k, v in self.cost_terms.items()},
            dual_bound=dual_bound,
            has_solution=pulp.value(self.prob.objective) is not None,
        )


def solve(data: FleetData, **kwargs) -> Solution:
    return EngineMroModel(data).solve(**kwargs)
