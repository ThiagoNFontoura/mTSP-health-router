"""GRASP construction and refinement loop."""

from collections.abc import Mapping, Sequence

import numpy as np

from .config import Config
from .construction import construct_day
from .local_search import refine_route
from .models import Family, Route, build_family_index
from .travel_matrix import TravelMatrix


def solve_day(
    families: Sequence[Family],
    day: int,
    day_rewards: Mapping[int, float],
    matrix: TravelMatrix,
    config: Config,
    rng: np.random.Generator,
    family_index: dict[int, int],
    used_ids: set[int] | None = None,
    used_mask: np.ndarray | None = None,
    nearest_nodes: list[np.ndarray] | None = None,
) -> Route:
    """Return the best refined route found for one day."""
    if config.n_iter is None or config.alpha is None:
        raise ValueError("GRASP requires n_iter and alpha")
    best = Route([0, 0], 0.0, 0.0)
    eligible_families = [
        family
        for index, family in enumerate(families)
        if (used_mask is None or not used_mask[index])
        and (used_ids is None or family.id not in used_ids)
    ]
    index = family_index
    for _ in range(config.n_iter):
        route = construct_day(
            families,
            day,
            day_rewards,
            matrix,
            config,
            rng,
            index,
            used_ids,
            used_mask,
            nearest_nodes,
        )
        route = refine_route(
            route,
            eligible_families,
            day_rewards,
            matrix,
            config,
            index,
            nearest_nodes,
        )
        if route.total_reward > best.total_reward:
            best = route
    return best
