"""GRASP construction for one planning day."""

from collections.abc import Mapping, Sequence

import numpy as np

from .config import Config, DEFAULT_CONFIG
from .models import Family, Route, build_family_index, node_index
from .risk import service_time
from .route_utils import total_time
from .travel_matrix import TravelMatrix


def construct_day(
    families: Sequence[Family],
    day: int,
    day_rewards: Mapping[int, float],
    matrix: TravelMatrix,
    config: Config,
    rng: np.random.Generator,
    family_index: Mapping[int, int],
    used_ids: set[int] | None = None,
    used_mask: np.ndarray | None = None,
    nearest_nodes: list[np.ndarray] | None = None,
) -> Route:
    """Construct one feasible route using greedy and RCL choices."""
    route = [0, 0]
    family_ids = np.asarray([family.id for family in families], dtype=np.int64)
    index = family_index
    matrix_nodes = np.asarray([node_index(family_id, index) for family_id in family_ids])
    service_values = np.asarray(
        [service_time(family.risk_class, config) for family in families],
        dtype=np.float64,
    )
    reward_values = np.asarray(
        [day_rewards.get(family_id, 0.0) for family_id in family_ids],
        dtype=np.float64,
    )
    family_by_id = {family.id: family for family in families}
    used = np.zeros(len(families), dtype=bool)
    if used_mask is not None:
        if len(used_mask) != len(families):
            raise ValueError("used_mask must match the family sequence length")
        used |= used_mask
    if used_ids:
        used |= np.isin(family_ids, list(used_ids))
    nearest_nodes = nearest_nodes or (
        matrix.precompute_nearest_nodes(config.neighbor_count)
        if config.use_neighbor_prefilter
        else None
    )
    while True:
        current = route[-2]
        route_mask = np.isin(family_ids, route)
        eligible = (~used) & (~route_mask) & (reward_values > 0.0)
        if nearest_nodes is not None:
            geographic = np.zeros(len(families), dtype=bool)
            geographic_matrix_nodes = nearest_nodes[node_index(current, index)]
            geographic |= np.isin(matrix_nodes, geographic_matrix_nodes)
            geographic |= np.asarray(
                [family.fixed_day == day for family in families],
                dtype=bool,
            )
            eligible &= geographic
        candidate_indices = np.flatnonzero(eligible)
        if candidate_indices.size == 0:
            break
        current_time = total_time(
            route,
            matrix,
            {family.id: service_time(family.risk_class, config) for family in families},
            index,
        )
        current_node = node_index(current, index)
        travel_from_current = matrix.row_minutes(current_node)[matrix_nodes[candidate_indices]]
        travel_to_ubs = matrix.to_ubs_minutes()[matrix_nodes[candidate_indices]]
        candidate_services = service_values[candidate_indices]
        candidate_rewards = reward_values[candidate_indices]
        move_time = travel_from_current + candidate_services + travel_to_ubs
        feasible_mask = current_time + move_time - matrix.d(current_node, 0) <= config.shift_minutes
        candidate_indices = candidate_indices[feasible_mask]
        if candidate_indices.size == 0:
            break
        travel_from_current = matrix.row_minutes(current_node)[matrix_nodes[candidate_indices]]
        scores = reward_values[candidate_indices] / (
            travel_from_current + service_values[candidate_indices]
        )
        fixed_mask = np.asarray(
            [family_by_id[int(family_ids[index])].fixed_day == day for index in candidate_indices],
            dtype=bool,
        )
        if np.any(fixed_mask):
            selected_index = candidate_indices[np.flatnonzero(fixed_mask)[np.argmax(scores[fixed_mask])]]
        else:
            maximum = float(np.max(scores))
            minimum = float(np.min(scores))
            threshold = maximum - (config.alpha or 0.0) * (maximum - minimum)
            rcl = candidate_indices[scores >= threshold]
            selected_index = rcl[int(rng.integers(0, len(rcl)))]
        selected_id = int(family_ids[selected_index])
        route.insert(-1, selected_id)
        used[selected_index] = True
    service_times = {
        family.id: service_time(family.risk_class, config) for family in families
    }
    rewards = sum(day_rewards.get(node, 0.0) for node in route[1:-1])
    return Route(route, total_time(route, matrix, service_times, index), rewards)
