from datetime import date

import numpy as np

from acs_routing.config import Config
from acs_routing.models import Family
from acs_routing.models import build_family_index
from acs_routing.travel_matrix import TravelMatrix
from acs_routing.weekly_planner import plan_week


def test_week_has_no_repeated_family():
    config = Config(n_iter=2, alpha=0.3, seed=1, target_interval={"R0": 30})
    families = [Family(index, 0, 0, {}, "R0", None, None) for index in range(1, 8)]
    matrix = TravelMatrix.from_square(np.full((8, 8), 10.0))
    state = plan_week(families, matrix, date(2026, 1, 5), config, build_family_index(families))
    visits = [family_id for route in state.routes for family_id in route.sequence[1:-1]]
    assert len(visits) == len(set(visits))
    assert all(route.total_time <= config.shift_minutes for route in state.routes)


def test_planner_maps_noncontiguous_family_ids_to_matrix_nodes():
    config = Config(n_iter=1, alpha=0.0, seed=1, target_interval={"R0": 30})
    families = [
        Family(10, 0, 0, {}, "R0", None, None),
        Family(20, 0, 0, {}, "R0", None, None),
        Family(30, 0, 0, {}, "R0", None, None),
    ]
    matrix = TravelMatrix.from_square(
        np.array(
            [
                [0, 60, 120, 180],
                [70, 0, 80, 90],
                [130, 85, 0, 75],
                [190, 95, 77, 0],
            ],
            dtype=float,
        )
    )
    state = plan_week(families, matrix, date(2026, 1, 5), config, build_family_index(families))
    index = build_family_index(families)
    service_times = {10: 10, 20: 10, 30: 10}
    for route in state.routes:
        manual_time = sum(
            matrix.d(
                0 if source == 0 else index[source],
                0 if target == 0 else index[target],
            )
            for source, target in zip(route.sequence, route.sequence[1:])
        ) + sum(service_times[family_id] for family_id in route.sequence[1:-1])
        assert route.total_time == manual_time
