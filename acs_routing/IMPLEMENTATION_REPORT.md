# Implementation Report

## 1. Overview

`acs_routing` plans a five-day set of community health agent home-visit routes from family data, risk classes, rewards, and an asymmetric travel matrix. The weekly planner builds a reward matrix, constructs all five routes in parallel, and then locally improves each route while preventing family reuse. Synthetic data and CSV family input with self-hosted OSRM support are available. The entry point is `acs_routing.main`, which prints five routes followed by a weekly report and can persist state.

## 2. Module-by-module summary

### `config.py`

- **Status:** partial.
- **Responsibility:** Defines immutable operational and algorithm configuration.
- **Main public API:** `Config(...)`; `Config.require_runtime_values() -> None`; `DEFAULT_CONFIG`.
- **Deviation/TODO:** `n_iter=50`, `alpha=0.3`, `seed=42`, `min_gain=1e-6`, and `max_passes=100` are executable defaults. `CLASSIFIED_FRACTION`, `RISK_SPLIT`, `PEAK_SCENARIO`, `FIXED_FRACTION`, `FIXED_PERIOD_WEEKS_DEFAULT`, and `FIXED_BIWEEKLY_SHARE` are explicit assumptions/configuration values. Target intervals remain assumptions for the health unit. Optional geographic filtering is implemented with `use_neighbor_prefilter=False` and `neighbor_count=50`.

### `models.py`

- **Status:** implemented.
- **Responsibility:** Defines the data-only family, route, and weekly-state dataclasses.
- **Main public API:** `Family(id: int, lat: float, lon: float, sentinels: dict[str, Any], risk_class: str, fixed_day: int | None, last_visit_date: date | None)`; `Route(sequence: list[int] = ..., total_time: float = ..., total_reward: float = ...)`; `WeekState(families: list[Family] = ..., routes: list[Route] = ..., monday_date: date | None = ...)`.
- **Main public API:** `build_family_index(families: Sequence[Family]) -> dict[int, int]`; `node_index(family_id: int, family_index: Mapping[int, int]) -> int`.
- **Deviation/TODO:** These dataclasses are mutable, not frozen. `Family` stores a precomputed `risk_class` and optional `fixed_period_weeks`/`fixed_phase_weeks`; it does not compute risk itself.

### `risk.py`

- **Status:** implemented.
- **Responsibility:** Computes Coelho-Savassi sentinel scores, risk classes, risk weights, and service times.
- **Main public API:** `compute_score(sentinels: Mapping[str, object]) -> int`; `classify(score: int) -> str`; `risk_weight(risk_class: str, config: Config = DEFAULT_CONFIG) -> int`; `service_time(risk_class: str, config: Config = DEFAULT_CONFIG) -> int`; `SENTINEL_POINTS`.
- **Deviation/TODO:** Sentinel point values still carry the existing note requiring verification against the original 2004 article. Synthetic generation now samples sentinel combinations that classify into the requested risk class.

### `reward.py`

- **Status:** implemented.
- **Responsibility:** Calculates family rewards and the weekly reward matrix.
- **Main public API:** `one_sided_gaussian(d: float, mu: float, sigma: float) -> float`; `delay_bonus(days_late: int, config: Config = DEFAULT_CONFIG) -> float`; `family_reward(family: Family, day: int, monday_date: date, config: Config = DEFAULT_CONFIG) -> float`; `reward_matrix(families: Sequence[Family], monday_date: date, config: Config = DEFAULT_CONFIG) -> np.ndarray`.
- **Deviation/TODO:** The delay bonus is recomputed from Monday's date whenever a family reward is evaluated rather than stored in a separate cached weekly object. It is therefore identical for all days for a given family, but not explicitly cached once per week. `is_fixed_active()` determines whether periodic fixed-day reward applies; inactive fixed families use flexible reward. The epsilon cutoff is family-specific: `epsilon_fraction * A_f * w_f * bonus_f`.

### `travel_matrix.py`

