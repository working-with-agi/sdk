"""Inputs: fleet / planned shop visits, company constraints, and shop quotes with risk profiles.

Units: money k$ (home-currency equivalent at today's FX rate), time months.
Month t = 0 is the calendar month given by ``start`` (e.g. "2026-10").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

LLP_WORKSCOPES_DEFAULT = ("CORE", "FULL")


@dataclass(frozen=True)
class Quote:
    price: float
    """Quoted price incl. labour, material and LLP kits [k$ at today's FX]."""
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
    currency: str = "HOME"
    """Quote currency. Non-home quotes carry FX risk."""
    booking_lead_months: int = 0
    """Slot reservation lead time: the induction must be booked this many months ahead."""
    rush_fee: float | None = None
    """Expedite fee [k$]; None = the shop does not offer expedite."""
    rush_tat_reduction: int = 0
    min_visits: int = 0
    """Contracted volume over the horizon (take-or-pay)."""
    shortfall_penalty: float = 0.0
    """Penalty per visit below ``min_visits`` [k$]."""


@dataclass(frozen=True)
class Visit:
    esn: str
    earliest: int
    latest: int
    """Removal window: induction month must lie in [earliest, latest]; ``latest`` is a
    hard limit (LLP life, EGT margin or AD compliance)."""
    allowed_workscopes: tuple[str, ...]
    """Workscopes that satisfy the engine's condition (EGT margin, LLP status, ADs)."""
    green_time_value: float
    """Value of one month of remaining on-wing life [k$/month]: inducting before
    ``latest`` throws this away for every month of margin left."""
    hazard: float = 0.0
    """Monthly probability of an unscheduled removal (failure) while the engine stays
    on wing from ``earliest`` until its planned induction."""
    watch: bool = False
    """On the watch list (fast EGT deterioration, borescope findings, ...)."""
    operator: str = ""


class Option(NamedTuple):
    visit: Visit
    shop: Shop
    workscope: str
    month: int
    rush: bool

    def tat(self) -> int:
        q = self.shop.quotes[self.workscope].tat
        return max(1, q - self.shop.rush_tat_reduction) if self.rush else q


@dataclass
class Problem:
    start: str
    horizon: int
    required_positions: list[int]
    """Engines that must be on wing each month = 2 x aircraft the schedule needs."""
    buffer: list[int]
    """Serviceable spare engines to keep on the shelf each month (planning rule)."""
    owned_engines: int
    short_lease_cost: float
    short_lease_max: int
    short_lease_max_peak: int
    """Lease engines available in peak months (the market is tight then)."""
    long_spare_cost: float
    long_spare_max: int
    aog_tiers: list[tuple[float, float]]
    """[(engines, cost per engine-month)]: uncovered positions cancel the lowest-margin
    flying first, so each extra missing engine costs more (last tier: engines=inf)."""
    aog_peak_multiplier: dict[int, float]
    """Calendar month (1-12) -> multiplier on AOG cost (holiday / summer peaks)."""
    unsched_rate: float
    """Unscheduled removals per engine-month (1 / MTBUR) for engines not in the plan."""
    background_engines: int
    """Engines whose unscheduled removals are modelled as a fleet-level Poisson process."""
    failure_cost_factor: float
    """Cost multiplier for a visit forced by an in-service failure (secondary damage)."""
    failure_extra_months: int
    """Extra off-wing months for a forced visit (no slot booked, parts not ready)."""
    unsched_tat: tuple[int, ...]
    unsched_tat_probs: tuple[float, ...]
    build_value: dict[str, float]
    """Value of the on-wing life a workscope builds, beyond this horizon [k$]."""
    llp_workscopes: tuple[str, ...]
    """Workscopes that consume an LLP kit."""
    llp_kit_lead_months: int
    llp_kits_on_hand: int
    """Kits already ordered / in stock; any other kit arrives after the lead time."""
    fiscal_year_start_month: int
    budget_by_fy: dict[str, float]
    """Expected shop-visit spend allowed per fiscal year, by induction month [k$]."""
    emergency_kit_premium: float
    """Extra cost of an LLP kit bought outside the normal lead time (broker / USM) [k$]."""
    max_aog_prob: float | None
    """Service target: maximum probability of any AOG month over the horizon."""
    fx_vol: float
    """Volatility of the home/foreign FX rate over the horizon (lognormal sigma)."""
    visits: list[Visit]
    shops: list[Shop]

    # --- calendar helpers ---------------------------------------------------
    def calendar(self, t: int) -> tuple[int, int]:
        y, m = map(int, self.start.split("-"))
        m0 = m - 1 + t
        return y + m0 // 12, m0 % 12 + 1

    def month_label(self, t: int) -> str:
        y, m = self.calendar(t)
        return f"{y}-{m:02d}"

    def fiscal_year(self, t: int) -> str:
        y, m = self.calendar(t)
        return f"FY{y if m >= self.fiscal_year_start_month else y - 1}"

    @property
    def installed_positions(self) -> int:
        return max(self.required_positions)

    def season(self, t: int) -> float:
        return self.aog_peak_multiplier.get(self.calendar(t)[1], 1.0)

    def aog_cost_at(self, t: int) -> float:
        """Cost of the first missing engine in month t (lowest tier)."""
        return self.aog_tiers[0][1] * self.season(t)

    def is_peak(self, t: int) -> bool:
        return self.aog_peak_multiplier.get(self.calendar(t)[1], 1.0) > 1.0

    def lease_cap_at(self, t: int) -> int:
        return self.short_lease_max_peak if self.is_peak(t) else self.short_lease_max

    def options(self):
        """All first-stage choices (visit, shop, workscope, induction month, expedite)."""
        for v in self.visits:
            for k in self.shops:
                for w in v.allowed_workscopes:
                    if w not in k.quotes:
                        continue
                    for t in range(v.earliest, min(v.latest, self.horizon - 1) + 1):
                        yield Option(v, k, w, t, False)
                        if k.rush_fee is not None:
                            yield Option(v, k, w, t, True)


def load(fleet_path: str | Path, shops_path: str | Path) -> Problem:
    f = json.loads(Path(fleet_path).read_text(encoding="utf-8"))
    s = json.loads(Path(shops_path).read_text(encoding="utf-8"))
    shops = []
    for k in s["shops"]:
        rush = k.get("expedite")
        vol = k.get("volume_commitment", {})
        shops.append(
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
                currency=k.get("currency", "HOME"),
                booking_lead_months=k.get("booking_lead_months", 0),
                rush_fee=rush["fee"] if rush else None,
                rush_tat_reduction=rush["tat_reduction"] if rush else 0,
                min_visits=vol.get("min_visits", 0),
                shortfall_penalty=vol.get("shortfall_penalty", 0.0),
            )
        )
    lease = f["short_term_lease"]
    llp = f.get("llp_kits", {})
    budget = f.get("budget", {})
    p = Problem(
        start=f.get("start", "2026-01"),
        horizon=f["horizon_months"],
        required_positions=_monthly(f, "required_positions", f.get("installed_positions")),
        buffer=_monthly(f, "buffer_spares", 0),
        owned_engines=f["owned_engines"],
        short_lease_cost=lease["cost_per_month"],
        short_lease_max=lease["max_engines"],
        short_lease_max_peak=lease.get("max_engines_peak", lease["max_engines"]),
        long_spare_cost=f["long_term_spare"]["cost_per_month"],
        long_spare_max=f["long_term_spare"]["max_engines"],
        aog_tiers=[
            (float("inf") if t.get("engines") is None else t["engines"], t["cost_per_month"])
            for t in f.get("aog_tiers", [{"engines": None, "cost_per_month": f.get("aog_cost_per_month", 0)}])
        ],
        aog_peak_multiplier={int(m): x for m, x in f.get("aog_peak_multiplier", {}).items()},
        unsched_rate=f["unscheduled_removals"]["rate_per_engine_month"],
        background_engines=f["unscheduled_removals"].get("background_engines", f["owned_engines"]),
        failure_cost_factor=f["unscheduled_removals"].get("failure_cost_factor", 1.0),
        failure_extra_months=f["unscheduled_removals"].get("failure_extra_months", 0),
        unsched_tat=tuple(f["unscheduled_removals"]["tat_months"]),
        unsched_tat_probs=tuple(f["unscheduled_removals"]["tat_probs"]),
        build_value=f["workscope_build_value"],
        llp_workscopes=tuple(llp.get("workscopes", LLP_WORKSCOPES_DEFAULT)),
        llp_kit_lead_months=llp.get("lead_time_months", 0),
        llp_kits_on_hand=llp.get("on_hand", 10**6),
        fiscal_year_start_month=budget.get("fiscal_year_start_month", 1),
        budget_by_fy=budget.get("by_fiscal_year", {}),
        emergency_kit_premium=llp.get("emergency_premium", 0.0),
        max_aog_prob=f.get("service_target", {}).get("max_aog_prob"),
        fx_vol=f.get("fx", {}).get("volatility", 0.0),
        visits=[
            Visit(
                e["esn"], e["window"][0], e["window"][1], tuple(e["allowed_workscopes"]),
                e.get("green_time_value_per_month", f.get("green_time_value_per_month", 0.0)),
                e.get("hazard", f.get("default_hazard", 0.0)),
                e.get("watch", False),
                e.get("operator", ""),
            )
            for e in f["engines"]
        ],
        shops=shops,
    )
    _validate(p)
    return p


def _monthly(f: dict, key: str, default) -> list[int]:
    v = f.get(key, default)
    return list(v) if isinstance(v, list) else [v] * f["horizon_months"]


def _validate(p: Problem) -> None:
    if len(p.required_positions) != p.horizon or len(p.buffer) != p.horizon:
        raise ValueError("required_positions / buffer_spares must have one value per month")
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
