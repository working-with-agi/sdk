"""Monte Carlo scenario generation.

A scenario fixes, for every first-stage option i (visit, shop, workscope, month, rush):
  start[s, i] month the engine actually leaves the wing: the planned month, or earlier
              if it fails in service first (then the visit is forced)
  cost[s, i]  realised shop-visit cost borne by the operator [k$]
  down[s, i]  realised off-wing months (shipping + TAT + delays)
and for every month t:
  unsched[s, t]  engines off-wing because of unscheduled removals

Sources of uncertainty:
  findings   teardown findings push cost above the quote (engine property)
  delay      shop-wide congestion + engine-specific delay
  fx         home/foreign exchange rate for quotes in foreign currency
  failure    in-service failure of a planned engine while it waits for its visit
             (monthly hazard from ``earliest``; watch-list engines have a high hazard)
  unsched    unscheduled removals of the rest of the fleet (Poisson, random shop time)

Common random numbers: findings are a property of the *engine*, so the same draw
is used for every shop / workscope of an engine; shops then differ in how likely
they are to bill it and in who pays (overrun_share). Shop congestion is shared by
all engines at the same shop in a scenario, and one FX path is shared by all
foreign-currency quotes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import Option, Problem


@dataclass
class ScenarioSet:
    cost: np.ndarray  # (S, I)
    down: np.ndarray  # (S, I) int
    start: np.ndarray  # (S, I) int
    unsched: np.ndarray  # (S, T) float
    options: list[Option]

    @property
    def n(self) -> int:
        return self.cost.shape[0]


@dataclass
class Draws:
    """The raw random draws, before they are mapped onto options."""

    find_u: np.ndarray  # (S, visits)
    find_z: np.ndarray  # (S, visits)
    shop_delay: np.ndarray  # (S, shops)
    eng_delay: np.ndarray  # (S, visits, shops)
    fx: np.ndarray  # (S,)  foreign-currency cost multiplier
    fail: np.ndarray  # (S, visits) month of in-service failure (large = none)
    unsched: np.ndarray  # (S, T)


def _lognormal(mean: float, cv: float, z: np.ndarray) -> np.ndarray:
    sigma2 = np.log1p(cv**2)
    return np.exp(np.log(mean) - sigma2 / 2 + np.sqrt(sigma2) * z)


def overrun_fraction(k, u: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Overrun above the quote as a fraction of the price (before cost sharing)."""
    return np.where(u < k.findings_prob, _lognormal(k.overrun_mean, k.overrun_cv, z), 0.0)


def draw(p: Problem, n: int, seed: int) -> Draws:
    rng = np.random.default_rng(seed)
    nv, ns = len(p.visits), len(p.shops)
    return Draws(
        find_u=rng.random((n, nv)),
        find_z=rng.standard_normal((n, nv)),
        shop_delay=np.stack(
            [rng.choice(k.shop_delay_months, size=n, p=k.shop_delay_probs) for k in p.shops], axis=1
        ),
        eng_delay=np.stack(
            [
                np.stack([rng.choice(k.engine_delay_months, size=n, p=k.engine_delay_probs) for k in p.shops], axis=1)
                for _ in range(nv)
            ],
            axis=1,
        ).reshape(n, nv, ns),
        fx=_lognormal(1.0, np.sqrt(np.expm1(p.fx_vol**2)), rng.standard_normal(n)) if p.fx_vol else np.ones(n),
        unsched=_unscheduled(p, n, rng),
        fail=_failures(p, n, rng),
    )


def _failures(p: Problem, n: int, rng: np.random.Generator) -> np.ndarray:
    never = 10**6
    out = np.full((n, len(p.visits)), never, dtype=int)
    for j, v in enumerate(p.visits):
        if v.hazard > 0:
            out[:, j] = v.earliest + rng.geometric(v.hazard, size=n) - 1
    return out


