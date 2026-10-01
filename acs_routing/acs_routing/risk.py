"""Coelho-Savassi household risk scoring."""

from collections.abc import Mapping
from functools import lru_cache

import numpy as np

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


@lru_cache(maxsize=None)
def _matching_sentinel_masks(risk_class: str) -> tuple[int, ...]:
    """Return all bit masks that classify into one risk class."""
    names = tuple(SENTINEL_POINTS)
    matching_masks: list[int] = []
    for mask in range(2 ** len(names)):
        sentinels = {
            name: bool(mask & (1 << position))
            for position, name in enumerate(names)
        }
        if classify(compute_score(sentinels)) == risk_class:
            matching_masks.append(mask)
    return tuple(matching_masks)


def sentinels_for_class(
    risk_class: str, rng: np.random.Generator, config: Config = DEFAULT_CONFIG
) -> dict[str, bool]:
    """Sample sentinel combinations until the requested risk class is reached."""
    names = tuple(SENTINEL_POINTS)
    matching_masks = _matching_sentinel_masks(risk_class)
    if not matching_masks:
        raise RuntimeError(f"Could not generate a sentinel combination for {risk_class}")
    mask = matching_masks[int(rng.integers(0, len(matching_masks)))]
    return {
        name: bool(mask & (1 << position))
        for position, name in enumerate(names)
    }
