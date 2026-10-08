"""Independent checks and optimality bounds for saved weekly plans."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isclose

import numpy as np

from .config import Config
from .models import Family, WeekState, build_family_index
from .reward import family_reward, is_fixed_active, reward_matrix
from .risk import service_time
from .route_utils import total_time
from .travel_matrix import TravelMatrix


@dataclass
class PlanValidation:
    """Collect validation messages without changing the plan."""

    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    information: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return whether every hard constraint and stored value is valid."""
        return not self.failed


def _route_coordinates(
    route_index: int, day: int | None, agent: int | None, config: Config
) -> tuple[int, int]:
    """Return one-based day and agent, supporting legacy saved routes."""
    return (
        day or route_index // config.agents_per_day + 1,
        agent or route_index % config.agents_per_day + 1,
    )


def validate_plan(
    state: WeekState,
    matrix: TravelMatrix,
    config: Config,
    excluded_ids: set[int] | None = None,
    time_tolerance_minutes: float = 1e-3,
    reward_tolerance: float = 1e-6,
) -> PlanValidation:
    """Validate a saved plan and certify reward optimality when possible."""
    result = PlanValidation()
    excluded = excluded_ids or set()
    families: Sequence[Family] = state.families
    family_by_id = {family.id: family for family in families}
    family_ids = set(family_by_id)
    expected_route_count = config.week_days * config.agents_per_day

    if state.monday_date is None:
        result.failed.append("plan has no monday_date")
        return result
    monday = state.monday_date
    if config.initial_date is not None and config.initial_date != monday:
        result.failed.append(
            "config initial_date does not match the saved plan monday_date"
        )
    if matrix.size != len(families) + 1:
        result.failed.append(
            "travel matrix size does not match UBS plus saved families"
        )
        return result

    if len(state.routes) == expected_route_count:
        result.passed.append(f"{expected_route_count} routes present")
    else:
        result.failed.append(
            f"expected {expected_route_count} routes, found {len(state.routes)}"
        )

    route_pairs: list[tuple[int, int]] = []
    visited_ids: list[int] = []
    stored_reward_total = 0.0
    recalculated_reward_total = 0.0
    recalculated_time_total = 0.0
    longest_route = 0.0
    family_index = build_family_index(families)
    service_times = {
        family.id: service_time(family.risk_class, config) for family in families
    }

    for route_index, route in enumerate(state.routes):
        day, agent = _route_coordinates(
            route_index, route.day, route.agent, config
        )
        route_pairs.append((day, agent))
        label = f"day {day}, agent {agent}"

        if not 1 <= day <= config.week_days:
            result.failed.append(f"{label}: day is outside the planning week")
        if not 1 <= agent <= config.agents_per_day:
            result.failed.append(f"{label}: agent is outside the configured count")
        if len(route.sequence) < 2 or route.sequence[0] != 0 or route.sequence[-1] != 0:
            result.failed.append(f"{label}: route must start and end at UBS node 0")
            continue

        route_family_ids = route.sequence[1:-1]
        unknown = set(route_family_ids) - family_ids
        if unknown:
            result.failed.append(
                f"{label}: unknown family IDs {sorted(unknown)}"
            )
            continue
        visited_ids.extend(route_family_ids)

        repeated_inside_route = [
            family_id
            for family_id, count in Counter(route_family_ids).items()
            if count > 1
        ]
        if repeated_inside_route:
            result.failed.append(
                f"{label}: repeated family IDs {sorted(repeated_inside_route)}"
            )

        wrong_fixed_day = [
            family_id
            for family_id in route_family_ids
            if is_fixed_active(family_by_id[family_id], monday)
            and family_by_id[family_id].fixed_day != day
        ]
        if wrong_fixed_day:
            result.failed.append(
                f"{label}: active fixed-day families scheduled incorrectly "
                f"{sorted(wrong_fixed_day)}"
            )

        recalculated_time = total_time(
            route.sequence, matrix, service_times, family_index
        )
        recalculated_reward = sum(
            family_reward(family_by_id[family_id], day, monday, config)
            for family_id in route_family_ids
        )
        recalculated_time_total += recalculated_time
        recalculated_reward_total += recalculated_reward
        stored_reward_total += route.total_reward
        longest_route = max(longest_route, recalculated_time)

        if recalculated_time > config.shift_minutes + time_tolerance_minutes:
            result.failed.append(
                f"{label}: {recalculated_time:.3f} minutes exceeds "
                f"the {config.shift_minutes}-minute shift"
            )
        if not isclose(
            route.total_time,
            recalculated_time,
            rel_tol=0.0,
            abs_tol=time_tolerance_minutes,
        ):
            result.failed.append(
                f"{label}: stored time {route.total_time:.3f} differs from "
                f"recalculated time {recalculated_time:.3f}"
            )
        if not isclose(
            route.total_reward,
            recalculated_reward,
            rel_tol=0.0,
            abs_tol=reward_tolerance,
        ):
            result.failed.append(
                f"{label}: stored reward {route.total_reward:.3f} differs from "
                f"recalculated reward {recalculated_reward:.3f}"
            )

    expected_pairs = {
        (day, agent)
        for day in range(1, config.week_days + 1)
        for agent in range(1, config.agents_per_day + 1)
    }
    pair_counts = Counter(route_pairs)
    duplicate_pairs = sorted(pair for pair, count in pair_counts.items() if count > 1)
    missing_pairs = sorted(expected_pairs - set(route_pairs))
    if not duplicate_pairs and not missing_pairs and len(route_pairs) == len(expected_pairs):
        result.passed.append("every day/agent assignment is present exactly once")
    else:
        if duplicate_pairs:
            result.failed.append(f"duplicate day/agent assignments: {duplicate_pairs}")
        if missing_pairs:
            result.failed.append(f"missing day/agent assignments: {missing_pairs}")

    visit_counts = Counter(visited_ids)
    duplicate_families = sorted(
        family_id for family_id, count in visit_counts.items() if count > 1
    )
    if duplicate_families:
        result.failed.append(f"families scheduled more than once: {duplicate_families}")
    else:
        result.passed.append("no family is scheduled more than once")

    scheduled_excluded = sorted(set(visited_ids) & excluded)
    if scheduled_excluded:
        result.failed.append(
            f"excluded/completed families were scheduled: {scheduled_excluded}"
        )
    elif excluded:
        result.passed.append("no excluded/completed family is scheduled")

    if not any("stored time" in message for message in result.failed):
        result.passed.append("stored route times match independent recalculation")
    if not any("stored reward" in message for message in result.failed):
        result.passed.append("stored route rewards match independent recalculation")
    if not any("exceeds" in message for message in result.failed):
        result.passed.append("every route is within the configured shift")
    if not any("unknown family" in message for message in result.failed):
        result.passed.append("every scheduled family exists in the saved plan")
    if not any("start and end" in message for message in result.failed):
        result.passed.append("every route starts and ends at UBS node 0")
    if not any("fixed-day" in message for message in result.failed):
        result.passed.append("every active fixed-day family is scheduled correctly")

    if not isclose(
        stored_reward_total,
        recalculated_reward_total,
        rel_tol=0.0,
        abs_tol=reward_tolerance,
    ):
        result.failed.append(
            "stored total reward differs from independently recalculated total"
        )

    eligible_positions = [
        position
        for position, family in enumerate(families)
        if family.id not in excluded
    ]
    rewards = reward_matrix(families, monday, config)
    reward_upper_bound = float(
        np.max(rewards[:, eligible_positions], axis=0).sum()
        if eligible_positions
        else 0.0
    )
    optimal_reward = isclose(
        recalculated_reward_total,
        reward_upper_bound,
        rel_tol=0.0,
        abs_tol=reward_tolerance,
    )
    if optimal_reward and result.is_valid:
        result.passed.append(
            "primary reward objective is globally optimal "
            f"({recalculated_reward_total:.3f}/{reward_upper_bound:.3f})"
        )
    elif optimal_reward:
        result.information.append(
            "reward upper bound was reached, but optimality cannot be certified "
            "because the plan is invalid"
        )
    else:
        result.information.append(
            "primary reward optimality is not proven "
            f"({recalculated_reward_total:.3f}/{reward_upper_bound:.3f} upper bound)"
        )

    unvisited = sorted((family_ids - excluded) - set(visited_ids))
    result.information.extend(
        [
            f"visited unique families: {len(set(visited_ids))}",
            f"unvisited eligible families: {len(unvisited)}",
            f"recalculated total route time: {recalculated_time_total:.3f} minutes",
            f"longest route: {longest_route:.3f} minutes",
            "minimum travel-time optimality is not proven",
            "workload-balance optimality is not part of the current objective",
        ]
    )
    if unvisited:
        result.information.append(f"unvisited family IDs: {unvisited}")
    return result
