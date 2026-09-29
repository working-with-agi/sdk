"""Distributionally robust planning: a Wasserstein ball around the Monte Carlo inputs.

SAA averages over scenarios drawn from input distributions (overrun, delay, FX,
failures, removals) as if those distributions were known. Many are assumptions
without a source. DRO plans against the worst expected cost over every distribution
within Wasserstein distance theta of the nominal one:

    max_{P : W1(P, P_hat) <= theta}  E_P[ C(x, xi) ]

The ball is restricted to a finite support: the nominal scenarios plus scenarios
drawn from stressed worlds (e.g. shop congestion, combined stress). Moving probability
mass from a nominal scenario to another support scenario costs their distance, so
theta is the budget for "how far reality may be from the assumptions". The finite-
support LP dual (Esfahani & Kuhn 2018) is in :func:`shop_mc.model.solve_saa`.

Distance: L1 between scenario summaries, each scaled by its spread in the nominal
sample, so one unit is "one standard deviation of one summary".
  cost    mean realised cost / nominal mean cost, over all options (findings, FX)
  down    mean off-wing months over all options (delays, congestion)
  early   share of options whose engine fails before the planned month
  unsched engine-months off-wing from unscheduled removals
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import Problem
from .model import Ambiguity
from .scenarios import ScenarioSet, sample

FEATURES = ("cost", "down", "early", "unsched")


def _key(o):
    return (o.visit.esn, o.shop.id, o.workscope, o.month, o.rush)


def summaries(sc: ScenarioSet, ref_cost: np.ndarray) -> np.ndarray:
    """(S, 4) scenario summaries in FEATURES order."""
    planned = np.array([o.month for o in sc.options])
    return np.column_stack([
        (sc.cost / ref_cost).mean(axis=1),
        sc.down.mean(axis=1),
        (sc.start < planned).mean(axis=1),
        sc.unsched.sum(axis=1),
    ])


@dataclass
class Support:
    sc: ScenarioSet
    """Nominal scenarios first, then each stressed world's, on the base problem's options."""
    weights: np.ndarray
    dist: np.ndarray
    labels: list[str]
    """World name of each support scenario."""

    def ambiguity(self, theta: float) -> Ambiguity:
        return Ambiguity(self.weights, self.dist, theta)


def pool(p: Problem, worlds: dict[str, Problem], n_nominal: int, n_per_world: int, seed: int) -> Support:
    """Nominal scenarios from ``p`` plus ``n_per_world`` from each stressed world.

    A world is the same fleet with different assumptions (``decide.case_problem``); its
    scenarios are mapped onto the base options, so a plan is judged on the base contract
    terms (quoted TAT, slots) while the realised costs and delays follow the world.
    """
    base = sample(p, n_nominal, seed)
    keys = [_key(o) for o in base.options]
    parts, labels = [base], ["base"] * n_nominal
    for m, (name, pw) in enumerate(worlds.items()):
        sw = sample(pw, n_per_world, seed + 101 * (m + 1))
        if [_key(o) for o in sw.options] != keys:
            raise ValueError(f"world {name!r} does not have the same options as the base problem")
        parts.append(sw)
        labels += [name] * n_per_world
    sc = ScenarioSet(
        cost=np.vstack([x.cost for x in parts]),
        down=np.vstack([x.down for x in parts]),
        start=np.vstack([x.start for x in parts]),
        unsched=np.vstack([x.unsched for x in parts]),
        options=base.options,
    )
    ref = np.maximum(base.cost.mean(axis=0), 1e-9)
    f = summaries(sc, ref)
    scale = f[:n_nominal].std(axis=0, ddof=1)
    scale = np.where(scale > 1e-9, scale, 1.0)
    z = f / scale
    dist = np.abs(z[:, None, :] - z[None, :, :]).sum(axis=2)
    weights = np.zeros(sc.n)
    weights[:n_nominal] = 1.0 / n_nominal
    return Support(sc, weights, dist, labels)


def remap(p: Problem, sc: ScenarioSet) -> ScenarioSet:
    """A world's scenarios on the base problem's options (for out-of-sample evaluation)."""
    if [_key(o) for o in sc.options] != [_key(o) for o in p.options()]:
        raise ValueError("the scenarios do not have the same options as the base problem")
    return ScenarioSet(sc.cost, sc.down, sc.start, sc.unsched, list(p.options()))
