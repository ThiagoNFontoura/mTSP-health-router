# acs_routing

Weekly route planning for community health agent home visits using real family data and a self-hosted OSRM foot-routing service.

## Local desktop interface

Run the simple offline interface with:

```powershell
python -m acs_routing.gui
```

Choose the family CSV, enter the number of health agents available per day and
their active time in minutes, then click **Processar e gerar rotas**. The
active time is the maximum duration of each agent's daily route. The result
is grouped by agent and day and shows each family's calculated priority.
All five weekdays are displayed, including empty days. Families that do not
fit are listed as not scheduled in the current week.

The interface normalizes the planning date to that week's Monday. After the
priority-based optimization, it fills remaining same-week capacity with
unassigned flexible families whenever they fit without exceeding active time.
Active fixed-day families remain restricted to their configured weekday.

The desktop interface does not require a web server or OSRM. It estimates car
travel locally from straight-line geographic distance at an assumed urban
speed of 30 km/h and uses the families' geographic centre as a virtual UBS.
The CLI below continues to use OSRM street-network times for operational
planning.

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

Para executar com três agentes por dia:

```powershell
python -m acs_routing.main --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000 --state-file state-3-agents.json --agents-per-day 3
```

Para executar o solver e renderizar o mapa no mesmo pipe, acrescente
`--render-output`:

```powershell
python -m acs_routing.main `
  --families-file data\families_porto_alegre_synthetic.csv `
  --ubs=-30.02267067,-51.06028531 `
  --osrm-url https://router.project-osrm.org `
  --agents-per-day 3 `
  --state-file data\poa-synthetic-state-osrm-3-agents.json `
  --render-output data\poa-synthetic-routes-osrm-3-agents.html
```

Esse comando salva o estado e, em seguida, chama o renderer automaticamente
usando a mesma URL e o mesmo perfil do OSRM.

The completed-visit CSV must contain `id,visit_date`. Configuration can be supplied as JSON or TOML:

```powershell
python -m acs_routing.main --config config.toml --families-file families.csv --ubs -23.55,-46.63 --osrm-url http://localhost:5000
```

Set `agents_per_day` in the JSON/TOML configuration, or pass
`--agents-per-day`, to create one route per available agent on each day. The
default is `1`, preserving the original behavior. Routes are optimized
together and a family can be assigned only once across the whole week.

### Renderizar rotas no mapa

Quando o planejamento for salvo com `--state-file`, as rotas podem ser renderizadas
em um mapa HTML autocontido:

```powershell
python scripts/render_routes_map.py `
  --state-file state.json `
  --ubs=-23.55,-46.63 `
  --output routes_map.html
```

O mapa usa longitude no eixo horizontal e latitude no eixo vertical, incluindo a UBS
e as geometrias das rotas. Os limites são calculados pela casa mais à esquerda, mais à
direita, mais acima e mais abaixo, com margem visual padrão de 8% em cada lado.
Use `--margin 0.12` para aumentar a margem. Cada rota recebe uma cor própria;
os filtros permitem selecionar o agente e o dia.

Para desenhar o caminho real das ruas, informe o mesmo OSRM usado pelo solver:

```powershell
python scripts/render_routes_map.py `
  --state-file state.json `
  --ubs=-23.55,-46.63 `
  --osrm-url http://localhost:5000 `
  --osrm-profile foot `
  --output routes_map_osrm.html
```

Sem `--osrm-url`, o renderer desenha segmentos retos entre as casas. Com a opção,
cada rota consulta `/route/v1/{profile}` do OSRM com `geometries=geojson` e usa a
geometria viária retornada. O HTML usa um basemap viário público do Esri, sem chave de API,
filtros compactos por agente e dia (sem legenda colorida no cabeçalho). O pan e o zoom são
limitados à área das rotas com margem visual; o limite é reaplicado após cada
movimento ou alteração de zoom.

### Interface gráfica local

Na pasta `acs_routing`, com o ambiente virtual ativado, execute:

```powershell
cd C:\Users\revol\OneDrive\Desktop\mTSP-health-router\acs_routing
.\.venv\Scripts\Activate.ps1
python -m acs_routing.gui
```

Na janela, escolha o CSV, informe a quantidade de agentes de saúde por dia e
o tempo ativo de cada agente, e clique em **Processar e gerar rotas**. Essa
interface é offline: calcula deslocamentos por distância geográfica e não
gera o HTML do mapa OSRM. Para gerar o HTML, use o comando da CLI com
`--render-output`.

## Synthetic test data scripts

Este script gera dados sintéticos dentro dos padrões necessários para o `acs_routing.families_loader.load_families`. Informe o número desejado de linhas, default é 100. O caminho do output é: `data/families_porto_alegre_synthetic.csv`.

```bash
cd acs_routing
python3 scripts/generate_synthetic_families.py [PREENCHER]
```

Após gerar os dados, é possível validar eles com o seguinte comando:

```bash
python3 - <<'PY'
from pathlib import Path
from acs_routing.families_loader import load_families

path = Path('data/families_porto_alegre_synthetic.csv')
rows = load_families(path)
print(path, len(rows), sorted({r.risk_class for r in rows}))
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
