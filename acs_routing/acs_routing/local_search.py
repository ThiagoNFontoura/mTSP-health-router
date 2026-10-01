"""Best-improvement local search for daily routes."""

from collections.abc import Mapping, Sequence

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


def refine_route(
    route: Route,
    families: Sequence[Family],
    rewards: Mapping[int, float],
    matrix: TravelMatrix,
    config: Config,
    family_index: dict[int, int],
    nearest_nodes: list[np.ndarray] | None = None,
) -> Route:
    """Apply improving 2-Opt, insertion, and replacement swaps."""
    family_by_id = {family.id: family for family in families}
    index = family_index
    service_times = {
        family.id: service_time(family.risk_class, config) for family in families
    }
    forward, backward = rebuild_prefixes(route.sequence, matrix, index)
    changed = True
    while changed:
        changed = False
        route_ids = route.sequence
        current_time = total_time(route_ids, matrix, service_times, index)
        best: tuple[str, tuple[int, ...], float, float] | None = None
        for left in range(1, len(route_ids) - 2):
            for right in range(left + 1, len(route_ids) - 1):
                delta = two_opt_delta(
                    route_ids, left, right, matrix, forward, backward, index
                )
                if delta < 0 and is_feasible(current_time, delta, config):
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

        unused = [family.id for family in families if family.id not in route_ids]
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
            for candidate_id in nearby:
                reward = rewards.get(candidate_id, 0.0)
                if reward <= 0:
                    continue
                delta = insertion_delta(
                    before,
                    candidate_id,
                    after,
                    matrix,
                    service_times[candidate_id],
                    index,
                )
                if is_feasible(current_time, delta, config):
                    route.sequence.insert(position, candidate_id)
                    route.total_time = total_time(route.sequence, matrix, service_times, index)
                    forward, backward = rebuild_prefixes(route.sequence, matrix, index)
                    route.total_reward += reward
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
            if family_by_id[removed_id].fixed_day is not None:
                continue
            for candidate_id in replacement_ids:
                if rewards.get(candidate_id, 0.0) <= rewards.get(removed_id, 0.0):
                    continue
                before = route_ids[position - 1]
                after = route_ids[position + 1]
                delta = swap_delta(
                    before,
                    removed_id,
                    after,
                    candidate_id,
                    matrix,
                    service_times[removed_id],
                    service_times[candidate_id],
                    index,
                )
                if is_feasible(current_time, delta, config):
                    route.sequence[position] = candidate_id
                    route.total_time = total_time(route.sequence, matrix, service_times, index)
                    forward, backward = rebuild_prefixes(route.sequence, matrix, index)
                    route.total_reward += rewards[candidate_id] - rewards.get(removed_id, 0.0)
                    changed = True
                    break
            if changed:
                break
    return route
