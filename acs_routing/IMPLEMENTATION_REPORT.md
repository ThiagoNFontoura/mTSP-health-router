# Current State

## Modules

- `config.py`: immutable algorithm and operational settings with JSON/TOML loading. Service times, risk weights, and target intervals remain assumptions to validate with the health unit.
- `models.py`: family, route, weekly state, and mandatory family-ID to matrix-node mapping.
- `risk.py`: Coelho-Savassi scoring and risk classification. Sentinel values still require verification against the 2004 article.
- `reward.py`: fixed/flexible rewards, periodic fixed-day activity, Gaussian timing, delay bonuses, and family-specific epsilon cutoffs.
- `travel_matrix.py`: contiguous asymmetric travel storage, seconds-to-minutes conversion, persistence, nearest nodes, and self-hosted OSRM `/table` integration.
- `families_loader.py`: validated family CSV loading, sentinel parsing, risk classification, periodic fixed-day fields, duplicate-ID checks, and coordinate validation.
- `construction.py`: simultaneous day/agent construction with one global family-used mask, full candidate evaluation, active fixed-day priority, and optional geographic filtering.
- `local_search.py`: bounded 2-Opt, insertion, and replacement refinement. Moves require `MIN_GAIN`; replacement uses `swap_delta` and inactive fixed families may be replaced.
- `grasp.py`: repeated weekly construction/refinement with deterministic sub-seeds and best-total-reward selection.
- `weekly_planner.py`: real weekly orchestration and current-week completed-family exclusion.
- `state.py`: JSON state persistence and completed/planned visit updates.
- `reports.py`: capacity, demand, delay, per-day visits, overdue distribution, and active fixed-day infeasibility warnings.
- `validation.py`: independent route, assignment, time, reward, and primary-objective optimality checks.
- `scripts/validate_osrm.py`: live OSRM table and route spot-check validation.
- `scripts/validate_plan.py`: command-line validation of an exact saved plan.
- `main.py`: real-data CLI only.

## Real data flow

`main.py` loads `Config` from optional JSON/TOML, validates a family CSV, parses UBS coordinates, requests an asymmetric foot-profile OSRM table, loads optional JSON state, applies current-week completed visits, and calls `plan_week`. The planner computes rewards, constructs one route per day and agent simultaneously, refines each route, persists state when requested, and prints routes plus the operational report.

Required CLI inputs are `--families-file`, `--ubs`, and `--osrm-url`. Optional inputs are `--config`, `--state-file`, `--completed-file`, and `--agents-per-day`.

## Validation status

The package includes regression tests for multi-agent allocation, uniqueness,
individual shift limits, reporting, and the one-agent default. The OSRM
validator and integration path have not been run against a live server because
no OSRM service was configured.

## Open items

- Real risk distributions, sentinel values, service times, and target intervals require validation with health-unit data.
- Inter-day local search is still a TODO extension point.
- Persistence is JSON-file based; there is no database layer.
- Live OSRM validation remains pending.
