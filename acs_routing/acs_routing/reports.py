"""Weekly demand and service reports."""

from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from .config import Config
from .models import Family, WeekState
from .reward import _ideal_day


def weekly_report(
    families: Sequence[Family], state: WeekState, config: Config
) -> dict[str, Any]:
    """Return demand, capacity, ideal-day, delay, and fixed-day metrics."""
    monday = state.monday_date
    if monday is None:
        raise ValueError("WeekState requires monday_date for reporting")
    due_by_week_end = 0
    delays: list[int] = []
    ideal_visits = 0
    fixed_served = 0
    family_by_id = {family.id: family for family in families}
    for family in families:
        interval = config.target_interval.get(family.risk_class)
        due_date = (
            family.last_visit_date + timedelta(days=interval)
            if family.last_visit_date is not None and interval is not None
            else monday
        )
        if due_date <= monday + timedelta(days=config.week_days - 1):
            due_by_week_end += 1
    for day_index, route in enumerate(state.routes, start=1):
        for family_id in route.sequence[1:-1]:
            family = family_by_id[family_id]
            expected_day = family.fixed_day or _ideal_day(family, monday, config)
            delay = max(0, day_index - expected_day)
            delays.append(delay)
            ideal_visits += int(day_index == expected_day)
            fixed_served += int(family.fixed_day is not None)
    visits = len(delays)
    return {
        "demand": due_by_week_end,
        "capacity": config.k * config.week_days,
        "ideal_day_percentage": (ideal_visits / visits * 100.0) if visits else 0.0,
        "delay_distribution": dict(Counter(delays)),
        "fixed_day_served": fixed_served,
    }
