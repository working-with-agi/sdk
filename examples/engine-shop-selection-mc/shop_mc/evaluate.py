"""Out-of-sample Monte Carlo evaluation of a fixed plan and SAA optimality-gap estimation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import Problem
from .model import Plan, fixed_cost, solve_saa
from .scenarios import ScenarioSet, sample


@dataclass
class Evaluation:
    n: int
    mean: float
    std: float
    p50: float
    p90: float
    p95: float
    cvar90: float
    """Mean of the worst 10 % scenario costs."""
    aog_prob: float
    """Probability of at least one AOG month."""
    aog_engine_months: float
    lease_engine_months: float
    costs: np.ndarray

    @property
    def stderr(self) -> float:
        return self.std / np.sqrt(self.n)


def evaluate(p: Problem, plan: Plan, sc: ScenarioSet) -> Evaluation:
    """Total cost per scenario with the plan fixed; the recourse is closed-form:
    shortfall is covered by short-term leases up to the cap, the rest is AOG."""
    T = p.horizon
    idx = np.array(plan.chosen)
    chosen = [sc.options[i] for i in idx]
    start = np.array([o.month for o in chosen])
    months = np.arange(T)

    visit_cost = sc.cost[:, idx].sum(axis=1)
    end = start[None, :] + sc.down[:, idx]  # (S, visits)
    off = ((start[None, :, None] <= months) & (months < end[:, :, None])).sum(axis=1)  # (S, T)
    available = p.owned_engines - off - sc.unsched + plan.long_spares
    short = np.maximum(0.0, p.installed_positions - available)
    lease = np.minimum(short, np.array([p.lease_cap_at(t) for t in range(T)]))
    aog = short - lease
    aog_cost = np.array([p.aog_cost_at(t) for t in range(T)])

    shortfall = sum(
        k.shortfall_penalty * max(0, k.min_visits - sum(1 for o in chosen if o.shop is k)) for k in p.shops
    )
    first_stage = (
        p.long_spare_cost * T * plan.long_spares + sum(fixed_cost(p, o) for o in chosen) + shortfall
        + p.emergency_kit_premium * plan.emergency_kits
    )
    total = first_stage + visit_cost + p.short_lease_cost * lease.sum(1) + (aog * aog_cost).sum(1)
    q = np.sort(total)
    return Evaluation(
        n=len(total),
        mean=float(total.mean()),
        std=float(total.std(ddof=1)),
        p50=float(np.percentile(total, 50)),
        p90=float(np.percentile(total, 90)),
        p95=float(np.percentile(total, 95)),
        cvar90=float(q[int(0.9 * len(q)) :].mean()),
        aog_prob=float((aog.sum(1) > 0).mean()),
        aog_engine_months=float(aog.sum(1).mean()),
        lease_engine_months=float(lease.sum(1).mean()),
        costs=total,
    )


@dataclass
class GapEstimate:
    lower: float
    lower_std: float
    upper: float
    upper_std: float

    @property
    def gap(self) -> float:
        return self.upper - self.lower

    def gap_ci95(self, m: int) -> float:
        """One-sided 95 % upper confidence limit on the optimality gap."""
        return self.gap + 1.645 * np.sqrt(self.lower_std**2 / m + self.upper_std**2)


def saa_gap(
    p: Problem, candidate: Plan, n: int, replications: int, eval_sc: ScenarioSet, seed: int, **solve_kw
) -> tuple[GapEstimate, list[float]]:
    """Mak-Morton-Wood style estimate: the mean of M independent SAA optimal values is a
    (downward-biased) estimate of a lower bound; the candidate's out-of-sample mean is an
    unbiased upper bound. Valid for the risk-neutral objective only."""
    lows = []
    for m in range(replications):
        plan = solve_saa(p, sample(p, n, seed + 1000 + m), **solve_kw)
        # the solver's proven bound keeps the estimate valid even if the MIP gap is not 0
        lows.append(plan.dual_bound if plan.dual_bound is not None else plan.objective)
    ev = evaluate(p, candidate, eval_sc)
    return (
        GapEstimate(
            lower=float(np.mean(lows)),
            lower_std=float(np.std(lows, ddof=1)) if len(lows) > 1 else 0.0,
            upper=ev.mean,
            upper_std=ev.stderr,
        ),
        lows,
    )
