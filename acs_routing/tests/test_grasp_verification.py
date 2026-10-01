from datetime import date

import numpy as np

from acs_routing.config import Config
from acs_routing.construction import construct_week
from acs_routing.models import build_family_index
from acs_routing.reward import reward_matrix
from acs_routing.grasp import solve_week
from acs_routing.synthetic_instance import generate_instance
from acs_routing.travel_matrix import TravelMatrix
from acs_routing.weekly_planner import plan_week


def test_rcl_is_used_and_different_seeds_can_change_the_week():
    families, matrix = generate_instance(20, np.random.default_rng(42), fixed_fraction=0.0)
    config = Config(n_iter=20, alpha=0.5, seed=1, target_interval={"R0": 30, "R1": 21, "R2": 14, "R3": 7})
    rewards = reward_matrix(families, date(2026, 1, 5), config)
    index = build_family_index(families)
    stats = {}
    construct_week(
        families,
        rewards,
        matrix,
        config,
        date(2026, 1, 5),
        np.random.default_rng(config.seed),
        index,
        stats=stats,
    )
    assert stats.get("rcl_picks", 0) > 0
    first = plan_week(families, matrix, date(2026, 1, 5), config, index)
    second = plan_week(
        families,
        matrix,
        date(2026, 1, 5),
        Config(**{**config.__dict__, "seed": 2}),
        index,
    )
    assert [route.sequence for route in first.routes] != [route.sequence for route in second.routes]


def test_best_week_reward_is_at_least_first_iteration_and_seed_is_reproducible():
    families, matrix = generate_instance(20, np.random.default_rng(42), fixed_fraction=0.0)
    config = Config(n_iter=20, alpha=0.5, seed=1, target_interval={"R0": 30, "R1": 21, "R2": 14, "R3": 7})
    rewards = reward_matrix(families, date(2026, 1, 5), config)
    index = build_family_index(families)
    metrics = {}
    best = solve_week(
        families,
        rewards,
        matrix,
        config,
        date(2026, 1, 5),
        np.random.default_rng(config.seed),
        index,
        metrics=metrics,
    )
    assert sum(route.total_reward for route in best) >= metrics["iteration_rewards"][0]
    first = plan_week(families, matrix, date(2026, 1, 5), config, index)
    second = plan_week(families, matrix, date(2026, 1, 5), config, index)
    assert [route.sequence for route in first.routes] == [route.sequence for route in second.routes]