- **Status:** implemented, with integration limitations.
- **Responsibility:** Stores asymmetric travel times and retrieves them from OSRM.
- **Main public API:** `TravelMatrix(seconds: np.ndarray, size: int)`; `TravelMatrix.from_square(seconds: Sequence[Sequence[float]]) -> TravelMatrix`; `TravelMatrix.seconds(source: int, destination: int) -> float`; `TravelMatrix.d(source: int, destination: int) -> float`; `TravelMatrix.row_minutes(source: int) -> np.ndarray`; `TravelMatrix.to_ubs_minutes() -> np.ndarray`; `TravelMatrix.nearest_nodes(source: int, count: int) -> np.ndarray`; `TravelMatrix.precompute_nearest_nodes(count: int) -> list[np.ndarray]`; `TravelMatrix.save(path: str | Path) -> None`; `TravelMatrix.load(path: str | Path, size: int) -> TravelMatrix`; `TravelMatrix.from_osrm(coordinates: Sequence[tuple[float, float]], base_url: str, profile: str = "foot", block_size: int = 100, timeout: float = 30.0, max_table_size: int = 100) -> TravelMatrix`.
- **Deviation/TODO:** The vector uses `float32`, not `uint16`. OSRM has not been tested against a real server in this project. `max_table_size=100` is enforced by limiting each source and destination chunk to at most half the table size, so each request contains at most the configured combined coordinate limit.

### `route_utils.py`

- **Status:** partial.
- **Responsibility:** Calculates route time, move deltas, prefixes, and feasibility.
- **Main public API:** `total_time(route: Sequence[int], matrix: TravelMatrix, service_times: Mapping[int, float], family_index: Mapping[int, int]) -> float`; `rebuild_prefixes(route: Sequence[int], matrix: TravelMatrix, family_index: Mapping[int, int]) -> tuple[np.ndarray, np.ndarray]`; `insertion_delta(a: int, x: int, b: int, matrix: TravelMatrix, service_time: float, family_index: Mapping[int, int]) -> float`; `swap_delta(p: int, r: int, n: int, x: int, matrix: TravelMatrix, service_time_r: float, service_time_x: float, family_index: Mapping[int, int]) -> float`; `two_opt_delta(route: Sequence[int], i: int, j: int, matrix: TravelMatrix, forward: np.ndarray, backward: np.ndarray, family_index: Mapping[int, int]) -> float`; `is_feasible(current_time: float, delta: float, config: Config = DEFAULT_CONFIG) -> bool`.
- **Deviation/TODO:** Family IDs are translated through `build_family_index()` and `node_index()`, with UBS node zero reserved. `two_opt_delta` now consumes precomputed forward/backward prefixes and does not rebuild them. Prefixes are rebuilt once after accepted route mutations.

### `construction.py`

- **Status:** implemented.
- **Responsibility:** Constructs all five daily routes concurrently from one global family-used mask.
- **Main public API:** `construct_week(families: Sequence[Family], reward_values: np.ndarray, matrix: TravelMatrix, config: Config, rng: np.random.Generator, family_index: Mapping[int, int], nearest_nodes: list[np.ndarray] | None = None) -> list[Route]`.
- **Deviation/TODO:** All eligible families compete across open days; there is no top-N pool. Active fixed-day families are greedily preferred, while inactive fixed families are treated as flexible. Only the selected day's score vector is recomputed after each assignment. Optional neighbor filtering is geographic and disabled by default.

### `local_search.py`

- **Status:** partial.
- **Responsibility:** Iteratively improves routes through 2-Opt, insertion, and replacement moves.
- **Main public API:** `nearest_neighbors(node: int, candidate_ids: Sequence[int], matrix: TravelMatrix, family_index: dict[int, int], limit: int | None = None) -> list[int]`; `refine_route(route: Route, families: Sequence[Family], rewards: Mapping[int, float], matrix: TravelMatrix, config: Config, family_index: dict[int, int], nearest_nodes: list[np.ndarray] | None = None) -> Route`.
- **Deviation/TODO:** Candidate insertion and replacement uses all unused positive-reward families unless the optional geographic prefilter is enabled. Only active fixed-day families are protected as removed positions. Replacement feasibility now uses `swap_delta` as its single time-delta source. Insertion and replacement deltas are vectorized across candidates. Moves require gain greater than `min_gain`, and each route refinement is bounded by `max_passes`. Metrics expose candidates evaluated and moves accepted.

### `grasp.py`

- **Status:** implemented.
- **Responsibility:** Repeats complete five-day construction and refines each route, retaining the best week.
- **Main public API:** `solve_week(families: Sequence[Family], reward_values: np.ndarray, matrix: TravelMatrix, config: Config, rng: np.random.Generator, family_index: dict[int, int], nearest_nodes: list[np.ndarray] | None = None) -> list[Route]`.
- **Deviation/TODO:** Each iteration derives a sub-seed from the main generator and records iteration rewards, greedy fixed picks, RCL picks, and operator metrics when requested. Inter-day local search remains unimplemented.

