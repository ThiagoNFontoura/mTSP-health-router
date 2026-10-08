"""Regression tests for simultaneous multi-agent planning."""

from datetime import date
import unittest

import numpy as np

from acs_routing.config import Config
from acs_routing.models import Family, Route, WeekState, build_family_index
from acs_routing.reports import weekly_report
from acs_routing.travel_matrix import TravelMatrix
from acs_routing.validation import validate_plan
from acs_routing.weekly_planner import plan_week


class MultiAgentPlanningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.families = [
            Family(index, 0.0, float(index), {}, "R0", None, None)
            for index in range(1, 7)
        ]
        self.matrix = TravelMatrix.from_square(np.zeros((7, 7)))
        self.monday = date(2026, 10, 5)

    def test_multiple_agents_receive_unique_families(self) -> None:
        config = Config(
            week_days=1,
            agents_per_day=2,
            shift_minutes=25,
            n_iter=4,
            max_passes=10,
        )

        state = plan_week(
            self.families,
            self.matrix,
            self.monday,
            config,
            build_family_index(self.families),
        )

        self.assertEqual([(route.day, route.agent) for route in state.routes], [(1, 1), (1, 2)])
        assigned = [
            family_id
            for route in state.routes
            for family_id in route.sequence[1:-1]
        ]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(len(assigned), 4)
        self.assertTrue(all(route.total_time <= config.shift_minutes for route in state.routes))

        report = weekly_report(self.families, state, config)
        self.assertEqual(report["families_visited_per_day"], [4])
        self.assertEqual(report["families_visited_per_agent_by_day"], [[2, 2]])
        self.assertEqual(report["capacity"], 28)

    def test_one_agent_default_keeps_one_route_per_day(self) -> None:
        config = Config(week_days=2, shift_minutes=25, n_iter=1, max_passes=2)

        state = plan_week(
            self.families,
            self.matrix,
            self.monday,
            config,
            build_family_index(self.families),
        )

        self.assertEqual(len(state.routes), 2)
        self.assertEqual([(route.day, route.agent) for route in state.routes], [(1, 1), (2, 1)])

    def test_validator_certifies_attained_reward_upper_bound(self) -> None:
        config = Config(week_days=1, agents_per_day=2, shift_minutes=35)
        state = WeekState(
            self.families,
            [
                Route([0, 1, 2, 3, 0], 30.0, 300.0, day=1, agent=1),
                Route([0, 4, 5, 6, 0], 30.0, 300.0, day=1, agent=2),
            ],
            self.monday,
        )

        result = validate_plan(state, self.matrix, config)

        self.assertTrue(result.is_valid)
        self.assertTrue(
            any("globally optimal" in message for message in result.passed)
        )

    def test_validator_rejects_duplicate_family(self) -> None:
        config = Config(week_days=1, agents_per_day=2, shift_minutes=35)
        state = WeekState(
            self.families,
            [
                Route([0, 1, 2, 3, 0], 30.0, 300.0, day=1, agent=1),
                Route([0, 3, 4, 5, 0], 30.0, 300.0, day=1, agent=2),
            ],
            self.monday,
        )

        result = validate_plan(state, self.matrix, config)

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any("scheduled more than once" in message for message in result.failed)
        )
        self.assertFalse(
            any("globally optimal" in message for message in result.passed)
        )


if __name__ == "__main__":
    unittest.main()
