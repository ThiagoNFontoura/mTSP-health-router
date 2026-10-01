"""Best-improvement local search for daily routes."""

from collections.abc import Mapping, Sequence
from datetime import date

from .config import Config
import numpy as np

from .models import Family, Route, build_family_index, node_index
from .route_utils import (
    insertion_delta,
    is_feasible,
    rebuild_prefixes,
    swap_delta,
    total_time,
    two_opt_delta,
)
from .risk import service_time
from .reward import is_fixed_active
from .travel_matrix import TravelMatrix


def nearest_neighbors(
    node: int,
    candidate_ids: Sequence[int],
    matrix: TravelMatrix,
    family_index: dict[int, int],
    limit: int | None = None,
    precomputed: list[np.ndarray] | None = None,
) -> list[int]:
    """Return nearby candidates ordered by travel time."""
    if precomputed is not None and family_index is not None:
        node_to_family = {node: family_id for family_id, node in family_index.items()}
        ordered = [
            node_to_family[node]
            for node in precomputed[node_index(node, family_index)]
            if node in node_to_family and node_to_family[node] in candidate_ids
        ]
        return ordered if limit is None else ordered[:limit]
    ordered = sorted(
        candidate_ids,
        key=lambda candidate: matrix.d(
            node_index(node, family_index), node_index(candidate, family_index)
        ),
    )
    return ordered if limit is None else ordered[:limit]


def _insertion_deltas(
    before: int,
    after: int,
    candidate_ids: Sequence[int],
    matrix: TravelMatrix,
    service_values: np.ndarray,
    family_index: dict[int, int],
) -> np.ndarray:
    """Return insertion deltas for all candidates at once."""
    candidate_nodes = np.asarray(
        [node_index(candidate, family_index) for candidate in candidate_ids],
        dtype=np.int64,
    )
    before_node = node_index(before, family_index)
    after_node = node_index(after, family_index)
    return (
        matrix.row_minutes(before_node)[candidate_nodes]
        + service_values
        + matrix.column_minutes(after_node)[candidate_nodes]
        - matrix.d(before_node, after_node)
    )


def _replacement_deltas(
    before: int,
    removed: int,
    after: int,
    candidate_ids: Sequence[int],
    matrix: TravelMatrix,
    removed_service: float,
    candidate_services: np.ndarray,
    family_index: dict[int, int],
) -> np.ndarray:
    """Return replacement deltas for all candidates at once."""
    candidate_nodes = np.asarray(
        [node_index(candidate, family_index) for candidate in candidate_ids],
        dtype=np.int64,
    )
    before_node = node_index(before, family_index)
    removed_node = node_index(removed, family_index)
    after_node = node_index(after, family_index)
    old_time = (
        matrix.d(before_node, removed_node)
        + matrix.d(removed_node, after_node)
        + removed_service
    )
    return (
        matrix.row_minutes(before_node)[candidate_nodes]
        + matrix.column_minutes(after_node)[candidate_nodes]
        + candidate_services
        - old_time
    )


def refine_route(
    route: Route,
    families: Sequence[Family],
    rewards: Mapping[int, float],
    matrix: TravelMatrix,
    config: Config,
    monday_date: date,
    family_index: dict[int, int],
    nearest_nodes: list[np.ndarray] | None = None,
    excluded_ids: set[int] | None = None,
) -> Route:
    """Apply improving 2-Opt, insertion, and replacement swaps."""
    family_by_id = {family.id: family for family in families}
    index = family_index
    service_times = {
        family.id: service_time(family.risk_class, config) for family in families
    }
    forward, backward = rebuild_prefixes(route.sequence, matrix, index)
    for _ in range(config.max_passes):
        changed = False
        changed = False
        route_ids = route.sequence
        current_time = total_time(route_ids, matrix, service_times, index)
        best: tuple[str, tuple[int, ...], float, float] | None = None
        for left in range(1, len(route_ids) - 2):
            for right in range(left + 1, len(route_ids) - 1):
                delta = two_opt_delta(
                    route_ids, left, right, matrix, forward, backward, index
                )
                if delta < -config.min_gain and is_feasible(current_time, delta, config):
                    candidate = route_ids[:left] + list(reversed(route_ids[left : right + 1])) + route_ids[right + 1 :]
                    best = ("route", tuple(candidate), delta, 0.0)
                    break
            if best:
                break
        if best:
            route.sequence = list(best[1])
            route.total_time = total_time(route.sequence, matrix, service_times, index)
            forward, backward = rebuild_prefixes(route.sequence, matrix, index)
            changed = True
            continue

        unused = [
            family.id
            for family in families
            if family.id not in route_ids
            and family.id not in (excluded_ids or set())
        ]
        unused_rewards = np.asarray([rewards.get(candidate, 0.0) for candidate in unused])
        unused_services = np.asarray([service_times[candidate] for candidate in unused])
        for position in range(1, len(route_ids)):
            before, after = route_ids[position - 1], route_ids[position]
            nearby = nearest_neighbors(
                before,
                unused,
                matrix,
                index,
                config.neighbor_count if config.use_neighbor_prefilter else None,
                nearest_nodes,
            )
            candidate_positions = [unused.index(candidate) for candidate in nearby]
            if candidate_positions:
                candidate_rewards = unused_rewards[candidate_positions]
                candidate_service_values = unused_services[candidate_positions]
                deltas = _insertion_deltas(
                    before,
                    after,
                    nearby,
                    matrix,
                    candidate_service_values,
                    index,
                )
                feasible = (
                    (candidate_rewards > config.min_gain)
                    & (current_time + deltas <= config.shift_minutes)
                )
                if np.any(feasible):
                    selected = int(np.flatnonzero(feasible)[np.argmax(candidate_rewards[feasible])])
                    candidate_id = nearby[selected]
                    route.sequence.insert(position, candidate_id)
                    route.total_time = total_time(route.sequence, matrix, service_times, index)
                    forward, backward = rebuild_prefixes(route.sequence, matrix, index)
                    route.total_reward += rewards[candidate_id]
                    changed = True
                    break
            if changed:
                break
        if changed:
            continue

        replacement_ids = nearest_neighbors(
            0,
            unused,
            matrix,
            index,
            config.neighbor_count if config.use_neighbor_prefilter else None,
            nearest_nodes,
        )
        for position in range(1, len(route_ids) - 1):
            removed_id = route_ids[position]
            if is_fixed_active(family_by_id[removed_id], monday_date):
                continue
            candidate_rewards = np.asarray([rewards.get(candidate, 0.0) for candidate in replacement_ids])
            candidate_services = np.asarray([service_times[candidate] for candidate in replacement_ids])
            deltas = _replacement_deltas(
                route_ids[position - 1],
                removed_id,
                route_ids[position + 1],
                replacement_ids,
                matrix,
                service_times[removed_id],
                candidate_services,
                index,
            )
            gains = candidate_rewards - rewards.get(removed_id, 0.0)
            feasible = (gains > config.min_gain) & (
                current_time + deltas <= config.shift_minutes
            )
            if np.any(feasible):
                selected = int(np.flatnonzero(feasible)[np.argmax(gains[feasible])])
                candidate_id = replacement_ids[selected]
                route.sequence[position] = candidate_id
                route.total_time = total_time(route.sequence, matrix, service_times, index)
                forward, backward = rebuild_prefixes(route.sequence, matrix, index)
                route.total_reward += gains[selected]
                changed = True
                break
            if changed:
                break
        if not changed:
            break
    return route
