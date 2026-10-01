"""Weekly demand and service reports."""

from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from .config import Config
from .models import Family, WeekState
from .reward import _days_late, _ideal_day, is_fixed_active


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
    active_fixed_by_day = [0 for _ in range(config.week_days)]
    active_fixed_served_by_day = [0 for _ in range(config.week_days)]
    visited_per_day: list[int] = []
    overdue_per_day: list[int] = []
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
        visited_per_day.append(len(route.sequence[1:-1]))
        overdue_count = 0
        for family_id in route.sequence[1:-1]:
            family = family_by_id[family_id]
            expected_day = (
                family.fixed_day
                if is_fixed_active(family, monday)
                else _ideal_day(family, monday, config)
            )
            delay = max(0, day_index - expected_day)
            delays.append(delay)
            ideal_visits += int(day_index == expected_day)
            active = is_fixed_active(family, monday)
            fixed_served += int(active and family.fixed_day is not None)
            if active and family.fixed_day == day_index:
                active_fixed_served_by_day[day_index - 1] += 1
            overdue_count += int(_days_late(family, monday, config) > 0)
        overdue_per_day.append(overdue_count)
    for family in families:
        if is_fixed_active(family, monday) and family.fixed_day is not None:
            active_fixed_by_day[family.fixed_day - 1] += 1
    visits = len(delays)
    return {
        "demand": due_by_week_end,
        "capacity": config.k * config.week_days,
        "ideal_day_percentage": (ideal_visits / visits * 100.0) if visits else 0.0,
        "delay_distribution": dict(Counter(delays)),
        "fixed_day_served": fixed_served,
        "families_visited_per_day": visited_per_day,
        "overdue_families_by_weekday": overdue_per_day,
        "active_fixed_families_by_day": active_fixed_by_day,
        "active_fixed_infeasible_by_day": [
            active - served
            for active, served in zip(active_fixed_by_day, active_fixed_served_by_day)
        ],
        "active_fixed_warning": any(
            active > served
            for active, served in zip(active_fixed_by_day, active_fixed_served_by_day)
        ),
    }
