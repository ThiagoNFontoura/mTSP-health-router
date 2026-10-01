"""Parallel GRASP construction for a complete planning week."""

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np

from .config import Config
from .models import Family, Route, node_index
from .risk import service_time
from .route_utils import total_time
from .reward import is_fixed_active
from .travel_matrix import TravelMatrix


def _score_vector(
    rewards: np.ndarray,
    position_node: int,
    matrix: TravelMatrix,
    matrix_nodes: np.ndarray,
    service_values: np.ndarray,
) -> np.ndarray:
    """Score every family from one current matrix position."""
    scores = np.zeros_like(rewards, dtype=np.float64)
    denominator = matrix.row_minutes(position_node)[matrix_nodes] + service_values
    np.divide(rewards, denominator, out=scores, where=denominator > 0)
    return scores


def construct_week(
    families: Sequence[Family],
    reward_values: np.ndarray,
    matrix: TravelMatrix,
    config: Config,
    monday_date: date,
    rng: np.random.Generator,
    family_index: Mapping[int, int],
    nearest_nodes: list[np.ndarray] | None = None,
) -> list[Route]:
    """Construct five routes concurrently with one global used mask."""
    if reward_values.shape != (config.week_days, len(families)):
        raise ValueError("reward_values must have shape (week_days, family_count)")
    family_ids = np.asarray([family.id for family in families], dtype=np.int64)
    matrix_nodes = np.asarray([node_index(family_id, family_index) for family_id in family_ids])
    service_values = np.asarray(
        [service_time(family.risk_class, config) for family in families],
        dtype=np.float64,
    )
    service_times = {family.id: service_time(family.risk_class, config) for family in families}
    fixed_days = np.asarray(
        [
            family.fixed_day if is_fixed_active(family, monday_date) else 0
            for family in families
        ],
        dtype=np.int64,
    )
    routes = [[0, 0] for _ in range(config.week_days)]
    positions = np.zeros(config.week_days, dtype=np.int64)
    current_times = np.zeros(config.week_days, dtype=np.float64)
    closed = np.zeros(config.week_days, dtype=bool)
    used = np.zeros(len(families), dtype=bool)
    scores = np.vstack(
        [
            _score_vector(
                reward_values[day], 0, matrix, matrix_nodes, service_values
            )
            for day in range(config.week_days)
        ]
    )
    if config.use_neighbor_prefilter and nearest_nodes is None:
        nearest_nodes = matrix.precompute_nearest_nodes(config.neighbor_count)
    while not np.all(closed):
        pairs: list[tuple[int, int, float, bool]] = []
        for day in np.flatnonzero(~closed):
            position_node = int(positions[day])
            eligible = (~used) & (reward_values[day] > 0.0)
            if nearest_nodes is not None:
                geographic = np.isin(matrix_nodes, nearest_nodes[position_node])
                geographic |= fixed_days == day + 1
                eligible &= geographic
            candidate_indices = np.flatnonzero(eligible)
            if candidate_indices.size:
                current_time = current_times[day]
                from_position = matrix.row_minutes(position_node)[matrix_nodes[candidate_indices]]
                to_ubs = matrix.to_ubs_minutes()[matrix_nodes[candidate_indices]]
                feasible = current_time + from_position + service_values[candidate_indices] + to_ubs <= config.shift_minutes
                candidate_indices = candidate_indices[feasible]
            if candidate_indices.size == 0:
                closed[day] = True
                continue
            for family_index_value in candidate_indices:
                pairs.append(
                    (
                        int(day),
                        int(family_index_value),
                        float(scores[day, family_index_value]),
                        bool(fixed_days[family_index_value] == day + 1),
                    )
                )
        if not pairs:
            continue
        fixed_pairs = [pair for pair in pairs if pair[3]]
        if fixed_pairs:
            selected = max(fixed_pairs, key=lambda pair: pair[2])
        else:
            pair_scores = np.asarray([pair[2] for pair in pairs], dtype=np.float64)
            threshold = float(np.max(pair_scores)) - config.alpha * (
                float(np.max(pair_scores)) - float(np.min(pair_scores))
            )
            rcl = [pair for pair in pairs if pair[2] >= threshold]
            selected = rcl[int(rng.integers(0, len(rcl)))]
        day, family_position, _, _ = selected
        family_id = int(family_ids[family_position])
        routes[day].insert(-1, family_id)
        used[family_position] = True
        current_times[day] = total_time(routes[day], matrix, service_times, family_index)
        positions[day] = matrix_nodes[family_position]
        scores[day] = _score_vector(
            reward_values[day], int(positions[day]), matrix, matrix_nodes, service_values
        )
    return [
        Route(
            sequence=route,
            total_time=total_time(route, matrix, service_times, family_index),
            total_reward=sum(
                reward_values[day, family_ids.tolist().index(family_id)]
                for family_id in route[1:-1]
            ),
        )
        for day, route in enumerate(routes)
    ]
