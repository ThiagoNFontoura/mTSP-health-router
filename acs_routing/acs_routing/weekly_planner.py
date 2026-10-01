"""Five-day weekly route orchestration."""

from collections.abc import Sequence
from datetime import date

import numpy as np

from .config import Config
from .grasp import solve_day
from .models import Family, Route, WeekState, build_family_index
from .reward import reward_matrix
from .travel_matrix import TravelMatrix


def plan_week(
    families: Sequence[Family],
    matrix: TravelMatrix,
    monday_date: date,
    config: Config,
    family_index: dict[int, int],
    excluded_ids: set[int] | None = None,
) -> WeekState:
    """Plan five daily routes without repeating a family."""
    config.require_runtime_values()
    values = reward_matrix(families, monday_date, config)
    rng = np.random.default_rng(config.seed)
    family_ids = np.asarray([family.id for family in families])
    used = np.isin(family_ids, list(excluded_ids or set()))
    nearest_nodes = (
        matrix.precompute_nearest_nodes(config.neighbor_count)
        if config.use_neighbor_prefilter
        else None
    )
    routes: list[Route] = []
    for day_index in range(config.week_days):
        day_rewards = {
            family.id: float(values[day_index, family_index])
            for family_index, family in enumerate(families)
        }
        route = solve_day(
            families,
            day_index + 1,
            day_rewards,
            matrix,
            config,
            rng,
            used_mask=used,
            family_index=family_index,
            nearest_nodes=nearest_nodes,
        )
        routes.append(route)
        used |= np.isin(
            family_ids, route.sequence[1:-1]
        )
    state = WeekState(list(families), routes, monday_date)
    # TODO: add an inter-day local-search extension point.
    return state
