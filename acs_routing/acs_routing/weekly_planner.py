"""Five-day weekly route orchestration."""

from collections.abc import Sequence
from datetime import date

import numpy as np

from .config import Config
from .grasp import solve_week
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
    """Plan five routes concurrently without repeating a family."""
    config.require_runtime_values()
    values = reward_matrix(families, monday_date, config)
    if excluded_ids:
        family_ids = np.asarray([family.id for family in families])
        values[:, np.isin(family_ids, list(excluded_ids))] = 0.0
    rng = np.random.default_rng(config.seed)
    nearest_nodes = (
        matrix.precompute_nearest_nodes(config.neighbor_count)
        if config.use_neighbor_prefilter
        else None
    )
    routes = solve_week(
        families,
        values,
        matrix,
        config,
        monday_date,
        rng,
        family_index,
        nearest_nodes,
    )
    state = WeekState(list(families), routes, monday_date)
    # TODO: add an inter-day local-search extension point.
    return state