def sample(p: Problem, n: int, seed: int) -> ScenarioSet:
    d = draw(p, n, seed)
    options = list(p.options())
    esn_idx = {v.esn: j for j, v in enumerate(p.visits)}
    shop_idx = {k.id: j for j, k in enumerate(p.shops)}

    cost = np.empty((n, len(options)))
    down = np.empty((n, len(options)), dtype=int)
    start = np.empty((n, len(options)), dtype=int)
    for i, o in enumerate(options):
        e, s, k = esn_idx[o.visit.esn], shop_idx[o.shop.id], o.shop
        q = k.quotes[o.workscope]
        overrun = overrun_fraction(k, d.find_u[:, e], d.find_z[:, e])
        billed = q.price * (1 + k.overrun_share * overrun) + (k.rush_fee if o.rush else 0.0)
        fx = d.fx if k.currency != "HOME" else 1.0
        failed = d.fail[:, e] < o.month
        start[:, i] = np.where(failed, d.fail[:, e], o.month)
        cost[:, i] = (billed * fx + k.transport_cost) * np.where(failed, p.failure_cost_factor, 1.0)
        down[:, i] = (
            k.transport_months + o.tat() + d.shop_delay[:, s] + d.eng_delay[:, e, s]
            + np.where(failed, p.failure_extra_months, 0)
        )

    return ScenarioSet(cost, down, start, d.unsched, options)


def _unscheduled(p: Problem, n: int, rng: np.random.Generator) -> np.ndarray:
    """Engines off-wing per month from unscheduled removals (Poisson arrivals)."""
    T = p.horizon
    out = np.zeros((n, T))
    arrivals = rng.poisson(p.unsched_rate * p.background_engines, size=(n, T))
    for s, t in zip(*np.nonzero(arrivals)):
        for _ in range(arrivals[s, t]):
            dur = rng.choice(p.unsched_tat, p=p.unsched_tat_probs)
            out[s, t : t + dur] += 1
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
        start=np.array([[o.month for o in big.options]]),
        unsched=big.unsched.mean(axis=0, keepdims=True),
        options=big.options,
    )


def input_distributions(p: Problem, n: int = 20000, seed: int = 0) -> dict:
    """Summaries of every uncertain input, for display (histograms / bar charts)."""
    d = draw(p, n, seed)
    shops = []
    for j, k in enumerate(p.shops):
        # operator-borne overrun over the quote, pooled over engines (engine draws are iid)
        ov = k.overrun_share * overrun_fraction(k, d.find_u.ravel(), d.find_z.ravel())
        delay = (d.shop_delay[:, j][:, None] + d.eng_delay[:, :, j]).ravel()
        vals, counts = np.unique(delay, return_counts=True)
        shops.append({
            "id": k.id,
            "name": k.name,
            "currency": k.currency,
            # distribution of the overrun *when there is one* (zero share reported separately)
            "overrun_pct_hist": np.histogram(ov[ov > 0] * 100, bins=np.linspace(0, 100, 21))[0].tolist(),
            "overrun_zero_share": float((ov == 0).mean()),
            "overrun_mean_pct": float(ov.mean() * 100),
            "overrun_p90_pct": float(np.percentile(ov, 90) * 100),
            "delay_months": vals.tolist(),
            "delay_probs": (counts / counts.sum()).tolist(),
        })
    rng = np.random.default_rng(seed + 1)
    total_unsched = rng.poisson(p.unsched_rate * p.background_engines * p.horizon, size=n)
    uv, uc = np.unique(total_unsched, return_counts=True)
    fx_edges = np.linspace(0.7, 1.3, 25)
    return {
        "overrun_edges_pct": np.linspace(0, 100, 21).tolist(),
        "shops": shops,
        "fx_edges": fx_edges.tolist(),
        "fx_hist": np.histogram(d.fx, bins=fx_edges)[0].tolist(),
        "fx_p10_p90": [float(np.percentile(d.fx, 10)), float(np.percentile(d.fx, 90))],
        "unsched_counts": uv.tolist(),
        "unsched_probs": (uc / n).tolist(),
        "aog_cost_by_month": [p.aog_cost_at(t) for t in range(p.horizon)],
        "aog_tiers": [[None if e == float("inf") else e, c] for e, c in p.aog_tiers],
        "required_positions": p.required_positions,
        "buffer": p.buffer,
        "hazards": [{"esn": v.esn, "hazard": v.hazard, "watch": v.watch, "operator": v.operator} for v in p.visits],
        "lease_cap_by_month": [p.lease_cap_at(t) for t in range(p.horizon)],
        "month_labels": [p.month_label(t) for t in range(p.horizon)],
    }
