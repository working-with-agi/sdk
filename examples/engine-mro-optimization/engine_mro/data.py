"""Problem data for the integrated engine maintenance planning model.

Units (unless noted):
  money  : k$ (thousand USD)
  time   : months (one period = one month)
  wear   : cycles (LLP life) / degC (EGT margin)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Module:
    name: str
    llp_life: int
    """Certified life of the module's LLP stack [cycles]."""
    llp_value_per_cycle: float
    """Value of one remaining LLP cycle [k$/cycle] (used for terminal value)."""


@dataclass(frozen=True)
class Workscope:
    code: str
    name: str
    cost: float
    """Shop visit cost incl. removal/installation, labour, material, LLP kits [k$]."""
    tat: int
    """Turn-around time: months the engine is unavailable after induction."""
    egt_restore_to: float | None
    """EGT margin after the visit [degC]; None = no performance restoration."""
    llp_replace: tuple[str, ...]
    """Modules whose LLP stack is replaced (life reset to full)."""


@dataclass(frozen=True)
class Engine:
    esn: str
    egt_margin: float
    """Usable EGT margin at t=0 [degC] (above the operator's safety floor)."""
    llp_remaining: dict[str, int]
    """Remaining LLP cycles per module at t=0."""
    installed: bool = True
    in_shop_until: int = 0
    """Engine is already in the shop for months [0, in_shop_until)."""
    cycles_per_month: int | None = None
    """Engine-specific utilisation; falls back to FleetData.cycles_per_month."""


@dataclass
class FleetData:
    horizon: int
    installed_positions: int
    """Engines that must be on-wing every month (aircraft x engines/aircraft)."""
    cycles_per_month: int
    egt_margin_max: float
    egt_loss_per_1000_cycles: float
    fuel_penalty_per_degC_month: float
    """Extra fuel burn cost per degC of lost margin per operating engine-month [k$]."""
    engine_change_cost: float
    """Cost of installing an engine on an aircraft (swap, test run, logistics) [k$]."""
    shop_slots: int
    """Max engines simultaneously in the shop (capacity / contract slots)."""
    lease_cost_per_month: float
    max_lease_engines: int
    aog_cost_per_month: float
    """Penalty for an uncovered engine position (aircraft on ground) [k$/month]."""
    discount_rate_annual: float
    terminal_egt_value_per_degC: float
    terminal_value_factor: float
    """Haircut applied to end-of-horizon asset value (< 1 avoids end effects)."""
    modules: list[Module]
    workscopes: list[Workscope]
    engines: list[Engine]
    meta: dict = field(default_factory=dict)

    # --- derived helpers -------------------------------------------------

    def cycles(self, engine: Engine) -> int:
        return engine.cycles_per_month or self.cycles_per_month

    def egt_loss_per_month(self, engine: Engine) -> float:
        return self.egt_loss_per_1000_cycles * self.cycles(engine) / 1000.0

    def discount(self, t: int) -> float:
        monthly = (1.0 + self.discount_rate_annual) ** (1.0 / 12.0)
        return 1.0 / monthly**t

    def validate(self) -> None:
        module_names = {m.name for m in self.modules}
        for w in self.workscopes:
            unknown = set(w.llp_replace) - module_names
            if unknown:
                raise ValueError(f"workscope {w.code}: unknown modules {unknown}")
            if w.tat < 1:
                raise ValueError(f"workscope {w.code}: tat must be >= 1")
        for e in self.engines:
            missing = module_names - set(e.llp_remaining)
            if missing:
                raise ValueError(f"engine {e.esn}: missing LLP data for {missing}")
            if not 0 <= e.egt_margin <= self.egt_margin_max:
                raise ValueError(f"engine {e.esn}: egt_margin out of range")
        if len(self.engines) < self.installed_positions:
            # Not fatal (leases / AOG slack keep the model feasible) but worth flagging.
            print(
                f"warning: {len(self.engines)} engines for "
                f"{self.installed_positions} positions"
            )


def load(path: str | Path) -> FleetData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    data = FleetData(
        horizon=raw["horizon_months"],
        installed_positions=raw["installed_positions"],
        cycles_per_month=raw["cycles_per_month"],
        egt_margin_max=raw["egt_margin_max"],
        egt_loss_per_1000_cycles=raw["egt_loss_per_1000_cycles"],
        fuel_penalty_per_degC_month=raw["fuel_penalty_per_degC_month"],
        engine_change_cost=raw["engine_change_cost"],
        shop_slots=raw["shop_slots"],
        lease_cost_per_month=raw["lease_cost_per_month"],
        max_lease_engines=raw["max_lease_engines"],
        aog_cost_per_month=raw["aog_cost_per_month"],
        discount_rate_annual=raw["discount_rate_annual"],
        terminal_egt_value_per_degC=raw["terminal_egt_value_per_degC"],
        terminal_value_factor=raw["terminal_value_factor"],
        modules=[Module(**m) for m in raw["modules"]],
        workscopes=[
            Workscope(**{**w, "llp_replace": tuple(w["llp_replace"])})
            for w in raw["workscopes"]
        ],
        engines=[Engine(**e) for e in raw["engines"]],
        meta=raw.get("meta", {}),
    )
    data.validate()
    return data
