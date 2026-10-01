"""Coelho-Savassi household risk scoring."""

from collections.abc import Mapping

from .config import Config, DEFAULT_CONFIG

# Values must be checked against the original Coelho-Savassi article (2004).
SENTINEL_POINTS: dict[str, int] = {
    "bedridden": 3,
    "physical_disability": 3,
    "mental_disability": 3,
    "poor_sanitation": 3,
    "severe_malnutrition": 3,
    "drug_addiction": 2,
    "unemployment": 2,
    "illiteracy": 1,
    "under_6_months": 1,
    "over_70_years": 1,
    "hypertension": 1,
    "diabetes": 1,
    "people_per_room_gt_1": 3,
    "people_per_room_eq_1": 2,
}


def compute_score(sentinels: Mapping[str, object]) -> int:
    """Return the total score for active household sentinels."""
    return sum(
        points
        for name, points in SENTINEL_POINTS.items()
        if bool(sentinels.get(name, False))
    )


def classify(score: int) -> str:
    """Classify a score into risk classes R0 through R3."""
    if score < 5:
        return "R0"
    if score <= 6:
        return "R1"
    if score <= 8:
        return "R2"
    return "R3"


def risk_weight(risk_class: str, config: Config = DEFAULT_CONFIG) -> int:
    """Return the configured weight for a risk class."""
    return config.risk_weight[risk_class]


def service_time(risk_class: str, config: Config = DEFAULT_CONFIG) -> int:
    """Return the configured service duration in minutes."""
    return config.service_time[risk_class]
