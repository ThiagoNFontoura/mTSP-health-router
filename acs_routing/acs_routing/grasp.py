"""Weekly GRASP construction and refinement loop."""

from collections.abc import Sequence
from datetime import date

import numpy as np

from .config import Config
from .construction import construct_week
from .local_search import refine_route
from .models import Family, Route
from .travel_matrix import TravelMatrix


def solve_week(
    families: Sequence[Family],
    reward_values: np.ndarray,
    matrix: TravelMatrix,
    config: Config,
    monday_date: date,
    rng: np.random.Generator,
    family_index: dict[int, int],
    nearest_nodes: list[np.ndarray] | None = None,
) -> list[Route]:
    """Return the best refined multi-agent week found."""
    best_routes: list[Route] | None = None
    best_reward = float("-inf")
    for _ in range(config.n_iter):
        sub_seed = int(rng.integers(0, np.iinfo(np.int64).max))
        sub_rng = np.random.default_rng(sub_seed)
        routes = construct_week(
            families,
            reward_values,
            matrix,
            config,
            monday_date,
            sub_rng,
            family_index,
            nearest_nodes,
        )
        used_ids = {
            family_id
            for route in routes
            for family_id in route.sequence[1:-1]
        }
        for route_index, route in enumerate(routes):
            day = (route.day - 1) if route.day is not None else (
                route_index // config.agents_per_day
            )
            route_ids = set(route.sequence[1:-1])
            excluded_ids = used_ids - route_ids
            day_rewards = {
                family.id: float(reward_values[day, index])
                for index, family in enumerate(families)
            }
            refine_route(
                route,
                families,
                day_rewards,
                matrix,
                config,
                monday_date,
                family_index,
                nearest_nodes,
                excluded_ids,
            )
            used_ids = {
                family_id
                for candidate in routes
                for family_id in candidate.sequence[1:-1]
            }
        total_reward = sum(route.total_reward for route in routes)
        if total_reward > best_reward:
            best_reward = total_reward
            best_routes = routes
    return best_routes or [
        Route(
            [0, 0],
            0.0,
            0.0,
            day=slot // config.agents_per_day + 1,
            agent=slot % config.agents_per_day + 1,
        )
        for slot in range(config.week_days * config.agents_per_day)
    ]
