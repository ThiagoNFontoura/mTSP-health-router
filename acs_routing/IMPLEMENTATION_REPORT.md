# Implementation Report

## 1. Overview

`acs_routing` plans a five-day set of community health agent home-visit routes from family data, risk classes, rewards, and an asymmetric travel matrix. The weekly planner builds a reward matrix, constructs and locally improves one route per day, and prevents families selected earlier in the week from being selected again. Synthetic data and CSV family input with self-hosted OSRM support are available. The entry point is `acs_routing.main`, which prints routes followed by a weekly report and can persist state.

## 2. Module-by-module summary

### `config.py`

- **Status:** partial.
- **Responsibility:** Defines immutable operational and algorithm configuration.
- **Main public API:** `Config(...)`; `Config.require_runtime_values() -> None`; `DEFAULT_CONFIG`.
- **Deviation/TODO:** `n_iter=50`, `alpha=0.3`, `seed=42`, and target intervals are now executable defaults. The target intervals are explicitly marked assumptions for the health unit. The configuration uses `epsilon_fraction` rather than a constant named `EPSILON`. Optional geographic filtering is implemented with `use_neighbor_prefilter=False` and `neighbor_count=50`. `initial_last_visit_date` defaults to `2026-01-01`.

### `models.py`

- **Status:** implemented.
- **Responsibility:** Defines the data-only family, route, and weekly-state dataclasses.
- **Main public API:** `Family(id: int, lat: float, lon: float, sentinels: dict[str, Any], risk_class: str, fixed_day: int | None, last_visit_date: date | None)`; `Route(sequence: list[int] = ..., total_time: float = ..., total_reward: float = ...)`; `WeekState(families: list[Family] = ..., routes: list[Route] = ..., monday_date: date | None = ...)`.
- **Main public API:** `build_family_index(families: Sequence[Family]) -> dict[int, int]`; `node_index(family_id: int, family_index: Mapping[int, int]) -> int`.
- **Deviation/TODO:** These dataclasses are mutable, not frozen. `Family` stores a precomputed `risk_class`; it does not compute one itself.

### `risk.py`

- **Status:** implemented.
- **Responsibility:** Computes Coelho-Savassi sentinel scores, risk classes, risk weights, and service times.
- **Main public API:** `compute_score(sentinels: Mapping[str, object]) -> int`; `classify(score: int) -> str`; `risk_weight(risk_class: str, config: Config = DEFAULT_CONFIG) -> int`; `service_time(risk_class: str, config: Config = DEFAULT_CONFIG) -> int`; `SENTINEL_POINTS`.
- **Deviation/TODO:** The code contains a comment stating that sentinel values must be checked against the original 2004 article. That verification has not been performed here.

### `reward.py`

- **Status:** implemented.
- **Responsibility:** Calculates family rewards and the weekly reward matrix.
- **Main public API:** `one_sided_gaussian(d: float, mu: float, sigma: float) -> float`; `delay_bonus(days_late: int, config: Config = DEFAULT_CONFIG) -> float`; `family_reward(family: Family, day: int, monday_date: date, config: Config = DEFAULT_CONFIG) -> float`; `reward_matrix(families: Sequence[Family], monday_date: date, config: Config = DEFAULT_CONFIG) -> np.ndarray`.
- **Deviation/TODO:** The delay bonus is recomputed from Monday's date whenever a family reward is evaluated rather than stored in a separate cached weekly object. It is therefore identical for all days for a given family, but not explicitly cached once per week. The epsilon cutoff is family-specific: `epsilon_fraction * A_f * w_f * bonus_f`.

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
- **Responsibility:** Constructs one daily route from all currently eligible positive-reward families.
- **Main public API:** `construct_day(families: Sequence[Family], day: int, day_rewards: Mapping[int, float], matrix: TravelMatrix, config: Config, rng: np.random.Generator, family_index: Mapping[int, int], used_ids: set[int] | None = None, used_mask: np.ndarray | None = None, nearest_nodes: list[np.ndarray] | None = None) -> Route`.
- **Deviation/TODO:** The construction phase no longer has `POOL` or top-N reward truncation. Candidate travel, service, feasibility, and score arrays are evaluated with NumPy. The removed private `-1` reward key and wrapper are no longer used. Optional neighbor filtering is geographic and disabled by default.

### `local_search.py`

- **Status:** partial.
- **Responsibility:** Iteratively improves routes through 2-Opt, insertion, and replacement moves.
- **Main public API:** `nearest_neighbors(node: int, candidate_ids: Sequence[int], matrix: TravelMatrix, family_index: dict[int, int], limit: int | None = None) -> list[int]`; `refine_route(route: Route, families: Sequence[Family], rewards: Mapping[int, float], matrix: TravelMatrix, config: Config, family_index: dict[int, int], nearest_nodes: list[np.ndarray] | None = None) -> Route`.
- **Deviation/TODO:** Candidate insertion and replacement uses all unused positive-reward families unless the optional geographic prefilter is enabled. Fixed-day families are skipped as removed positions during replacement. Replacement feasibility now uses `swap_delta` as its single time-delta source. Precomputed neighbor lists are passed from the weekly planner when filtering is enabled.