### `weekly_planner.py`

- **Status:** partial.
- **Responsibility:** Orchestrates five daily GRASP runs and tracks families used during the week.
- **Main public API:** `plan_week(families: Sequence[Family], matrix: TravelMatrix, monday_date: date, config: Config, family_index: dict[int, int], excluded_ids: set[int] | None = None) -> WeekState`.
- **Deviation/TODO:** It calls `solve_week()` once with the full reward matrix and no external used-mask loop. Neighbor lists are precomputed once per week when enabled. The inter-day local-search extension remains a TODO comment. State persistence and completed-visit updates are not called from this function.

### `families_loader.py`

- **Status:** implemented.
- **Responsibility:** Validates and loads family CSV rows, including sentinel values, fixed days, dates, risk scores, and risk classes.
- **Main public API:** `load_families(path: str | Path, initial_last_visit_date: date | None = None) -> list[Family]`.
- **Deviation/TODO:** `people_per_room` is converted to the two risk sentinel flags. `fixed_day` requires valid period and phase columns. Full family data is not inferred from coordinates alone.

### `state.py`

- **Status:** implemented and partially integrated into the CLI flow.
- **Responsibility:** Saves and loads weekly state as JSON and updates completed visit dates.
- **Main public API:** `save_state(state: WeekState, path: str | Path) -> None`; `load_state(path: str | Path) -> WeekState`; `update_completed_visits(families: list[Family], completed_ids: set[int], visit_date: date) -> None`; `record_planned_but_not_completed(families: list[Family], planned_ids: set[int]) -> None`.
- **Deviation/TODO:** Planned-but-not-completed recording explicitly validates IDs and leaves dates unchanged. The CLI now loads an existing state file when requested and saves the newly planned state, but it does not collect completion status from the user.

### `reports.py`

- **Status:** implemented.
- **Responsibility:** Produces weekly demand, capacity, ideal-day, delay, fixed-day, per-day visit, and per-day overdue metrics.
- **Main public API:** `weekly_report(families: Sequence[Family], state: WeekState, config: Config) -> dict[str, Any]`.
- **Deviation/TODO:** The report uses `config.k * config.week_days` for capacity. Demand is counted by families due by the end of the configured week based on `last_visit_date`; there is no separate demand schedule input. Active fixed families receive per-day infeasibility counts and a warning flag; inactive fixed families are excluded.

### `synthetic_instance.py`

- **Status:** implemented.
- **Responsibility:** Generates synthetic families, risk classes, fixed days, coordinates, and an asymmetric matrix.
- **Main public API:** `generate_instance(family_count: int, rng: np.random.Generator, fixed_fraction: float = 0.2, initial_last_visit_date: date | None = None) -> tuple[list[Family], TravelMatrix]`; `demo_config() -> Config`.
- **Deviation/TODO:** The generator supports `typical` and `peak` risk scenarios, class-targeted sentinel combinations, periodic fixed families, and varied last-visit dates. Risk splits and fixed schedules are synthetic assumptions, not real area data.

### `main.py`

- **Status:** partial.
- **Responsibility:** Provides the command-line entry point for synthetic weekly planning.
- **Main public API:** `build_parser() -> argparse.ArgumentParser`; `main() -> None`.
- **Deviation/TODO:** Synthetic input remains the default, while `--families-file`, `--coords-file`, `--ubs`, `--osrm-url`, and `--state-file` support real family/OSRM coordinates and JSON history. `--coords-file` alone supplies basic `R0` records; `--families-file` supplies sentinel, risk, and periodic fixed-day metadata.

## 3. Data flow

1. `main.py` creates `demo_config()`. It either generates a synthetic instance, loads family CSV data with a separate UBS coordinate, or reads UBS-first coordinates and builds a matrix through a self-hosted OSRM URL. If `--state-file` exists, its family history replaces the generated/basic family records. A completed-visit CSV updates dates before planning, and only visits dated on or after the planning Monday are excluded from that plan.
2. `generate_instance()` selects a typical or peak class distribution, samples class-matching sentinel combinations, varies visit dates and periodic fixed schedules, and creates a synthetic asymmetric `TravelMatrix` with UBS at index 0.
3. `plan_week()` validates runtime configuration and calls `reward_matrix()`, which evaluates risk weights, target intervals, delay bonuses, Gaussian timing, fixed-day rewards, and the epsilon cutoff.
4. `plan_week()` passes the complete reward matrix to `solve_week()` once.
5. Each GRASP iteration runs `construct_week()`, which assigns family/day pairs across all open days using an internal global used mask, then refines each route with local search.
6. The returned `WeekState` is passed to `weekly_report()` by `main.py`. When requested, `main.py` saves the planned state as JSON. Completion updates remain an explicit caller operation through `state.py`.

