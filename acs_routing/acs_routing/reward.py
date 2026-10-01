"""Pure family reward functions."""

from datetime import date, timedelta
from math import exp
from collections.abc import Sequence

import numpy as np

from .config import Config, DEFAULT_CONFIG
from .models import Family
from .risk import risk_weight


def one_sided_gaussian(d: float, mu: float, sigma: float) -> float:
    """Rise toward one until ``mu`` and remain one afterward."""
    if d >= mu:
        return 1.0
    return exp(-((d - mu) ** 2) / (2.0 * sigma**2))


def delay_bonus(days_late: int, config: Config = DEFAULT_CONFIG) -> float:
    """Return the capped weekly bonus for Monday's delay."""
    return min(
        config.delay_bonus_cap,
        1.0 + config.delay_bonus_per_day * max(0, days_late),
    )


def _days_late(family: Family, monday_date: date, config: Config) -> int:
    """Return overdue days at the start of the planning week."""
    if family.last_visit_date is None:
        return 0
    interval = config.target_interval.get(family.risk_class)
    if interval is None:
        raise ValueError(f"Missing target interval for {family.risk_class}")
    due_date = family.last_visit_date + timedelta(days=interval)
    return max(0, (monday_date - due_date).days)


def _ideal_day(family: Family, monday_date: date, config: Config) -> int:
    """Return the one-based ideal weekday for a flexible visit."""
    if family.last_visit_date is None:
        return 1
    interval = config.target_interval.get(family.risk_class)
    if interval is None:
        raise ValueError(f"Missing target interval for {family.risk_class}")
    due_date = family.last_visit_date + timedelta(days=interval)
    return min(config.week_days, max(1, (due_date - monday_date).days + 1))


def family_reward(
    family: Family,
    day: int,
    monday_date: date,
    config: Config = DEFAULT_CONFIG,
) -> float:
    """Return one family's reward for a one-based planning day."""
    weight = risk_weight(family.risk_class, config)
    bonus = delay_bonus(_days_late(family, monday_date, config), config)
    if family.fixed_day is not None:
        value = config.a_fixed * weight if day == family.fixed_day else 0.0
        maximum_reward = config.a_fixed * weight * bonus
    else:
        distance = abs(day - _ideal_day(family, monday_date, config))
        value = config.a_flex * weight * bonus * one_sided_gaussian(
            -float(distance), 0.0, config.sigma
        )
        maximum_reward = config.a_flex * weight * bonus
    epsilon = config.epsilon_fraction * maximum_reward
    return value if value >= epsilon else 0.0


def reward_matrix(
    families: Sequence[Family],
    monday_date: date,
    config: Config = DEFAULT_CONFIG,
) -> np.ndarray:
    """Return rewards with shape ``(week_days, family_count)``."""
    return np.asarray(
        [
            [family_reward(family, day, monday_date, config) for family in families]
            for day in range(1, config.week_days + 1)
        ],
        dtype=np.float64,
    )
