"""Benchmark weekly planning on synthetic family counts."""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

import numpy as np

from acs_routing.synthetic_instance import demo_config, generate_instance
from acs_routing.models import build_family_index
from acs_routing.weekly_planner import plan_week


def benchmark(
    size: int,
    iterations: int,
    use_neighbor_prefilter: bool,
) -> tuple[float, float, list[int], list[float], float]:
    """Return timing and route metrics for one family count."""
    config = replace(
        demo_config(),
        n_iter=iterations,
        use_neighbor_prefilter=use_neighbor_prefilter,
        neighbor_count=1,
    )
    families, matrix = generate_instance(size, np.random.default_rng(config.seed))
    started = time.perf_counter()
    state = plan_week(
        families,
        matrix,
        config.initial_date,
        config,
        build_family_index(families),
    )
    elapsed = time.perf_counter() - started
    visited = [len(route.sequence[1:-1]) for route in state.routes]
    route_times = [round(route.total_time, 3) for route in state.routes]
    total_reward = sum(route.total_reward for route in state.routes)
    return elapsed, elapsed / config.week_days, visited, route_times, total_reward


def main() -> None:
    """Run configured benchmark sizes and print wall-clock results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("sizes", nargs="*", type=int, default=[100, 300, 600, 900])
    parser.add_argument("--iterations", nargs="+", type=int, default=[1, 50])
    parser.add_argument(
        "--full-candidates",
        action="store_true",
        help="disable the geographic prefilter; large runs may be very slow",
    )
    args = parser.parse_args()
    use_neighbor_prefilter = not args.full_candidates
    for size in args.sizes:
        for iterations in args.iterations:
            total, per_day, visited, route_times, reward = benchmark(
                size, iterations, use_neighbor_prefilter
            )
            print(
                f"families={size} iterations={iterations} "
                f"neighbor_prefilter={use_neighbor_prefilter} "
                f"total_seconds={total:.3f} per_day_seconds={per_day:.3f} "
                f"visited_per_day={visited} route_minutes={route_times} "
                f"total_reward={reward:.3f}",
                flush=True,
            )


if __name__ == "__main__":
    main()
