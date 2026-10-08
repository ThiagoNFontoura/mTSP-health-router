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
    visited_per_day = [0 for _ in range(config.week_days)]
    overdue_per_day = [0 for _ in range(config.week_days)]
    visited_per_agent_by_day = [
        [0 for _ in range(config.agents_per_day)]
        for _ in range(config.week_days)
    ]
    route_times_by_agent_by_day = [
        [0.0 for _ in range(config.agents_per_day)]
        for _ in range(config.week_days)
    ]
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
    for route_index, route in enumerate(state.routes):
        day_index = route.day or (route_index // config.agents_per_day + 1)
        agent_index = route.agent or (route_index % config.agents_per_day + 1)
        if not 1 <= day_index <= config.week_days:
            raise ValueError("route day is outside the configured planning week")
        if not 1 <= agent_index <= config.agents_per_day:
            raise ValueError("route agent is outside the configured agent count")
        visit_count = len(route.sequence[1:-1])
        visited_per_day[day_index - 1] += visit_count
        visited_per_agent_by_day[day_index - 1][agent_index - 1] = visit_count
        route_times_by_agent_by_day[day_index - 1][agent_index - 1] = route.total_time
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
            overdue_per_day[day_index - 1] += int(
                _days_late(family, monday, config) > 0
            )
    for family in families:
        if is_fixed_active(family, monday) and family.fixed_day is not None:
            active_fixed_by_day[family.fixed_day - 1] += 1
    visits = len(delays)
    return {
        "demand": due_by_week_end,
        "capacity": config.k * config.week_days * config.agents_per_day,
        "ideal_day_percentage": (ideal_visits / visits * 100.0) if visits else 0.0,
        "delay_distribution": dict(Counter(delays)),
        "fixed_day_served": fixed_served,
        "families_visited_per_day": visited_per_day,
        "families_visited_per_agent_by_day": visited_per_agent_by_day,
        "route_times_by_agent_by_day": route_times_by_agent_by_day,
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
