import numpy as np

from acs_routing.config import Config
from acs_routing.local_search import refine_route
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
        route, families, {1: 1, 2: 100}, matrix, config, build_family_index(families)
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
        build_family_index(families),
    )
    assert refined.sequence == [0, 20, 0]
    assert refined.total_time == total_time(
        refined.sequence,
        matrix,
        {10: 30, 20: 10},
        build_family_index(families),
    )