### `grasp.py`

- **Status:** implemented.
- **Responsibility:** Repeats daily construction and local refinement and keeps the highest-reward route.
- **Main public API:** `solve_day(families: Sequence[Family], day: int, day_rewards: Mapping[int, float], matrix: TravelMatrix, config: Config, rng: np.random.Generator, family_index: dict[int, int], used_ids: set[int] | None = None, used_mask: np.ndarray | None = None, nearest_nodes: list[np.ndarray] | None = None) -> Route`.
- **Deviation/TODO:** It receives a seeded NumPy generator, family mapping, and optional shared neighbor lists. It does not implement inter-day optimization.

### `weekly_planner.py`

- **Status:** partial.
- **Responsibility:** Orchestrates five daily GRASP runs and tracks families used during the week.
- **Main public API:** `plan_week(families: Sequence[Family], matrix: TravelMatrix, monday_date: date, config: Config, family_index: dict[int, int], excluded_ids: set[int] | None = None) -> WeekState`.
- **Deviation/TODO:** It uses the `(week_days, family_count)` reward matrix, centralized family mapping, and a boolean used mask; it does not create sorted arrays. Neighbor lists are precomputed once per week when enabled. The inter-day local-search extension remains a TODO comment. State persistence and completed-visit updates are not called from this function.

### `families_loader.py`

- **Status:** implemented.
- **Responsibility:** Validates and loads family CSV rows, including sentinel values, fixed days, dates, risk scores, and risk classes.
- **Main public API:** `load_families(path: str | Path, initial_last_visit_date: date | None = None) -> list[Family]`.
- **Deviation/TODO:** `people_per_room` is converted to the two risk sentinel flags. Full family data is not inferred from coordinates alone.

### `state.py`

- **Status:** implemented and partially integrated into the CLI flow.
- **Responsibility:** Saves and loads weekly state as JSON and updates completed visit dates.
- **Main public API:** `save_state(state: WeekState, path: str | Path) -> None`; `load_state(path: str | Path) -> WeekState`; `update_completed_visits(families: list[Family], completed_ids: set[int], visit_date: date) -> None`; `record_planned_but_not_completed(families: list[Family], planned_ids: set[int]) -> None`.
- **Deviation/TODO:** Planned-but-not-completed recording explicitly validates IDs and leaves dates unchanged. The CLI now loads an existing state file when requested and saves the newly planned state, but it does not collect completion status from the user.

### `reports.py`

- **Status:** implemented.
- **Responsibility:** Produces weekly demand, capacity, ideal-day, delay, and fixed-day service metrics.
- **Main public API:** `weekly_report(families: Sequence[Family], state: WeekState, config: Config) -> dict[str, Any]`.
- **Deviation/TODO:** The report uses `config.k * config.week_days` for capacity. Demand is counted by families due by the end of the configured week based on `last_visit_date`; there is no separate demand schedule input.

### `synthetic_instance.py`

- **Status:** implemented.
- **Responsibility:** Generates synthetic families, risk classes, fixed days, coordinates, and an asymmetric matrix.
- **Main public API:** `generate_instance(family_count: int, rng: np.random.Generator, fixed_fraction: float = 0.2, initial_last_visit_date: date | None = None) -> tuple[list[Family], TravelMatrix]`; `demo_config() -> Config`.
- **Deviation/TODO:** The generator now creates all sentinel keys and varies last-visit dates across not-yet-due, due, slightly late, and very late cases. The date categories are synthetic assumptions tied to the default target intervals.

### `main.py`

- **Status:** partial.
- **Responsibility:** Provides the command-line entry point for synthetic weekly planning.
- **Main public API:** `build_parser() -> argparse.ArgumentParser`; `main() -> None`.
- **Deviation/TODO:** Synthetic input remains the default, while `--coords-file`, `--osrm-url`, and `--state-file` support self-hosted OSRM coordinates and JSON history. A coordinate CSV supplies basic `R0` family records; it does not contain full sentinel/risk metadata.

## 3. Data flow

1. `main.py` creates `demo_config()`. It either generates a synthetic instance, loads family CSV data with a separate UBS coordinate, or reads UBS-first coordinates and builds a matrix through a self-hosted OSRM URL. If `--state-file` exists, its family history replaces the generated/basic family records. A completed-visit CSV updates dates before planning and excludes those IDs from the next plan.
2. `generate_instance()` creates all sentinel keys, computes each family score with `compute_score()`, classifies it with `classify()`, varies visit dates/fixed days, and creates a synthetic asymmetric `TravelMatrix` with UBS at index 0.
3. `plan_week()` validates runtime configuration and calls `reward_matrix()`, which evaluates risk weights, target intervals, delay bonuses, Gaussian timing, fixed-day rewards, and the epsilon cutoff.
4. For each configured weekday, `plan_week()` passes that reward row and the boolean used mask to `solve_day()`.
5. `solve_day()` runs construction followed by local search for `n_iter` iterations. Construction adds feasible positive-reward families, then the planner marks route family IDs in the used mask before the next day.
6. The returned `WeekState` is passed to `weekly_report()` by `main.py`. When requested, `main.py` saves the planned state as JSON. Completion updates remain an explicit caller operation through `state.py`.

