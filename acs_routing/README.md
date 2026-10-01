# acs_routing

Weekly route planning for community health agent home visits using real family data and a self-hosted OSRM foot-routing service.

## Real-data flow

1. Prepare a family CSV with `id`, `lat`, `lon`, all sentinel columns, optional `fixed_day`, `fixed_period_weeks`, `fixed_phase_weeks`, and `last_visit_date`.
2. Start a self-hosted OSRM instance with the foot profile.
3. Run the CLI with the family file, UBS coordinates, OSRM URL, and optional state/completion files.

```powershell
cd C:\Users\revol\OneDrive\Desktop\mTSP-health-router\acs_routing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[osrm]"
python -m acs_routing.main --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000 --state-file state.json --completed-file completed.csv
```

The completed-visit CSV must contain `id,visit_date`. Configuration can be supplied as JSON or TOML:

```powershell
python -m acs_routing.main --config config.toml --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000
```

## OSRM

Use a self-hosted OSRM instance with the foot profile:

```powershell
osrm-extract -p /opt/foot.lua region.osm.pbf
osrm-partition region.osrm
osrm-customize region.osrm
osrm-routed --algorithm mld --max-table-size 1000 region.osrm
```

Validate a configured server with:

```powershell
python -m scripts.validate_osrm --osrm-url http://localhost:5000 --coords-file coordinates.csv
```

## Modules

- `config.py`: real configuration and JSON/TOML loading.
- `families_loader.py`: validated family CSV loading and risk classification.
- `risk.py`, `reward.py`: risk and reward calculations.
- `travel_matrix.py`: asymmetric travel storage and OSRM table client.
- `construction.py`, `local_search.py`, `grasp.py`: parallel weekly construction and route refinement.
- `weekly_planner.py`: weekly orchestration.
- `state.py`, `reports.py`: JSON state and operational reports.
- `main.py`: real-data CLI entry point.

## Open items

Real risk/service-time validation, live OSRM validation, multiple agents, inter-day local search, and a database layer remain future work. See `IMPLEMENTATION_REPORT.md` for the current implementation state.
