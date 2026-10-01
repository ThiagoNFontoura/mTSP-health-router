from datetime import date

import numpy as np
import acs_routing.construction as construction

from acs_routing.config import Config
from acs_routing.construction import construct_week
from acs_routing.models import Family, build_family_index
from acs_routing.travel_matrix import TravelMatrix


def test_construction_stays_within_shift():
    config = Config(n_iter=1, alpha=0.3, seed=1, target_interval={"R0": 30})
    families = [Family(index, 0, 0, {}, "R0", None, None) for index in range(1, 5)]
    matrix = TravelMatrix.from_square(np.full((5, 5), 30.0))
    routes = construct_week(
        families,
        np.full((5, len(families)), 10.0),
        matrix,
        config,
        date(2026, 1, 5),
        np.random.default_rng(1),
        build_family_index(families),
    )
    assert all(route.total_time <= config.shift_minutes for route in routes)


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
    rewards = np.zeros((5, len(families)))
    rewards[0] = [99.0, 100.0, 100.0]
    routes = construct_week(
        families,
        rewards,
        TravelMatrix.from_square(seconds),
        config,
        date(2026, 1, 5),
        np.random.default_rng(1),
        build_family_index(families),
    )
    assert routes[0].sequence[1] == 1


def test_far_fixed_day_candidate_survives_neighbor_prefilter():
    config = Config(
        n_iter=1,
        alpha=1.0,
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
    rewards = np.zeros((5, len(families)))
    rewards[0] = [10.0, 10.0, 100.0]
    routes = construct_week(
        families,
        rewards,
        TravelMatrix.from_square(seconds),
        config,
        date(2026, 1, 5),
        np.random.default_rng(1),
        build_family_index(families),
    )
    assert routes[0].sequence[1] == 3


def test_only_chosen_day_scores_are_recomputed(monkeypatch):
    config = Config(n_iter=1, alpha=0.0, seed=1, target_interval={"R0": 30})
    families = [Family(index, 0, 0, {}, "R0", None, None) for index in range(1, 4)]
    matrix = TravelMatrix.from_square(np.full((4, 4), 30.0))
    rewards = np.full((5, 3), 10.0)
    original = construction._score_vector
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(construction, "_score_vector", counted)
    routes = construction.construct_week(
        families, rewards, matrix, config, date(2026, 1, 5), np.random.default_rng(1), build_family_index(families)
    )
    visits = sum(len(route.sequence[1:-1]) for route in routes)
    assert calls == config.week_days + visits


def test_parallel_construction_is_reproducible_for_both_alpha_modes():
    families = [Family(index, 0, 0, {}, "R0", None, None) for index in range(1, 6)]
    matrix = TravelMatrix.from_square(np.full((6, 6), 30.0))
    index = build_family_index(families)
    rewards = np.arange(25, dtype=float).reshape(5, 5) + 1.0
    for alpha in (0.0, 0.7):
        config = Config(n_iter=1, alpha=alpha, seed=7, target_interval={"R0": 30})
        first = construction.construct_week(
            families, rewards, matrix, config, date(2026, 1, 5), np.random.default_rng(config.seed), index
        )
        second = construction.construct_week(
            families, rewards, matrix, config, date(2026, 1, 5), np.random.default_rng(config.seed), index
        )
        assert [route.sequence for route in first] == [route.sequence for route in second]