## 4. Key algorithmic decisions as implemented

- **Reward:** Fixed-day families receive `A_FIXED * risk_weight` on their exact day and zero otherwise. Flexible families receive `A_FLEX * risk_weight * delay_bonus * one_sided_gaussian`. The delay bonus uses `DELAY_BONUS_PER_DAY` and `DELAY_BONUS_CAP`; the cutoff uses `epsilon_fraction` multiplied by the maximum fixed reward. With current configured coefficients, the worst fixed reward is `A_FIXED * 1 = 2500`, while the best flexible reward before cutoff is `A_FLEX * 8 * 1.25 = 1000`, so fixed rewards have a 2.5-to-1 margin over the best flexible reward.
- **Construction candidates:** All families that are not used, not already in the route, and have positive reward for the day are evaluated. The old `POOL` and reward-based top-N logic are fully removed. `use_neighbor_prefilter` is the optional geographic prefilter flag and defaults to `False`; when enabled, `neighbor_count` is used and fixed-day families for the current day are added back to the geographic candidate set.
- **Score and RCL:** The score is `reward_j / (d(current, j) + service_time_j)`. If feasible fixed-day candidates for the current day exist, the highest-score one is selected greedily. Otherwise, candidates with scores at least `s_max - alpha * (s_max - s_min)` form the RCL and the injected NumPy generator samples one candidate.
- **Stopping:** Construction stops when no positive-reward candidate satisfies the remaining-time feasibility check. The check includes current route time, travel to the candidate, service time, and travel from the candidate back to the UBS. It does not stop based on `k`.
- **Local search and deltas:** The search tries 2-Opt, insertion, and replacement moves until no move is accepted. Replacement feasibility uses the single `swap_delta` formula. 2-Opt uses asymmetric forward/backward prefixes supplied by the local-search state; prefixes are rebuilt only after accepted mutations, so delta evaluation itself is O(1).
- **Fixed-day protection:** Replacement skips a route position when its family has a non-`None` `fixed_day`. This protects fixed-day families from being removed by the implemented replacement move.
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

## 6. Tests

The final test run completed with **25 passed, 0 failed, 0 skipped**.

- `tests/test_risk.py`: risk-class cutoff boundaries and sentinel score calculation.
- `tests/test_reward.py`: one-sided Gaussian shape, capped delay bonus, and fixed-versus-flexible reward margin.
- `tests/test_route_utils.py`: insertion, swap, and asymmetric 2-Opt deltas against full route-time recomputation.
- `tests/test_construction.py`: shift feasibility, close-candidate selection without reward truncation, and fixed-day inclusion with geographic prefiltering.
- `tests/test_local_search.py`: fixed-day family protection during refinement.
- `tests/test_weekly_planner.py`: shift feasibility and no repeated families across the week.
- `tests/test_travel_matrix.py`: mocked OSRM coordinate order and combined request-size limit.
- `tests/test_state_reports.py`: JSON round trip, completed/planned visit updates, and report values.
- `tests/test_cli_and_synthetic.py`: CLI synthetic argument parsing, all sentinel keys, and varied due-date situations.
- `tests/test_families_loader.py`: valid family CSV parsing, risk classification, and row error reporting.

Originally requested behaviors covered by the current tests include risk cutoffs, Gaussian/bonus behavior, reward margin, asymmetric delta comparisons, shift limits, weekly no-repeat behavior, and fixed-day swap protection.

Not directly covered by the current tests are real OSRM communication, live CLI execution with a self-hosted server, and multiple-agent planning.

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

The verified run produced `25 passed` and the synthetic CLI printed five daily routes plus a weekly report. The expanded benchmark script prints both iteration counts by default and accepts `--full-candidates`. The final benchmark attempt did not complete the first 100-family case within 120 seconds; a direct 100-family, one-iteration reproduction also exceeded 20 seconds after the mandatory mapping and synthetic-date changes. No timing is invented for the 100, 300, 600, or 900 family cases. This is a real performance limitation: construction and local-search work depend on the selected route sizes and move opportunities, not only on input family count.

## 8. Known limitations and open items

- Multiple-agent planning is not implemented; the code plans one route per weekday.
- Inter-day local search is not implemented; `weekly_planner.py` contains a TODO extension point.
- State persistence is wired into `main.py`; completion status is supplied through `--completed-file` rather than collected interactively.
- Coordinate CSV loading creates basic `R0` family records; full real-instance sentinel/risk loading is not implemented.
- `target_interval` values are explicit assumptions and still require definition with the health unit.
- Service times, target intervals, and sentinel point values are assumptions in configuration/code; sentinel values still require checking against the Coelho-Savassi 2004 article.
- The OSRM client has not been verified against a live server.
- Default 50-iteration performance was attempted and timed out at 100 families during the benchmark check.
- Local-search replacement is route-family replacement using the tested `swap_delta` formula, not a conventional two-position swap between existing route positions.
- The coordinate CSV path does not provide full sentinel/risk metadata.
