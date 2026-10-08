"""Parallel GRASP construction for a complete planning week."""

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np

from .config import Config
from .models import Family, Route, node_index
from .risk import service_time
from .route_utils import total_time
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
    """Construct every day/agent route with one global family-used mask."""
    if reward_values.shape != (config.week_days, len(families)):
        raise ValueError("reward_values must have shape (week_days, family_count)")
    family_ids = np.asarray([family.id for family in families], dtype=np.int64)
    matrix_nodes = np.asarray([node_index(family_id, family_index) for family_id in family_ids])
    service_values = np.asarray(
        [service_time(family.risk_class, config) for family in families],
        dtype=np.float64,
    )
    service_times = {family.id: service_time(family.risk_class, config) for family in families}
    slot_days = np.repeat(np.arange(config.week_days), config.agents_per_day)
    slot_count = len(slot_days)
    routes = [[0, 0] for _ in range(slot_count)]
    positions = np.zeros(slot_count, dtype=np.int64)
    current_times = np.zeros(slot_count, dtype=np.float64)
    closed = np.zeros(slot_count, dtype=bool)
    used = np.zeros(len(families), dtype=bool)
    scores = np.vstack(
        [
            _score_vector(
                reward_values[day], 0, matrix, matrix_nodes, service_values
            )
            for day in slot_days
        ]
    )
    if config.use_neighbor_prefilter and nearest_nodes is None:
        nearest_nodes = matrix.precompute_nearest_nodes(config.neighbor_count)
    while not np.all(closed):
        pairs: list[tuple[int, int, float]] = []
        for slot in np.flatnonzero(~closed):
            day = int(slot_days[slot])
            position_node = int(positions[slot])
            eligible = (~used) & (reward_values[day] > 0.0)
            if nearest_nodes is not None:
                geographic = np.isin(matrix_nodes, nearest_nodes[position_node])
                eligible &= geographic
            candidate_indices = np.flatnonzero(eligible)
            if candidate_indices.size:
                current_time = current_times[slot]
                from_position = matrix.row_minutes(position_node)[matrix_nodes[candidate_indices]]
                to_ubs = matrix.to_ubs_minutes()[matrix_nodes[candidate_indices]]
                feasible = current_time + from_position + service_values[candidate_indices] + to_ubs <= config.shift_minutes
                candidate_indices = candidate_indices[feasible]
            if candidate_indices.size == 0:
                closed[slot] = True
                continue
            top_position = int(
                candidate_indices[
                    np.argmax(scores[slot, candidate_indices])
                ]
            )
            pairs.append(
                (
                    int(slot),
                    top_position,
                    float(scores[slot, top_position]),
                )
            )
        if not pairs:
            continue
        # Each slot is an independent stack for one fixed day/agent. The
        # global choice compares the current top of every eligible stack.
        slot, family_position, _ = max(pairs, key=lambda pair: pair[2])
        day = int(slot_days[slot])
        family_id = int(family_ids[family_position])
        routes[slot].insert(-1, family_id)
        used[family_position] = True
        current_times[slot] = total_time(routes[slot], matrix, service_times, family_index)
        positions[slot] = matrix_nodes[family_position]
        scores[slot] = _score_vector(
            reward_values[day], int(positions[slot]), matrix, matrix_nodes, service_values
        )
    family_positions = {
        int(family_id): position for position, family_id in enumerate(family_ids)
    }
    return [
        Route(
            sequence=route,
            total_time=total_time(route, matrix, service_times, family_index),
            total_reward=sum(
                reward_values[int(slot_days[slot]), family_positions[family_id]]
                for family_id in route[1:-1]
            ),
            day=int(slot_days[slot]) + 1,
            agent=slot % config.agents_per_day + 1,
        )
        for slot, route in enumerate(routes)
    ]