## 4. Key algorithmic decisions as implemented

- **Reward:** Fixed-day families receive `A_FIXED * risk_weight` on their exact day and zero otherwise. Flexible families receive `A_FLEX * risk_weight * delay_bonus * one_sided_gaussian`. The delay bonus uses `DELAY_BONUS_PER_DAY` and `DELAY_BONUS_CAP`; the cutoff is per-family: `epsilon_fraction * (A_f * w_f * bonus_f)`. With current configured coefficients, the worst fixed reward is `A_FIXED * 1 = 2500`, while the best flexible reward before cutoff is `A_FLEX * 8 * 1.25 = 1000`, so fixed rewards have a 2.5-to-1 margin over the best flexible reward.
- **Construction candidates:** All families that are not globally used and have positive reward for the relevant day are evaluated across all open days. The old `POOL` and reward-based top-N logic are fully removed. `use_neighbor_prefilter` is the optional geographic prefilter flag and defaults to `False`; when enabled, `neighbor_count` is used and active fixed-day families for the current day are added back to that day’s geographic candidate set.
- **Score and RCL:** Each open day maintains a score vector `reward[d, j] / (d(position_d, j) + service_time_j)`. Feasible `(day, family)` pairs are pooled globally. If any pair is a fixed-day family on its own day, the highest-score such pair is selected greedily. Otherwise, pairs with scores at least `s_max - alpha * (s_max - s_min)` form one global RCL and the injected NumPy generator samples a pair.
- **Stopping:** A day closes only when its full feasible `(day, family)` set is empty. The feasibility check includes current route time, travel from that day’s current position, service time, and return travel to the UBS. The week stops when all five days are closed; it does not stop based on `k`.
- **Local search and deltas:** The search tries 2-Opt, insertion, and replacement moves until no move is accepted or `max_passes` is reached. Moves require strict improvement greater than `min_gain`. Insertion and replacement candidate deltas are vectorized; replacement feasibility uses the single `swap_delta` formula. 2-Opt uses asymmetric forward/backward prefixes supplied by the local-search state; prefixes are rebuilt only after accepted mutations, so delta evaluation itself is O(1).
- **Fixed-day protection:** Replacement skips a route position only when its family is active under `is_fixed_active()`. Inactive periodic fixed families can be treated as flexible and replaced.
- **Travel matrix:** `TravelMatrix` stores a contiguous `float32` one-dimensional seconds vector. Element `(i, j)` is accessed at index `i * size + j`. `d(i, j)` and row helpers convert seconds to minutes by dividing by `60.0`. The UBS is conventionally index `0`.

## 5. OSRM integration status

The client is implemented in `TravelMatrix.from_osrm()`. It calls the OSRM `/table/v1/{profile}/...` endpoint, defaults to the `foot` profile, accepts `max_table_size=100`, and keeps combined source/destination coordinate blocks within that limit. Coordinates are emitted as `longitude,latitude`. It uses `requests` only inside that method.

It has not been tested against a real OSRM server in this project; validation has used synthetic matrices and unit tests only.

Install the optional dependency and run a self-hosted OSRM instance with the foot profile. The project does not document or use a public server URL:

```powershell
pip install -e ".[test,osrm]"
osrm-extract -p /opt/foot.lua region.osm.pbf
osrm-partition region.osrm
osrm-customize region.osrm
osrm-routed --algorithm mld --max-table-size 1000 region.osrm
python -m acs_routing.main --coords-file coordinates.csv --osrm-url http://localhost:5000
```

`main.py` accepts `--families-file`, `--coords-file`, `--ubs`, and `--osrm-url` for real-data matrix construction.

`scripts/validate_osrm.py` performs table shape, diagonal, positivity, asymmetry, NaN, and direct-route spot checks. It was not run because no real OSRM server was configured. The pytest integration test is marked `integration` and skips unless `OSRM_URL` is set.

## 6. Tests

