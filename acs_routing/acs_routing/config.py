"""Immutable application configuration."""

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping


@dataclass(frozen=True)
class Config:
    """Hold all numeric and operational configuration values."""

    shift_minutes: int = 360
    k: int = 14  # used only for capacity estimates and reports, never to limit candidates
    use_neighbor_prefilter: bool = False
    neighbor_count: int = 50
    n_iter: int = 50
    alpha: float = 0.3
    seed: int = 42
    service_time: Mapping[str, int] = field(
        default_factory=lambda: {"R0": 10, "R1": 15, "R2": 20, "R3": 30}
    )
    risk_weight: Mapping[str, int] = field(
        default_factory=lambda: {"R0": 1, "R1": 2, "R2": 4, "R3": 8}
    )
    target_interval: Mapping[str, int] = field(
        default_factory=lambda: {
            # ASSUMPTION - to be defined with the health unit.
            "R0": 90,
            "R1": 60,
            "R2": 30,
            "R3": 14,
        }
    )
    a_fixed: int = 2500
    a_flex: int = 100
    delay_bonus_per_day: float = 0.02
    delay_bonus_cap: float = 1.25
    sigma: float = 1.0
    epsilon_fraction: float = 0.01
    week_days: int = 5
    osrm_profile: str = "foot"
    initial_date: date | None = None
    initial_last_visit_date: date | None = date(2026, 1, 1)

    def require_runtime_values(self) -> None:
        """Reject unresolved algorithm settings before execution."""
        if self.n_iter <= 0 or self.alpha < 0 or self.alpha > 1:
            raise ValueError("n_iter must be positive and alpha must be in [0, 1]")


DEFAULT_CONFIG = Config()
