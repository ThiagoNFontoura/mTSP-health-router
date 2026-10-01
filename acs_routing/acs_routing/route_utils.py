"""Route-time and constant-time move calculations."""

from collections.abc import Mapping, Sequence

import numpy as np

from .config import Config, DEFAULT_CONFIG
from .models import node_index
from .travel_matrix import TravelMatrix


def total_time(
    route: Sequence[int],
    matrix: TravelMatrix,
    service_times: Mapping[int, float],
    family_index: Mapping[int, int],
) -> float:
    """Return route travel plus service time in minutes."""
    travel = sum(
        matrix.d(node_index(source, family_index), node_index(target, family_index))
        for source, target in zip(route, route[1:])
    )
    service = sum(service_times.get(node, 0.0) for node in route[1:-1])
    return travel + service


def rebuild_prefixes(
    route: Sequence[int],
    matrix: TravelMatrix,
    family_index: Mapping[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Build forward and reverse edge prefixes for an asymmetric route."""
    forward = np.asarray(
        [
            matrix.d(node_index(source, family_index), node_index(target, family_index))
            for source, target in zip(route, route[1:])
        ],
        dtype=np.float64,
    )
    backward = np.asarray(
        [
            matrix.d(node_index(target, family_index), node_index(source, family_index))
            for source, target in zip(route, route[1:])
        ],
        dtype=np.float64,
    )
    return np.concatenate(([0.0], np.cumsum(forward))), np.concatenate(
        ([0.0], np.cumsum(backward))
    )


def insertion_delta(
    a: int,
    x: int,
    b: int,
    matrix: TravelMatrix,
    service_time: float,
    family_index: Mapping[int, int],
) -> float:
    """Return the time delta for inserting ``x`` between ``a`` and ``b``."""
    return (
        matrix.d(node_index(a, family_index), node_index(x, family_index))
        + service_time
        + matrix.d(node_index(x, family_index), node_index(b, family_index))
        - matrix.d(node_index(a, family_index), node_index(b, family_index))
    )


def swap_delta(
    p: int,
    r: int,
    n: int,
    x: int,
    matrix: TravelMatrix,
    service_time_r: float,
    service_time_x: float,
    family_index: Mapping[int, int],
) -> float:
    """Return the O(1) delta for replacing ``r`` between ``p`` and ``n``."""
    old_time = (
        matrix.d(node_index(p, family_index), node_index(r, family_index))
        + matrix.d(node_index(r, family_index), node_index(n, family_index))
        + service_time_r
    )
    new_time = (
        matrix.d(node_index(p, family_index), node_index(x, family_index))
        + matrix.d(node_index(x, family_index), node_index(n, family_index))
        + service_time_x
    )
    return new_time - old_time


def two_opt_delta(
    route: Sequence[int],
    i: int,
    j: int,
    matrix: TravelMatrix,
    forward: np.ndarray,
    backward: np.ndarray,
    family_index: Mapping[int, int],
) -> float:
    """Return the time delta for reversing the inclusive segment ``i:j``."""
    if i >= j:
        return 0.0
    old_segment = forward[j] - forward[i]
    reverse_segment = backward[j] - backward[i]
    boundary_old = matrix.d(
        node_index(route[i - 1], family_index), node_index(route[i], family_index)
    ) + matrix.d(node_index(route[j], family_index), node_index(route[j + 1], family_index))
    boundary_new = matrix.d(
        node_index(route[i - 1], family_index), node_index(route[j], family_index)
    ) + matrix.d(node_index(route[i], family_index), node_index(route[j + 1], family_index))
    return reverse_segment - old_segment + boundary_new - boundary_old


def is_feasible(
    current_time: float,
    delta: float,
    config: Config = DEFAULT_CONFIG,
) -> bool:
    """Return whether a move remains within the configured shift."""
    return current_time + delta <= config.shift_minutes