The final test run completed with **39 passed, 1 skipped, 0 failed**. The skipped test is the live OSRM integration test because `OSRM_URL` was not configured.

- `tests/test_risk.py`: risk-class cutoff boundaries and sentinel score calculation.
- `tests/test_reward.py`: one-sided Gaussian shape, capped delay bonus, and fixed-versus-flexible reward margin.
- `tests/test_grasp_verification.py`: RCL use, different-seed week variation, reproducibility, and best-of-N reward accounting.
- `tests/test_route_utils.py`: insertion, swap, and asymmetric 2-Opt deltas against full route-time recomputation.
- `tests/test_construction.py`: parallel five-day construction, shift feasibility, closure when a shorter candidate fits, fixed-day greedy selection, score recomputation count, geographic prefiltering, and reproducibility.
- `tests/test_local_search.py`: fixed-day family protection during refinement.
- `tests/test_weekly_planner.py`: shift feasibility and no repeated families across the week.
- `tests/test_travel_matrix.py`: mocked OSRM coordinate order and combined request-size limit.
- `tests/test_state_reports.py`: JSON round trip, completed/planned visit updates, consecutive-week exclusion, and report values including per-day metrics.
- `tests/test_cli_and_synthetic.py`: CLI synthetic argument parsing, current-week completed-visit exclusion, all sentinel keys, and varied due-date situations.
- `tests/test_families_loader.py`: valid family CSV parsing, risk classification, and row error reporting.
- `tests/test_osrm_integration.py`: live OSRM table check, skipped without `OSRM_URL`.

Originally requested behaviors covered by the current tests include risk cutoffs, Gaussian/bonus behavior, reward margin, asymmetric delta comparisons, shift limits, weekly no-repeat behavior, and fixed-day swap protection.

Not directly covered by the current tests are real OSRM communication, live CLI execution with a self-hosted server, multiple-agent planning, and replacement acceptance on a broad random workload.

## 7. How to run

