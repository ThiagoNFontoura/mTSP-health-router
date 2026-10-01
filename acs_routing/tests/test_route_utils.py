import numpy as np
import pytest
import acs_routing.route_utils as route_utils

from acs_routing.route_utils import (
    insertion_delta,
    rebuild_prefixes,
    swap_delta,
    total_time,
    two_opt_delta,
)
from acs_routing.travel_matrix import TravelMatrix
from acs_routing.models import build_family_index, Family


def matrix() -> TravelMatrix:
    return TravelMatrix.from_square(
        np.array([[0, 60, 120, 180], [70, 0, 80, 90], [130, 85, 0, 75], [190, 95, 77, 0]])
    )


def test_deltas_match_full_recomputation_for_asymmetric_matrix():
    travel = matrix()
    route = [0, 1, 2, 3, 0]
    services = {1: 10, 2: 10, 3: 10}
    family_index = build_family_index(
        [Family(1, 0, 0, {}, "R0", None, None), Family(2, 0, 0, {}, "R0", None, None), Family(3, 0, 0, {}, "R0", None, None)]
    )
    base = total_time(route, travel, services, family_index)
    reversed_route = [0, 2, 1, 3, 0]
    forward, backward = rebuild_prefixes(route, travel, family_index)
    assert two_opt_delta(route, 1, 2, travel, forward, backward, family_index) == pytest.approx(
        total_time(reversed_route, travel, services, family_index) - base
    )
    inserted = [0, 1, 2, 3, 1, 0]
    assert insertion_delta(3, 1, 0, travel, 10, family_index) == pytest.approx(
        total_time(inserted, travel, services, family_index) - base
    )


def test_swap_delta_matches_full_recomputation():
    travel = matrix()
    route = [0, 1, 2, 3, 0]
    swapped = [0, 2, 1, 3, 0]
    family_index = build_family_index(
        [Family(1, 0, 0, {}, "R0", None, None), Family(2, 0, 0, {}, "R0", None, None)]
    )
    assert swap_delta(0, 1, 2, 2, travel, 0, 0, family_index) == pytest.approx(
        total_time([0, 2, 2, 0], travel, {}, family_index) - total_time([0, 1, 2, 0], travel, {}, family_index)
    )


def test_two_opt_delta_does_not_rebuild_prefixes(monkeypatch):
    travel = matrix()
    route = [0, 1, 2, 3, 0]
    family_index = build_family_index(
        [Family(1, 0, 0, {}, "R0", None, None), Family(2, 0, 0, {}, "R0", None, None), Family(3, 0, 0, {}, "R0", None, None)]
    )
    forward, backward = rebuild_prefixes(route, travel, family_index)

    def fail_rebuild(*args, **kwargs):
        raise AssertionError("two_opt_delta must use supplied prefixes")

    monkeypatch.setattr(route_utils, "rebuild_prefixes", fail_rebuild)
    assert two_opt_delta(route, 1, 2, travel, forward, backward, family_index) == pytest.approx(
        1.333333333333334
    )
