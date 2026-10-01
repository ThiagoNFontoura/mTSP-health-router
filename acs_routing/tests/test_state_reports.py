from datetime import date

from acs_routing.config import Config
from acs_routing.models import Family, Route, WeekState
from acs_routing.models import build_family_index
from acs_routing.reports import weekly_report
from acs_routing.state import (
    load_state,
    record_planned_but_not_completed,
    save_state,
    update_completed_visits,
)
from acs_routing.travel_matrix import TravelMatrix
from acs_routing.weekly_planner import plan_week
import numpy as np


def test_state_json_round_trip_and_visit_updates(tmp_path):
    family = Family(10, 1.0, 2.0, {"diabetes": True}, "R0", None, date(2026, 1, 1))
    state = WeekState([family], [Route([0, 10, 0], 20.0, 10.0)], date(2026, 1, 5))
    path = tmp_path / "state.json"
    save_state(state, path)
    loaded = load_state(path)
    assert loaded.families[0].last_visit_date == date(2026, 1, 1)
    update_completed_visits(loaded.families, {10}, date(2026, 1, 6))
    assert loaded.families[0].last_visit_date == date(2026, 1, 6)
    record_planned_but_not_completed(loaded.families, {10})
    assert loaded.families[0].last_visit_date == date(2026, 1, 6)


def test_weekly_report_values():
    config = Config(target_interval={"R0": 30}, n_iter=1, alpha=0.3, seed=1)
    families = [Family(10, 0, 0, {}, "R0", 1, date(2025, 12, 5))]
    state = WeekState(families, [Route([0, 10, 0], 20.0, 100.0)], date(2026, 1, 5))
    report = weekly_report(families, state, config)
    assert report["demand"] == 1
    assert report["capacity"] == 70
    assert report["ideal_day_percentage"] == 100.0
    assert report["delay_distribution"] == {0: 1}
    assert report["fixed_day_served"] == 1
    assert report["families_visited_per_day"] == [1]
    assert report["overdue_families_by_weekday"] == [1]


def test_report_warns_when_active_fixed_day_capacity_is_insufficient():
    config = Config(target_interval={"R0": 30}, n_iter=1, alpha=0.3, seed=1)
    families = [
        Family(index, 0, 0, {}, "R0", 1, None, 1, 0)
        for index in range(1, 20)
    ]
    state = WeekState(families, [Route([0, 1, 0], 20.0, 100.0)] + [Route([0, 0], 0.0, 0.0) for _ in range(4)], date(2026, 1, 5))
    report = weekly_report(families, state, config)
    assert report["active_fixed_families_by_day"][0] == len(families)
    assert report["active_fixed_infeasible_by_day"][0] == len(families) - 1
    assert report["active_fixed_warning"] is True


def test_completed_first_week_families_are_excluded_from_second_plan():
    config = Config(target_interval={"R0": 30}, n_iter=1, alpha=0.0, seed=1)
    families = [
        Family(10, 0, 0, {}, "R0", None, date(2025, 12, 1)),
        Family(20, 0, 0, {}, "R0", None, date(2025, 12, 1)),
    ]
    matrix = TravelMatrix.from_square(np.full((3, 3), 10.0))
    index = build_family_index(families)
    first = plan_week(families, matrix, date(2026, 1, 5), config, index)
    first_ids = {
        family_id
        for route in first.routes
        for family_id in route.sequence[1:-1]
    }
    update_completed_visits(families, first_ids, date(2026, 1, 5))
    second = plan_week(
        families,
        matrix,
        date(2026, 1, 12),
        config,
        index,
        excluded_ids=first_ids,
    )
    second_ids = {
        family_id
        for route in second.routes
        for family_id in route.sequence[1:-1]
    }
    assert first_ids.isdisjoint(second_ids)