From the `acs_routing` project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
python -m pytest -q
python -m acs_routing.main --synthetic 5
python -m acs_routing.main --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000 --state-file state.json --completed-file completed.csv
python -m scripts.benchmark
```

The required pre-fix diagnosis measured `construct_week` and route refinement separately: 20 families took `0.000955s` construction and `0.000343s` refinement; 50 took `0.001694s` and `0.000976s`; 100 took `0.002747s` construction, after which refinement exceeded the 30-second probe timeout. The refinement stack was the bottleneck, not construction. After adding `MIN_GAIN` and `MAX_PASSES`, the verified run produced `39 passed, 1 skipped` and the synthetic CLI printed five parallel routes plus a weekly report.

The full scenario benchmark command was run with `--sizes 100 300 600 900 --timeout 1`, both scenarios, fixed fractions `0.0` and `0.1`, both prefilter modes, and `n_iter` values `1` and `50`. It produced 18 completed cases and 46 explicit `TIMEOUT` lines. Representative real output was:

```text
families=100 scenario=typical fixed_fraction=0.0 prefilter=False iterations=1 total_seconds=0.047437 total_reward=9802.062 overdue_per_week=[50, 0, 0, 0]
families=100 scenario=typical fixed_fraction=0.0 prefilter=False iterations=50 status=TIMEOUT timeout_seconds=1.0
families=300 scenario=peak fixed_fraction=0.1 prefilter=True iterations=1 total_seconds=0.008778 total_reward=38544.221 overdue_per_week=[150, 280, 266, 245]
families=900 scenario=peak fixed_fraction=0.1 prefilter=True iterations=1 status=TIMEOUT timeout_seconds=1.0
```

The completed 100-family examples had class counts `{'R0': 94, 'R1': 3, 'R2': 2, 'R3': 1}` for typical and `{'R0': 90, 'R1': 4, 'R2': 5, 'R3': 1}` for peak. In the completed examples, `n_iter=1` and `n_iter=50` often had identical total rewards because the same reward-positive family set was visited; RCL and greedy-pick counts still increased across iterations. Full-candidate cases timed out sooner than prefiltered cases. Insertion/replacement accepted moves were zero in most generated cases because construction filled feasible capacity and/or the optional nearest-neighbor set had no improving external candidate; instrumentation now reports those counts instead of hiding them.

| Families | Iterations | Construction s | Refine s | 2-Opt s | Insert s | Replace s | Total s | Visits/day | Route minutes/day | Reward |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- | ---: |
| 20 | 1 | 0.000926 | 0.000260 | 0.000018 | 0.000000 | 0.000000 | 0.001569 | `[1,5,1,0,1]` | `[30.297,151.426,30.649,0,30.643]` | 63146.919 |
| 20 | 50 | 0.041949 | 0.011365 | 0.000775 | 0.000000 | 0.000000 | 0.056990 | `[1,5,1,0,1]` | `[30.297,151.426,30.649,0,30.643]` | 63146.919 |
| 50 | 1 | 0.001598 | 0.000834 | 0.000168 | 0.000000 | 0.000000 | 0.003141 | `[8,4,1,2,2]` | `[228.562,121.945,30.649,61.539,61.247]` | 223329.193 |
| 50 | 50 | 0.074852 | 0.040637 | 0.008545 | 0.000000 | 0.000000 | 0.120474 | `[8,4,1,2,2]` | `[228.562,121.945,30.649,61.539,61.247]` | 223329.193 |
| 100 | 1 | 0.002662 | 0.003973 | 0.001154 | 0.000000 | 0.000000 | 0.008039 | `[11,9,1,11,7]` | `[305.051,245.308,30.649,325.98,215.005]` | 435567.578 |
| 100 | 50 | 0.133505 | 0.179596 | 0.056656 | 0.000000 | 0.000000 | 0.321547 | `[11,9,1,11,7]` | `[305.051,245.308,30.649,325.98,215.005]` | 435567.578 |
| 300 | 1 | 0.007207 | 0.004141 | 0.001219 | 0.000000 | 0.000000 | 0.015750 | `[11,13,12,11,11]` | `[339.17,354.697,359.732,341.867,339.46]` | 996793.141 |
| 300 | 50 | 0.356059 | 0.211960 | 0.063237 | 0.000000 | 0.000000 | 0.585221 | `[11,13,12,11,11]` | `[339.17,354.697,359.732,341.867,339.46]` | 996793.141 |
| 600 | 1 | 0.012278 | 0.004752 | 0.001162 | 0.000000 | 0.000000 | 0.027954 | `[11,11,11,11,11]` | `[346.499,348.533,352.086,350.848,345.697]` | 1100000.000 |
| 600 | 50 | 0.417351 | 0.238700 | 0.057931 | 0.000000 | 0.000000 | 0.688595 | `[11,11,11,11,11]` | `[346.499,348.533,352.086,350.848,345.697]` | 1100000.000 |
| 900 | 1 | 0.010606 | 0.005666 | 0.000838 | 0.000000 | 0.000000 | 0.036527 | `[11,11,11,11,11]` | `[356.91,351.48,353.187,356.076,353.304]` | 1080000.000 |
| 900 | 50 | 0.550295 | 0.291651 | 0.042207 | 0.000000 | 0.000000 | 0.894938 | `[11,11,11,11,11]` | `[356.91,351.48,353.187,356.076,353.304]` | 1080000.000 |

The initial pre-fix benchmark timeout was caused by `refine_route` cycling through accepted moves; after `MIN_GAIN` and `MAX_PASSES`, all requested cases completed. A sequential-versus-parallel comparison was not run because the old implementation is not retained as a runnable working-tree module.

## 8. Known limitations and open items

- Multiple-agent planning is not implemented; the code plans one route per weekday.
- Inter-day local search is not implemented; `weekly_planner.py` contains a TODO extension point.
- There is no database layer; state is JSON-file based.
- State persistence is wired into `main.py`; completion status is supplied through `--completed-file` rather than collected interactively.
- `--coords-file` alone creates basic `R0` family records; `families_loader.py` provides full sentinel/risk CSV loading through `--families-file`.
- `target_interval` values are explicit assumptions and still require definition with the health unit.
- Service times, target intervals, and sentinel point values are assumptions in configuration/code; sentinel values still require checking against the Coelho-Savassi 2004 article.
- The OSRM client has not been verified against a live server.
- Local search is bounded by `MIN_GAIN` and `MAX_PASSES`; broad full-candidate benchmark cases can still exceed a short one-second benchmark timeout.
- Local-search replacement is route-family replacement using the tested `swap_delta` formula, not a conventional two-position swap between existing route positions.
- The coordinate-only CSV path does not provide full sentinel/risk metadata; use `--families-file` for that data.
- Real risk distributions and service-time values have not been validated against area data; typical/peak distributions remain configured assumptions.
