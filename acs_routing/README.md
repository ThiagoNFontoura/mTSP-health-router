# acs_routing

Weekly route planning for community health agent home visits using real family data and a self-hosted OSRM foot-routing service.

## Local desktop interface

Run the simple offline interface with:

```powershell
python -m acs_routing.gui
```

Choose the family CSV, enter the number of employees available per day and
their active time in minutes, then click **Processar e gerar rotas**. The
active time is the maximum duration of each employee's daily route. The result
is grouped by employee and day and shows each family's calculated priority.
All five weekdays are displayed, including empty days. Families that do not
fit are listed as not scheduled in the current week.

The desktop interface does not require a web server or OSRM. It estimates
travel times locally from straight-line geographic distance and uses the
families' geographic centre as a virtual UBS. The CLI below continues to use
OSRM street-network times for operational planning.

## Real-data flow

1. Prepare a family CSV with `id`, `lat`, `lon`, all sentinel columns, optional `fixed_day`, `fixed_period_weeks`, `fixed_phase_weeks`, and `last_visit_date`.
2. Start a self-hosted OSRM instance with the foot profile.
3. Run the CLI with the family file, UBS coordinates, OSRM URL, and optional state/completion files.

```powershell
cd C:\Users\revol\OneDrive\Desktop\mTSP-health-router\acs_routing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[osrm]"
python -m acs_routing.main --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000 --state-file state.json --completed-file completed.csv --agents-per-day 5
```

The completed-visit CSV must contain `id,visit_date`. Configuration can be supplied as JSON or TOML:

```powershell
python -m acs_routing.main --config config.toml --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000
```

Set `agents_per_day` in the JSON/TOML configuration, or pass
`--agents-per-day`, to create one route per available agent on each day. The
default is `1`, preserving the original behavior. Routes are optimized
together and a family can be assigned only once across the whole week.
## Synthetic test data scripts

This project includes two generator scripts under `scripts/` for synthetic Porto Alegre test data. They are meant to create CSV files that match the loader contract used by `acs_routing.families_loader.load_families`.

### Quick dataset for fast smoke tests

- Script: `scripts/generate_synthetic_families_quick.py`
- Output: `data/families_porto_alegre_quick.csv`
- Size: 50 rows
- Best for: quick validation, route debugging, and short local runs

```bash
cd acs_routing
python3 scripts/generate_synthetic_families_quick.py
```

### Default dataset for fuller testing

- Script: `scripts/generate_synthetic_families.py`
- Output: `data/families_porto_alegre_synthetic.csv`
- Size: 100 rows
- Best for: more representative weekly planning and benchmarking

```bash
cd acs_routing
python3 scripts/generate_synthetic_families.py
```

Both scripts generate synthetic data with:

- valid Porto Alegre coordinates
- required household IDs and geo fields
- health-risk sentinel flags required by the risk classifier
- optional fixed-day scheduling fields
- last-visit dates to simulate overdue and priority logic

After generation, you can validate them directly with the project loader:

```bash
python3 - <<'PY'
from pathlib import Path
from acs_routing.families_loader import load_families

for name in [
    'data/families_porto_alegre_quick.csv',
    'data/families_porto_alegre_synthetic.csv',
]:
    path = Path(name)
    rows = load_families(path)
    print(name, len(rows), sorted({r.risk_class for r in rows}))
PY
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

Save a generated plan and validate its hard constraints, stored totals, and
primary reward optimality bound independently:

```powershell
python -m acs_routing.main --config config.toml --families-file families.csv --ubs=-23.55,-46.63 --osrm-url http://localhost:5000 --state-file plan.json
python -m scripts.validate_plan --plan-file plan.json --config config.toml --ubs=-23.55,-46.63 --osrm-url http://localhost:5000
```

The validator certifies global optimality only when a valid plan reaches the
sum of every eligible family's maximum possible reward. It reports travel-time
and workload-balance optimality separately because those are not the current
GRASP selection objective.

## Modules

- `config.py`: real configuration and JSON/TOML loading.
- `families_loader.py`: validated family CSV loading and risk classification.
- `risk.py`, `reward.py`: risk and reward calculations.
- `travel_matrix.py`: asymmetric travel storage and OSRM table client.
- `construction.py`, `local_search.py`, `grasp.py`: simultaneous multi-agent weekly construction and route refinement.
- `weekly_planner.py`: weekly orchestration.
- `state.py`, `reports.py`: JSON state and operational reports.
- `validation.py`, `scripts/validate_plan.py`: independent saved-plan checks and reward optimality certificate.
- `main.py`: real-data CLI entry point.

## Open items

Real risk/service-time validation, live OSRM validation, inter-day local search, and a database layer remain future work. See `IMPLEMENTATION_REPORT.md` for the current implementation state.
