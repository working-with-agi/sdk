"""Inputs: fleet / planned shop visits and shop quotes (with their risk profiles).

Units: money k$, time months.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Quote:
    price: float
    """Quoted price incl. labour, material and LLP kits [k$]."""
    tat: int
    """Quoted shop turn-around time [months]."""


@dataclass(frozen=True)
class Shop:
    id: str
    name: str
    slots: int
    """Engines the shop accepts concurrently (contract slots)."""
    transport_cost: float
    """Round-trip transport, insurance, stand rental per visit [k$]."""
    transport_months: int
    """Extra off-wing time for shipping (both ways) [months]."""
    overrun_share: float
    """Share of findings overrun borne by the operator: 1 = T&M, 0 = fixed price."""
    quotes: dict[str, Quote]
    findings_prob: float
    """Probability that teardown findings push the cost above the quote."""
    overrun_mean: float
    """Mean overrun as a fraction of the quoted price, given findings."""
    overrun_cv: float
    """Coefficient of variation of the overrun (lognormal)."""
    shop_delay_months: tuple[int, ...]
    shop_delay_probs: tuple[float, ...]
    """Shop-wide congestion delay: common to all engines at this shop in a scenario."""
    engine_delay_months: tuple[int, ...]
    engine_delay_probs: tuple[float, ...]
    """Engine-specific delay (parts shortage, extra repairs)."""


@dataclass(frozen=True)
class Visit:
    esn: str
    earliest: int
    latest: int
    """Removal window: induction month must lie in [earliest, latest]."""
    allowed_workscopes: tuple[str, ...]
    """Workscopes that satisfy the engine's condition (EGT margin, LLP status, ADs)."""


@dataclass
class Problem:
    horizon: int
    installed_positions: int
    owned_engines: int
    short_lease_cost: float
    short_lease_max: int
    long_spare_cost: float
    long_spare_max: int
    aog_cost: float
    unsched_rate: float
    """Unscheduled removals per engine-month (1 / MTBUR)."""
    unsched_tat: tuple[int, ...]
    unsched_tat_probs: tuple[float, ...]
    build_value: dict[str, float]
    """Value of the on-wing life a workscope builds, beyond this horizon [k$]."""
    visits: list[Visit]
    shops: list[Shop]

    def options(self):
        """All first-stage choices (visit, shop, workscope, induction month)."""
        for v in self.visits:
            for k in self.shops:
                for w in v.allowed_workscopes:
                    if w not in k.quotes:
                        continue
                    for t in range(v.earliest, min(v.latest, self.horizon - 1) + 1):
                        yield v, k, w, t


def load(fleet_path: str | Path, shops_path: str | Path) -> Problem:
    f = json.loads(Path(fleet_path).read_text(encoding="utf-8"))
    s = json.loads(Path(shops_path).read_text(encoding="utf-8"))
    shops = [
        Shop(
            id=k["id"],
            name=k["name"],
            slots=k["slots"],
            transport_cost=k["transport_cost"],
            transport_months=k["transport_months"],
            overrun_share=k["overrun_share"],
            quotes={w: Quote(**q) for w, q in k["quotes"].items()},
            findings_prob=k["findings"]["prob"],
            overrun_mean=k["findings"]["overrun_mean"],
            overrun_cv=k["findings"]["overrun_cv"],
            shop_delay_months=tuple(k["delay"]["shop_months"]),
            shop_delay_probs=tuple(k["delay"]["shop_probs"]),
            engine_delay_months=tuple(k["delay"]["engine_months"]),
            engine_delay_probs=tuple(k["delay"]["engine_probs"]),
        )
        for k in s["shops"]
    ]
    p = Problem(
        horizon=f["horizon_months"],
        installed_positions=f["installed_positions"],
        owned_engines=f["owned_engines"],
        short_lease_cost=f["short_term_lease"]["cost_per_month"],
        short_lease_max=f["short_term_lease"]["max_engines"],
        long_spare_cost=f["long_term_spare"]["cost_per_month"],
        long_spare_max=f["long_term_spare"]["max_engines"],
        aog_cost=f["aog_cost_per_month"],
        unsched_rate=f["unscheduled_removals"]["rate_per_engine_month"],
        unsched_tat=tuple(f["unscheduled_removals"]["tat_months"]),
        unsched_tat_probs=tuple(f["unscheduled_removals"]["tat_probs"]),
        build_value=f["workscope_build_value"],
        visits=[
            Visit(e["esn"], e["window"][0], e["window"][1], tuple(e["allowed_workscopes"]))
            for e in f["engines"]
        ],
        shops=shops,
    )
    _validate(p)
    return p


def _validate(p: Problem) -> None:
    for k in p.shops:
        for probs in (k.shop_delay_probs, k.engine_delay_probs):
            if abs(sum(probs) - 1) > 1e-9:
                raise ValueError(f"shop {k.id}: delay probabilities must sum to 1")
        if not 0 <= k.overrun_share <= 1:
            raise ValueError(f"shop {k.id}: overrun_share must be in [0, 1]")
    for v in p.visits:
        if not any(w in k.quotes for k in p.shops for w in v.allowed_workscopes):
            raise ValueError(f"{v.esn}: no shop quotes any allowed workscope")
        if v.earliest > v.latest or v.earliest >= p.horizon:
            raise ValueError(f"{v.esn}: invalid removal window")
