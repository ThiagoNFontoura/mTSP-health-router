"""Immutable application configuration."""

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

CLASSIFIED_FRACTION = 0.06  # ASSUMPTION for the typical area; Coelho-Savassi reports a PEAK of 9.68% in one microarea.
CLASSIFIED_CAP = 0.10
RISK_SPLIT = {"R1": 0.55, "R2": 0.30, "R3": 0.15}  # ASSUMPTION: typical order R1 > R2 > R3; to be replaced with real data.
PEAK_SCENARIO = {"R1": 9, "R2": 11, "R3": 2}  # Coelho-Savassi peak microarea; stress scenario.
PEAK_SCENARIO_REFERENCE_FAMILIES = 227
FIXED_FRACTION = 0.10
FIXED_PERIOD_WEEKS_DEFAULT = 4
FIXED_BIWEEKLY_SHARE = 0.0
SYNTHETIC_MAX_SENTINEL_ATTEMPTS = 1000


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
    min_gain: float = 1e-6
    max_passes: int = 100
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
    synthetic_reference_date: date = date(2026, 1, 5)
    classified_fraction: float = CLASSIFIED_FRACTION
    fixed_fraction: float = FIXED_FRACTION
    fixed_period_weeks_default: int = FIXED_PERIOD_WEEKS_DEFAULT
    fixed_biweekly_share: float = FIXED_BIWEEKLY_SHARE
    synthetic_max_sentinel_attempts: int = SYNTHETIC_MAX_SENTINEL_ATTEMPTS

    @property
    def risk_split(self) -> Mapping[str, float]:
        """Return the assumed classified-family risk split."""
        return dict(RISK_SPLIT)

    @property
    def peak_scenario(self) -> Mapping[str, int]:
        """Return the Coelho-Savassi peak-microarea stress counts."""
        return dict(PEAK_SCENARIO)

    def require_runtime_values(self) -> None:
        """Reject unresolved algorithm settings before execution."""
        if self.n_iter <= 0 or self.alpha < 0 or self.alpha > 1:
            raise ValueError("n_iter must be positive and alpha must be in [0, 1]")
        if self.classified_fraction < 0 or self.classified_fraction > CLASSIFIED_CAP:
            raise ValueError("classified_fraction must be between 0 and CLASSIFIED_CAP")
        if self.fixed_fraction < 0 or self.fixed_fraction > FIXED_FRACTION:
            raise ValueError("fixed_fraction must be between 0 and FIXED_FRACTION")
        if self.fixed_biweekly_share < 0 or self.fixed_biweekly_share > 1:
            raise ValueError("fixed_biweekly_share must be between 0 and 1")


DEFAULT_CONFIG = Config()
