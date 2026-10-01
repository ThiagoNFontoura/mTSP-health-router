"""Synthetic data and asymmetric travel matrix generation."""

from datetime import date, timedelta
from typing import Sequence

import numpy as np

from .config import Config, DEFAULT_CONFIG
from .models import Family
from .risk import SENTINEL_POINTS, classify, compute_score
from .travel_matrix import TravelMatrix


def generate_instance(
    family_count: int,
    rng: np.random.Generator,
    fixed_fraction: float = 0.2,
    initial_last_visit_date: date | None = None,
) -> tuple[list[Family], TravelMatrix]:
    """Generate families and a deterministic asymmetric matrix."""
    coordinates = [(0.0, 0.0)]
    families: list[Family] = []
    for family_id in range(1, family_count + 1):
        lat, lon = rng.uniform(-1.0, 1.0, size=2)
        coordinates.append((float(lat), float(lon)))
        sentinels = {name: bool(rng.integers(0, 2)) for name in SENTINEL_POINTS}
        score = compute_score(sentinels)
        risk_class = classify(score)
        reference_date = date(2026, 1, 5)
        interval = DEFAULT_CONFIG.target_interval[risk_class]
        situation = family_id % 4
        offset = {1: -5, 2: 0, 3: 2, 0: 10}[situation]
        last_visit = reference_date - timedelta(days=interval + offset)
        fixed_day = int(rng.integers(1, 6)) if rng.random() < fixed_fraction else None
        families.append(
            Family(
                family_id,
                float(lat),
                float(lon),
                sentinels,
                risk_class,
                fixed_day,
                initial_last_visit_date if initial_last_visit_date is not None else last_visit,
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
