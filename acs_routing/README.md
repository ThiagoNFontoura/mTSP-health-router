# acs_routing

Weekly route planning for home visits by community health agents (ACS).

## Structure

- `acs_routing/config.py`: immutable configuration, realistic typical/peak risk assumptions, periodic fixed-day settings, and optional geographic prefiltering.
- `acs_routing/models.py`: data models.
- `acs_routing/families_loader.py`: validated family CSV loading and risk classification.
- `acs_routing/risk.py`: Coelho-Savassi scoring.
- `acs_routing/reward.py`: family reward functions.
- `acs_routing/travel_matrix.py`: asymmetric travel times and OSRM.
- `acs_routing/route_utils.py`: route evaluation and deltas.
- `acs_routing/construction.py`, `local_search.py`, `grasp.py`: parallel five-day construction and per-route optimization with optional geographic prefiltering and reusable route prefixes.
- `acs_routing/weekly_planner.py`: five-day planning through one parallel `solve_week` call.
- `acs_routing/state.py`, `reports.py`: JSON persistence, completed-visit updates, and weekly reports.
- `acs_routing/synthetic_instance.py`, `main.py`: typical/peak synthetic data, periodic fixed schedules, and CLI support for synthetic or self-hosted OSRM inputs.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
python -m pytest -q
python -m acs_routing.main --synthetic 30
```

For a real travel matrix, provide a UBS-first CSV with `id,lat,lon` and a self-hosted OSRM URL:

```powershell
python -m acs_routing.main --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000 --state-file state.json --completed-file completed.csv
```

The OSRM client expects the `foot` profile. A benchmark is available with:

```powershell
python -m scripts.benchmark
python -m scripts.validate_osrm --osrm-url http://localhost:5000 --coords-file coordinates.csv
```
