# mTSP-health-router

Planejamento semanal de rotas de visitas domiciliares para agentes comunitários de saúde (ACS), partindo de uma UBS, com priorização por risco familiar (Coelho-Savassi) e tempos de deslocamento reais a pé via OSRM.

O repositório tem duas partes:

- [Dataset Generator](#dataset-generator): geração do dataset de famílias.
- [ACS Routing](#acs-routing): o solver de rotas.

---

## Dataset Generator



---

## ACS Routing

Pacote Python (`acs_routing/`) que recebe um CSV de famílias, a localização da UBS e um servidor OSRM, e devolve cinco rotas diárias (segunda a sexta) sem repetir famílias na semana. <!--Revisar: a ideia é integrar com algum banco de dados, e não utilizar CSVs-->

### Como funciona

1. **Risco.** Cada família recebe uma pontuação Coelho-Savassi a partir de sentinelas binárias e é classificada em R0 a R3 (R0: < 5 pontos; R1: 5-6; R2: 7-8; R3: ≥ 9).
2. **Recompensa.** Cada par (família, dia) recebe uma recompensa:
   - *Dia fixo ativo* (`fixed_day`, com período e fase em semanas): recompensa alta (`a_fixed × peso`) somente no dia fixo.
   - *Visita flexível*: `a_flex × peso × bônus`, com decaimento gaussiano conforme a distância ao dia ideal (derivado de `last_visit_date` + intervalo-alvo do risco).
   - O *bônus de atraso* cresce por dia de atraso até um teto; recompensas abaixo de `epsilon_fraction` do máximo viram zero.
3. **Tempos de viagem.** Matriz assimétrica de durações obtida da API `/table` de um OSRM (perfil `foot`), armazenada em um vetor contíguo.
4. **Construção (GRASP).** Cada combinação dia/agente mantém uma pilha independente de famílias. A pontuação de cada candidato é `recompensa / (deslocamento + tempo de atendimento)`. O maior valor global entre as pilhas elegíveis é inserido no caminhamento do seu próprio dia/agente; depois, somente essa pilha é recalculada, porque apenas sua posição atual mudou. Famílias com dia fixo ativo competem normalmente pelo score global, mas só têm recompensa positiva no dia fixo. Só entram candidatos cuja inserção ainda permite voltar à UBS dentro do turno.
5. **Busca local.** Cada rota é refinada com 2-Opt, inserção e substituição de famílias, exigindo ganho mínimo (`min_gain`) e respeitando o turno. Famílias com dia fixo ativo não são substituídas.
6. **Iterações.** Repete construção + refinamento `n_iter` vezes (sub-seeds determinísticas a partir de `seed`) e mantém a semana com maior recompensa total.
7. **Relatório.** Demanda × capacidade, % de visitas no dia ideal, distribuição de atrasos, visitas por dia e alertas de dias fixos inviáveis.

### Requisitos

- Python ≥ 3.11
- `numpy` (obrigatório) e `requests` (extra `osrm`)
- Servidor OSRM com perfil `foot` (veja [OSRM](#osrm))

### Instalação e uso

```powershell
cd acs_routing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[osrm]"
```

#### Interface gráfica

No Windows, dê duplo clique em [`GUI.bat`](GUI.bat), na raiz do
projeto. O script usa o `.venv` local quando ele existe e, caso contrário, usa
o Python disponível no `PATH`.

Selecione o CSV, informe a quantidade de agentes de saúde e processe o arquivo.
O planejamento do CSV é gerado mesmo se o OSRM estiver desligado. Depois,
clique em **Abrir mapa das rotas** para consultar o OSRM e obter as geometrias
viárias reais. A GUI usa o serviço público
`https://router.project-osrm.org` para o mapa; nenhum mapa com linhas retas é
criado. O mapa é salvo em
`%USERPROFILE%\.acs-routing\gui\routes.html` e precisa de internet para
carregar a biblioteca Leaflet e o mapa-base Esri no navegador.

```powershell
python -m acs_routing.main `
  --families-file families.csv `
  --ubs=-30.03,-51.22 `
  --osrm-url http://localhost:5000
```

| Argumento | Obrigatório | Descrição |
|---|---|---|
| `--families-file` | sim | CSV de famílias |
| `--ubs` | sim | Coordenadas da UBS como `lat,lon` |
| `--osrm-url` | sim | URL base do OSRM |
| `--config` | não | Arquivo JSON ou TOML com parâmetros |
| `--state-file` | não | JSON de histórico, lido e sobrescrito a cada execução |
| `--completed-file` | não | CSV `id,visit_date` com visitas realizadas |

> Use `--ubs=lat,lon` (com `=`): como a latitude/longitude são negativas, sem o `=` o `argparse` interpreta o valor como uma opção.

A saída lista, para cada dia, a sequência de IDs (`0` = UBS), o tempo total em minutos e a recompensa, seguida do relatório semanal.

### Entradas

**CSV de famílias** (`--families-file`)

| Coluna | Descrição |
|---|---|
| `id`, `lat`, `lon` | Identificador único e coordenadas |
| `bedridden`, `physical_disability`, `mental_disability`, `poor_sanitation`, `severe_malnutrition`, `drug_addiction`, `unemployment`, `illiteracy`, `under_6_months`, `over_70_years`, `hypertension`, `diabetes` | Sentinelas (`0` ou `1`) |
| `people_per_room` **ou** `people_per_room_gt_1` + `people_per_room_eq_1` | Densidade domiciliar |
| `last_visit_date` (opcional) | `YYYY-MM-DD`; se ausente, usa `initial_last_visit_date` |
| `fixed_day`, `fixed_period_weeks`, `fixed_phase_weeks` (opcionais) | Dia fixo (1-5) e periodicidade; `fixed_day` exige os outros dois |

**Visitas realizadas** (`--completed-file`): colunas `id,visit_date`. Atualizam a última visita das famílias; as realizadas a partir da data de início da semana são excluídas do planejamento.

**Estado** (`--state-file`): quando informado, as famílias (com datas de última visita) vêm do estado salvo; o CSV ainda é validado, mas não é usado como fonte.

### Configuração

Valores padrão em `acs_routing/config.py`; qualquer campo pode ser sobrescrito por JSON ou TOML (campos desconhecidos geram erro):

```toml
n_iter = 100
initial_date = "2026-10-12"   # início da semana planejada (padrão: hoje)

[service_time]
R0 = 10
R1 = 15
R2 = 20
R3 = 30
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `shift_minutes` | 360 | Duração do turno |
| `n_iter` | 50 | Iterações do GRASP |
| `alpha` | 0.3 | Mantido por compatibilidade; a construção atual é gulosa e escolhe sempre o maior score global |
| `seed` | 42 | Semente |
| `service_time` | R0-R3: 10/15/20/30 | Minutos por visita |
| `risk_weight` | R0-R3: 1/2/4/8 | Peso de cada classe |
| `target_interval` | R0-R3: 90/60/30/14 | Dias entre visitas |
| `a_fixed` / `a_flex` | 2500 / 100 | Escala da recompensa fixa / flexível |
| `delay_bonus_per_day` / `delay_bonus_cap` | 0.02 / 1.25 | Bônus por atraso e teto |
| `sigma` | 1.0 | Largura da gaussiana do dia ideal |
| `epsilon_fraction` | 0.01 | Corte de recompensas desprezíveis |
| `use_neighbor_prefilter` / `neighbor_count` | False / 50 | Pré-filtro de vizinhos mais próximos |
| `k` | 14 | Visitas/dia estimadas (apenas relatório de capacidade) |
| `osrm_profile` | foot | Perfil do OSRM |
| `initial_date` | hoje | Data de início da semana |
| `initial_last_visit_date` | 2026-01-01 | Última visita assumida quando ausente |

> Tempos de atendimento, pesos de risco e intervalos-alvo são valores padrão configuráveis, ajustáveis conforme a rotina da unidade de saúde.

### OSRM

```powershell
osrm-extract -p /opt/foot.lua region.osm.pbf
osrm-partition region.osrm
osrm-customize region.osrm
osrm-routed --algorithm mld --max-table-size 1000 region.osrm
```

Para validar o servidor (formato da matriz, diagonal zero, assimetria e conferência com `/route`), a partir de `acs_routing/`:

```powershell
python -m scripts.validate_osrm --osrm-url http://localhost:5000 --coords-file coordinates.csv
```

O CSV de coordenadas deve ter as colunas `lat,lon`, com a UBS na primeira linha. <!--Mesmo ponto de antes: revisar a parte do cSV pois vamos usar uma integração com banco de dados-->

### Módulos

| Módulo | Função |
|---|---|
| `config.py` | Configuração imutável e carga JSON/TOML |
| `models.py` | `Family`, `Route`, `WeekState` e mapeamento ID → nó da matriz |
| `families_loader.py` | Leitura e validação do CSV de famílias |
| `risk.py`, `reward.py` | Pontuação de risco e funções de recompensa |
| `travel_matrix.py` | Matriz assimétrica e cliente OSRM `/table` |
| `construction.py`, `local_search.py`, `grasp.py` | Construção, refinamento e laço GRASP |
| `route_utils.py` | Tempo de rota e deltas dos movimentos |
| `weekly_planner.py` | Orquestração da semana |
| `state.py`, `reports.py` | Persistência JSON e relatórios |
| `main.py` | CLI |
