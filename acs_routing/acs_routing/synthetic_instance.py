"""Synthetic data and asymmetric travel matrix generation."""

from datetime import date, timedelta
from typing import Sequence

import numpy as np

from .config import (
    PEAK_SCENARIO_REFERENCE_FAMILIES,
    Config,
    DEFAULT_CONFIG,
)
from .models import Family
from .risk import sentinels_for_class
from .travel_matrix import TravelMatrix


def generate_instance(
    family_count: int,
    rng: np.random.Generator,
    fixed_fraction: float | None = None,
    initial_last_visit_date: date | None = None,
    scenario: str = "typical",
    config: Config = DEFAULT_CONFIG,
) -> tuple[list[Family], TravelMatrix]:
    """Generate families and a deterministic asymmetric matrix."""
    if scenario not in {"typical", "peak"}:
        raise ValueError("scenario must be typical or peak")
    fixed_share = config.fixed_fraction if fixed_fraction is None else fixed_fraction
    if fixed_share < 0 or fixed_share > 0.10:
        raise ValueError("fixed_fraction cannot exceed 0.10")
    if scenario == "peak":
        scaled = {
            risk_class: round(
                family_count * count / PEAK_SCENARIO_REFERENCE_FAMILIES
            )
            for risk_class, count in config.peak_scenario.items()
        }
    else:
        classified_count = round(family_count * config.classified_fraction)
        scaled = {
            risk_class: round(classified_count * share)
            for risk_class, share in config.risk_split.items()
        }
    classified_total = sum(scaled.values())
    if classified_total > family_count:
        raise ValueError("risk scenario classified count exceeds family count")
    risk_classes = ["R0"] * (family_count - classified_total)
    for risk_class, count in scaled.items():
        risk_classes.extend([risk_class] * count)
    rng.shuffle(risk_classes)
    coordinates = [(0.0, 0.0)]
    families: list[Family] = []
    fixed_count = round(family_count * fixed_share)
    fixed_positions = set(
        rng.choice(family_count, size=fixed_count, replace=False).tolist()
    )
    biweekly_count = round(fixed_count * config.fixed_biweekly_share)
    fixed_positions_list = list(fixed_positions)
    rng.shuffle(fixed_positions_list)
    biweekly_positions = set(fixed_positions_list[:biweekly_count])
    for family_id in range(1, family_count + 1):
        lat, lon = rng.uniform(-1.0, 1.0, size=2)
        coordinates.append((float(lat), float(lon)))
        risk_class = risk_classes[family_id - 1]
        sentinels = sentinels_for_class(risk_class, rng, config)
        reference_date = config.synthetic_reference_date
        interval = config.target_interval[risk_class]
        situation = family_id % 4
        offset = {1: -5, 2: 0, 3: 2, 0: 10}[situation]
        last_visit = reference_date - timedelta(days=interval + offset)
        is_fixed = family_id - 1 in fixed_positions
        fixed_day = int(rng.integers(1, config.week_days + 1)) if is_fixed else None
        fixed_period = (
            2 if family_id - 1 in biweekly_positions else config.fixed_period_weeks_default
        ) if is_fixed else None
        fixed_phase = int(rng.integers(0, fixed_period)) if fixed_period else None
        families.append(
            Family(
                family_id,
                float(lat),
                float(lon),
                sentinels,
                risk_class,
                fixed_day,
                initial_last_visit_date if initial_last_visit_date is not None else last_visit,
                fixed_period,
                fixed_phase,
            )
        )
    matrix_values = np.zeros((family_count + 1, family_count + 1), dtype=np.float32)
    for source in range(family_count + 1):
        for destination in range(family_count + 1):
            if source != destination:
                distance = np.linalg.norm(
                    np.asarray(coordinates[source]) - np.asarray(coordinates[destination])
                )
                matrix_values[source, destination] = 5.0 + 20.0 * distance + source * 0.3
    return families, TravelMatrix.from_square(matrix_values)


def demo_config() -> Config:
    """Return executable settings for the synthetic demonstration."""
    return Config(
        n_iter=20,
        alpha=0.3,
        seed=42,
        target_interval={"R0": 30, "R1": 21, "R2": 14, "R3": 7},
        initial_date=date(2026, 1, 5),
    )
