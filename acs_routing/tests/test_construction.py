import numpy as np

from acs_routing.config import Config
from acs_routing.construction import construct_day
from acs_routing.models import Family, build_family_index
from acs_routing.travel_matrix import TravelMatrix


def test_construction_stays_within_shift():
    config = Config(n_iter=1, alpha=0.3, seed=1, target_interval={"R0": 30})
    families = [Family(index, 0, 0, {}, "R0", None, None) for index in range(1, 5)]
    matrix = TravelMatrix.from_square(np.full((5, 5), 30.0))
    route = construct_day(
        families, 1, {family.id: 10.0 for family in families}, matrix, config, np.random.default_rng(1), family_index=build_family_index(families)
    )
    assert route.total_time <= config.shift_minutes


def test_close_candidate_competes_with_higher_reward_distant_candidates():
    config = Config(n_iter=1, alpha=0.0, seed=1, target_interval={"R0": 30})
    families = [Family(index, 0, 0, {}, "R0", None, None) for index in range(1, 4)]
    seconds = np.array(
        [
            [0, 60, 600, 600],
            [60, 0, 60, 60],
            [600, 60, 0, 60],
            [600, 60, 60, 0],
        ],
        dtype=float,
    )
    route = construct_day(
        families,
        1,
        {1: 99.0, 2: 100.0, 3: 100.0},
        TravelMatrix.from_square(seconds),
        config,
        np.random.default_rng(1),
        family_index=build_family_index(families),
    )
    assert route.sequence[1] == 1


def test_far_fixed_day_candidate_survives_neighbor_prefilter():
    config = Config(
        n_iter=1,
        alpha=0.0,
        seed=1,
        target_interval={"R0": 30},
        use_neighbor_prefilter=True,
        neighbor_count=1,
    )
    families = [
        Family(1, 0, 0, {}, "R0", None, None),
        Family(2, 0, 0, {}, "R0", None, None),
        Family(3, 0, 0, {}, "R0", 1, None),
    ]
    seconds = np.array(
        [
            [0, 60, 120, 600],
            [60, 0, 60, 600],
            [120, 60, 0, 600],
            [600, 600, 600, 0],
        ],
        dtype=float,
    )
    route = construct_day(
        families,
        1,
        {1: 10.0, 2: 10.0, 3: 100.0},
        TravelMatrix.from_square(seconds),
        config,
        np.random.default_rng(1),
        family_index=build_family_index(families),
    )
    assert route.sequence[1] == 3
