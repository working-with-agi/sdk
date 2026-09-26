"""Monte Carlo scenario generation.

A scenario fixes, for every first-stage option i = (visit, shop, workscope, month):
  cost[s, i]  realised shop-visit cost borne by the operator [k$]
  down[s, i]  realised off-wing months (shipping + TAT + delays)
and for every month t:
  unsched[s, t]  engines off-wing because of unscheduled removals

Common random numbers: teardown findings are a property of the *engine*,
so the same draw is used for every shop / workscope of an engine; shops then
differ in how likely they are to bill it and in who pays (overrun_share).
Shop congestion is shared by all engines at the same shop in a scenario.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import Problem


@dataclass
class ScenarioSet:
    cost: np.ndarray  # (S, I)
    down: np.ndarray  # (S, I) int
    unsched: np.ndarray  # (S, T) float
    options: list  # [(visit, shop, workscope, month)]

    @property
    def n(self) -> int:
        return self.cost.shape[0]


def _lognormal(mean: float, cv: float, z: np.ndarray) -> np.ndarray:
    sigma2 = np.log1p(cv**2)
    return np.exp(np.log(mean) - sigma2 / 2 + np.sqrt(sigma2) * z)


def sample(p: Problem, n: int, seed: int) -> ScenarioSet:
    rng = np.random.default_rng(seed)
    options = list(p.options())
    esn_idx = {v.esn: j for j, v in enumerate(p.visits)}
    shop_idx = {k.id: j for j, k in enumerate(p.shops)}

    # engine-level findings draws, shared across shops (common random numbers)
    find_u = rng.random((n, len(p.visits)))
    find_z = rng.standard_normal((n, len(p.visits)))
    # delays: shop-wide congestion + engine-specific
    shop_delay = np.stack(
        [rng.choice(k.shop_delay_months, size=n, p=k.shop_delay_probs) for k in p.shops], axis=1
    )
    eng_delay = np.stack(
        [
            np.stack(
                [rng.choice(k.engine_delay_months, size=n, p=k.engine_delay_probs) for k in p.shops],
                axis=1,
            )
            for _ in p.visits
        ],
        axis=1,
    )  # (n, visits, shops)

    cost = np.empty((n, len(options)))
    down = np.empty((n, len(options)), dtype=int)
    for i, (v, k, w, _t) in enumerate(options):
        e, s = esn_idx[v.esn], shop_idx[k.id]
        q = k.quotes[w]
        overrun = np.where(
            find_u[:, e] < k.findings_prob, _lognormal(k.overrun_mean, k.overrun_cv, find_z[:, e]), 0.0
        )
        cost[:, i] = q.price + k.transport_cost + k.overrun_share * q.price * overrun
        down[:, i] = k.transport_months + q.tat + shop_delay[:, s] + eng_delay[:, e, s]

    return ScenarioSet(cost, down, _unscheduled(p, n, rng), options)


def _unscheduled(p: Problem, n: int, rng: np.random.Generator) -> np.ndarray:
    """Engines off-wing per month from unscheduled removals (Poisson arrivals)."""
    T = p.horizon
    out = np.zeros((n, T))
    arrivals = rng.poisson(p.unsched_rate * p.owned_engines, size=(n, T))
    for s, t in zip(*np.nonzero(arrivals)):
        for _ in range(arrivals[s, t]):
            d = rng.choice(p.unsched_tat, p=p.unsched_tat_probs)
            out[s, t : t + d] += 1
    return out


def mean_value(p: Problem, n: int = 20000, seed: int = 0) -> ScenarioSet:
    """The expected-value (EV) problem: one scenario with every parameter at its mean.

    Downtime is rounded to whole months; unscheduled removals become a fractional
    steady-state average. Solving this and evaluating the plan by Monte Carlo
    gives the value of the stochastic solution (VSS).
    """
    big = sample(p, n, seed)
    return ScenarioSet(
        cost=big.cost.mean(axis=0, keepdims=True),
        down=np.rint(big.down.mean(axis=0, keepdims=True)).astype(int),
        unsched=big.unsched.mean(axis=0, keepdims=True),
        options=big.options,
    )
