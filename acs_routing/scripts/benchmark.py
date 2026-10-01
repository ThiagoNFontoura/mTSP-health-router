"""Benchmark parallel weekly planning with bounded per-case execution."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import time
from dataclasses import replace
from datetime import timedelta
from typing import Any

import numpy as np

from acs_routing import grasp
from acs_routing import local_search
from acs_routing.models import build_family_index
from acs_routing.reward import is_fixed_active, _days_late
from acs_routing.state import update_completed_visits
from acs_routing.synthetic_instance import demo_config, generate_instance
from acs_routing.weekly_planner import plan_week


def _run_case(
    size: int,
    iterations: int,
    scenario: str,
    fixed_fraction: float,
    use_neighbor_prefilter: bool,
    output: Any,
) -> None:
    """Run one benchmark case and place metrics on the output queue."""
    config = replace(
        demo_config(),
        n_iter=iterations,
        use_neighbor_prefilter=use_neighbor_prefilter,
        neighbor_count=1,
        fixed_fraction=fixed_fraction,
    )
    families, matrix = generate_instance(
        size,
        np.random.default_rng(config.seed),
        fixed_fraction=fixed_fraction,
        scenario=scenario,
        config=config,
    )
    family_index = build_family_index(families)
    construction_seconds = 0.0
    refine_seconds = 0.0
    operator_seconds = {"two_opt": 0.0, "insertion": 0.0, "replacement": 0.0}
    original_construct = grasp.construct_week
    original_refine = grasp.refine_route
    metrics: dict[str, object] = {}

    def timed_construct(*args: Any, **kwargs: Any) -> list[Any]:
        nonlocal construction_seconds
        started = time.perf_counter()
        result = original_construct(*args, **kwargs)
        construction_seconds += time.perf_counter() - started
        return result

    def timed_refine(*args: Any, **kwargs: Any) -> Any:
        nonlocal refine_seconds
        started = time.perf_counter()
        result = original_refine(*args, **kwargs)
        refine_seconds += time.perf_counter() - started
        return result

    operator_names = {
        "two_opt": "two_opt_delta",
        "insertion": "insertion_delta",
        "replacement": "swap_delta",
    }
    original_operators = {
        name: getattr(local_search, attribute)
        for name, attribute in operator_names.items()
    }

    def make_timed_operator(name: str, original: Any) -> Any:
        def timed_operator(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            result = original(*args, **kwargs)
            operator_seconds[name] += time.perf_counter() - started
            return result

        return timed_operator

    grasp.construct_week = timed_construct
    grasp.refine_route = timed_refine
    for name, original in original_operators.items():
        setattr(local_search, operator_names[name], make_timed_operator(name, original))
    started = time.perf_counter()
    state = plan_week(
        families, matrix, config.initial_date, config, family_index, metrics=metrics
    )
    total_seconds = time.perf_counter() - started
    measured_construction_seconds = construction_seconds
    measured_refine_seconds = refine_seconds
    measured_operator_seconds = dict(operator_seconds)
    visited_ids = {
        family_id
        for route in state.routes
        for family_id in route.sequence[1:-1]
    }
    first_visited_ids = set(visited_ids)
    fixed_ids = {family.id for family in families if is_fixed_active(family, config.initial_date)}
    overdue_per_week = []
    current_date = config.initial_date
    for _ in range(4):
        overdue_per_week.append(
            sum(_days_late(family, current_date, config) > 0 for family in families)
        )
        update_completed_visits(families, visited_ids, current_date)
        current_date = current_date + timedelta(days=7)
        if _ < 3:
            next_state = plan_week(
                families,
                matrix,
                current_date,
                config,
                family_index,
            )
            visited_ids = {
                family_id
                for route in next_state.routes
                for family_id in route.sequence[1:-1]
            }
    iteration_rewards = metrics.get("iteration_rewards", [])
    output.put(
        {
            "families": size,
            "iterations": iterations,
            "scenario": scenario,
            "fixed_fraction": fixed_fraction,
            "neighbor_prefilter": use_neighbor_prefilter,
            "construction_seconds": measured_construction_seconds,
            "refine_seconds": measured_refine_seconds,
            "two_opt_seconds": measured_operator_seconds["two_opt"],
            "insertion_seconds": measured_operator_seconds["insertion"],
            "replacement_seconds": measured_operator_seconds["replacement"],
            "total_seconds": total_seconds,
            "visited_per_day": [len(route.sequence[1:-1]) for route in state.routes],
            "route_minutes": [round(route.total_time, 3) for route in state.routes],
            "total_reward": round(sum(route.total_reward for route in state.routes), 3),
            "class_counts": {
                risk_class: sum(family.risk_class == risk_class for family in families)
                for risk_class in ("R0", "R1", "R2", "R3")
            },
            "active_fixed": len(fixed_ids),
            "fixed_visited": len(first_visited_ids & fixed_ids),
            "flexible_visited": len(first_visited_ids - fixed_ids),
            "iteration_reward_spread": (
                float(round(min(iteration_rewards), 3)),
                float(round(sum(iteration_rewards) / len(iteration_rewards), 3)),
                float(round(max(iteration_rewards), 3)),
            ),
            "greedy_fixed_picks": metrics.get("greedy_fixed_picks", 0),
            "rcl_picks": metrics.get("rcl_picks", 0),
            "candidate_pairs": metrics.get("candidate_pairs_evaluated", 0),
            "two_opt_candidates": metrics.get("two_opt_candidates", 0),
            "insertion_candidates": metrics.get("insertion_candidates", 0),
            "replacement_candidates": metrics.get("replacement_candidates", 0),
            "two_opt_moves": metrics.get("two_opt_moves_accepted", 0),
            "insertion_moves": metrics.get("insertion_moves_accepted", 0),
            "replacement_moves": metrics.get("replacement_moves_accepted", 0),
            "overdue_per_week": overdue_per_week,
        }
    )


def run_case(
    size: int,
    iterations: int,
    scenario: str,
    fixed_fraction: float,
    use_neighbor_prefilter: bool,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    """Run one case and return metrics, or ``None`` on timeout."""
    output: mp.Queue = mp.Queue()
    process = mp.Process(
        target=_run_case,
        args=(size, iterations, scenario, fixed_fraction, use_neighbor_prefilter, output),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        return None
    return output.get() if not output.empty() else None


def main() -> None:
    """Run all requested sizes and iteration counts."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "sizes", nargs="*", type=int, default=[20, 50, 100, 300, 600, 900]
    )
    parser.add_argument("--iterations", nargs="+", type=int, default=[1, 50])
    parser.add_argument("--scenarios", nargs="+", choices=["typical", "peak"], default=["typical", "peak"])
    parser.add_argument("--fixed-fractions", nargs="+", type=float, default=[0.0, 0.1])
    parser.add_argument("--prefilters", nargs="+", choices=["on", "off"], default=["on", "off"])
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--full-candidates", action="store_true")
    args = parser.parse_args()
    for size in args.sizes:
        for scenario in args.scenarios:
            for fixed_fraction in args.fixed_fractions:
                for prefilter in args.prefilters:
                    for iterations in args.iterations:
                        use_neighbor_prefilter = prefilter == "on" and not args.full_candidates
                        result = run_case(
                            size,
                            iterations,
                            scenario,
                            fixed_fraction,
                            use_neighbor_prefilter,
                            args.timeout,
                        )
                        prefix = (
                            f"families={size} scenario={scenario} fixed_fraction={fixed_fraction} "
                            f"prefilter={use_neighbor_prefilter} iterations={iterations} "
                        )
                        if result is None:
                            print(
                                prefix + f"status=TIMEOUT timeout_seconds={args.timeout}",
                                flush=True,
                            )
                            continue
                        iteration_rewards = result["iteration_reward_spread"]
                        print(
                            prefix
                            + f"construction_seconds={result['construction_seconds']:.6f} "
                            f"refine_seconds={result['refine_seconds']:.6f} "
                            f"two_opt_seconds={result['two_opt_seconds']:.6f} "
                            f"insertion_seconds={result['insertion_seconds']:.6f} "
                            f"replacement_seconds={result['replacement_seconds']:.6f} "
                            f"total_seconds={result['total_seconds']:.6f} "
                            f"class_counts={result['class_counts']} active_fixed={result['active_fixed']} "
                            f"visited_per_day={result['visited_per_day']} "
                            f"route_minutes={result['route_minutes']} "
                            f"fixed_visited={result['fixed_visited']} flexible_visited={result['flexible_visited']} "
                            f"total_reward={result['total_reward']:.3f} "
                            f"iteration_reward_spread={iteration_rewards} "
                            f"greedy_fixed={result['greedy_fixed_picks']} rcl={result['rcl_picks']} "
                            f"candidate_pairs={result['candidate_pairs']} "
                            f"operator_candidates=({result['two_opt_candidates']},{result['insertion_candidates']},{result['replacement_candidates']}) "
                            f"operator_moves=({result['two_opt_moves']},{result['insertion_moves']},{result['replacement_moves']}) "
                            f"overdue_per_week={result['overdue_per_week']}",
                            flush=True,
                        )


if __name__ == "__main__":
    main()
