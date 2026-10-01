from datetime import date

import numpy as np
import pytest

from acs_routing.config import Config
from acs_routing.local_search import (
    _insertion_deltas,
    _replacement_deltas,
    refine_route,
)
from acs_routing.route_utils import insertion_delta, swap_delta
from acs_routing.models import Family, Route, build_family_index
from acs_routing.route_utils import total_time
from acs_routing.travel_matrix import TravelMatrix


def test_fixed_day_family_is_not_removed_by_search():
    config = Config(n_iter=1, alpha=0.3, seed=1, target_interval={"R0": 30})
    families = [
        Family(1, 0, 0, {}, "R0", 1, None),
        Family(2, 0, 0, {}, "R0", None, None),
    ]
    matrix = TravelMatrix.from_square(np.array([[0, 1, 1], [1, 0, 1], [1, 1, 0]], dtype=float))
    route = Route([0, 1, 0], 12, 1)
    refined = refine_route(
        route, families, {1: 1, 2: 100}, matrix, config, date(2026, 1, 5), build_family_index(families)
    )
    assert 1 in refined.sequence


def test_replacement_uses_delta_and_matches_recomputed_time():
    config = Config(n_iter=1, alpha=0.3, seed=1, target_interval={"R0": 30, "R3": 30})
    families = [
        Family(10, 0, 0, {}, "R3", None, None),
        Family(20, 0, 0, {}, "R0", None, None),
    ]
    matrix = TravelMatrix.from_square(
        np.array(
            [[0, 9600, 9600], [9600, 0, 9600], [9600, 9600, 0]],
            dtype=float,
        )
    )
    route = Route([0, 10, 0], 350.0, 1.0)
    refined = refine_route(
        route,
        families,
        {10: 1.0, 20: 100.0},
        matrix,
        config,
        date(2026, 1, 5),
        build_family_index(families),
    )
    assert refined.sequence == [0, 20, 0]
    assert refined.total_time == total_time(
        refined.sequence,
        matrix,
        {10: 30, 20: 10},
        build_family_index(families),
    )


def test_inactive_fixed_family_can_be_replaced():
    config = Config(n_iter=1, alpha=0.3, seed=1, target_interval={"R0": 30})
    families = [
        Family(10, 0, 0, {}, "R0", 1, None, 4, 1),
        Family(20, 0, 0, {}, "R0", None, None),
    ]
    matrix = TravelMatrix.from_square(
        np.array([[0, 9600, 9600], [9600, 0, 9600], [9600, 9600, 0]], dtype=float)
    )
    route = Route([0, 10, 0], 340.0, 1.0)
    refined = refine_route(
        route,
        families,
        {10: 1.0, 20: 100.0},
        matrix,
        config,
        date(2026, 1, 5),
        build_family_index(families),
    )
    assert refined.sequence == [0, 20, 0]


def test_vectorized_move_deltas_match_scalar_references():
    families = [
        Family(1, 0, 0, {}, "R0", None, None),
        Family(2, 0, 0, {}, "R0", None, None),
        Family(3, 0, 0, {}, "R0", None, None),
    ]
    index = build_family_index(families)
    matrix = TravelMatrix.from_square(
        np.array([[0, 60, 90, 120], [70, 0, 80, 100], [130, 85, 0, 75], [190, 95, 77, 0]], dtype=float)
    )
    candidates = [2, 3]
    service_values = np.asarray([10.0, 10.0])
    insertion_values = _insertion_deltas(0, 1, candidates, matrix, service_values, index)
    replacement_values = _replacement_deltas(0, 1, 0, candidates, matrix, 10.0, service_values, index)
    assert insertion_values == pytest.approx(
        [insertion_delta(0, candidate, 1, matrix, 10.0, index) for candidate in candidates]
    )
    assert replacement_values == pytest.approx(
        [swap_delta(0, 1, 0, candidate, matrix, 10.0, 10.0, index) for candidate in candidates]
    )


def test_tied_moves_do_not_cycle():
    config = Config(
        shift_minutes=12,
        min_gain=1e-6,
        max_passes=2,
        n_iter=1,
        alpha=0.0,
        seed=1,
        target_interval={"R0": 30},
    )
    families = [
        Family(1, 0, 0, {}, "R0", None, None),
        Family(2, 0, 0, {}, "R0", None, None),
    ]
    matrix = TravelMatrix.from_square(np.full((3, 3), 30.0))
    route = Route([0, 1, 0], 11.0, 100.0)
    refined = refine_route(
        route, families, {1: 100.0, 2: 100.0}, matrix, config, date(2026, 1, 5), build_family_index(families)
    )
    assert refined.sequence == [0, 1, 0]
