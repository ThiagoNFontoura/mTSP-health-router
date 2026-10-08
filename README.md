# ACS-ROUTING

Ferramenta de linha de comando para o **planejamento semanal de visitas domiciliares** de agentes comunitários de saúde (ACS). A partir de uma UBS, o ACS-ROUTING monta rotas de segunda a sexta-feira priorizando famílias por **risco (Coelho-Savassi)**, periodicidade, atraso e restrições de dia fixo, usando **tempos reais de deslocamento a pé** obtidos via [OSRM](https://project-osrm.org/).

## Sumário

- [Visão geral](#visão-geral)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Uso](#uso)
- [Dados de entrada](#dados-de-entrada)
- [Como o algoritmo funciona](#como-o-algoritmo-funciona)
- [Configuração](#configuração)
- [OSRM](#osrm)
- [Validação](#validação)
- [Organização dos módulos](#organização-dos-módulos)
- [Estado atual e limitações](#estado-atual-e-limitações)

---

## Visão geral

O ACS-ROUTING recebe:

- um CSV de famílias;
- as coordenadas da UBS;
- um servidor OSRM com perfil `foot`;
- opcionalmente, um arquivo de configuração, um arquivo de estado e um CSV de visitas realizadas.

E produz um planejamento semanal de segunda a sexta-feira, com **uma ou mais rotas por dia** (uma por agente disponível), **sem atribuir a mesma família mais de uma vez na semana**. O planejamento considera risco familiar, periodicidade das visitas, atrasos, restrições de dia fixo, tempo de atendimento, deslocamentos e a duração máxima do turno.

A saída traz, para cada dia/agente, a sequência de IDs visitados (`0` = UBS), a duração total e a recompensa da rota, seguidas de um relatório operacional semanal.

## Requisitos

- Python ≥ 3.11
- `numpy` ≥ 1.24 (obrigatório)
- `requests` ≥ 2.31 (extra `osrm`)
- Servidor OSRM com perfil `foot` (veja [OSRM](#osrm))

O pacote está em `acs_routing/` e é distribuído como `acs-routing` versão `0.1.0`.

## Instalação

```powershell
cd acs_routing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[osrm]"
```

## Uso

Exemplo mínimo (um agente por dia):

```powershell
python -m acs_routing.main `
  --families-file families.csv `
  --ubs=-23.55,-46.63 `
  --osrm-url http://localhost:5000
```

Exemplo com persistência de estado, histórico de visitas e múltiplos agentes:

```powershell
python -m acs_routing.main `
  --families-file families.csv `
  --ubs=-23.55,-46.63 `
  --osrm-url http://localhost:5000 `
  --state-file state.json `
  --completed-file completed.csv `
  --agents-per-day 5
```

| Argumento | Obrigatório | Descrição |
|---|---|---|
| `--families-file` | sim | CSV de famílias |
| `--ubs` | sim | Coordenadas da UBS no formato `lat,lon` |
| `--osrm-url` | sim | URL base de um servidor OSRM acessível |
| `--config` | não | Configuração em JSON ou TOML |
| `--state-file` | não | Estado em JSON, lido e atualizado a cada execução |
| `--completed-file` | não | CSV `id,visit_date` com visitas realizadas |
| `--agents-per-day` | não | Número de agentes/rotas por dia (padrão: `1`) |

> **Atenção:** use `--ubs=lat,lon` (com `=`). Como as coordenadas costumam ser negativas, sem o `=` o `argparse` interpreta o valor como se fosse uma opção.

## Dados de entrada

### CSV de famílias (`--families-file`)

| Coluna | Obrigatória | Descrição |
|---|---|---|
| `id` | sim | Identificador único da família |
| `lat`, `lon` | sim | Coordenadas geográficas |
| `bedridden`, `physical_disability`, `mental_disability`, `poor_sanitation`, `severe_malnutrition`, `drug_addiction`, `unemployment`, `illiteracy`, `under_6_months`, `over_70_years`, `hypertension`, `diabetes` | sim | Sentinelas binárias (`0` ou `1`) |
| `people_per_room` **ou** `people_per_room_gt_1` + `people_per_room_eq_1` | sim | Densidade domiciliar (uma das duas formas) |
| `last_visit_date` | não | Data da última visita (`YYYY-MM-DD`). Se ausente, usa `initial_last_visit_date` |
| `fixed_day` | não | Dia fixo de visita, de 1 a 5 |
| `fixed_period_weeks`, `fixed_phase_weeks` | não* | Periodicidade e fase da visita fixa. *Obrigatórias quando `fixed_day` é informado |

O carregador valida IDs duplicados, coordenadas, sentinelas, datas, classificação de risco e campos de periodicidade.

### Visitas realizadas (`--completed-file`)

```text
id,visit_date
```

As visitas atualizam a data de última visita das famílias. Visitas realizadas **a partir do início da semana planejada** são excluídas do planejamento daquela semana.

### Estado persistido (`--state-file`)

Quando informado, o estado JSON mantém as famílias e suas datas de última visita, e é atualizado a cada execução. O CSV continua sendo validado, mas **o estado salvo passa a ser a fonte dos dados de planejamento**.

## Como o algoritmo funciona

1. **Classificação de risco.** Calcula a pontuação Coelho-Savassi a partir das sentinelas e classifica cada família:

   | Classe | Pontuação |
   |---|---|
   | R0 | < 5 |
   | R1 | 5–6 |
   | R2 | 7–8 |
   | R3 | ≥ 9 |

2. **Recompensa por família e dia.**
   - Famílias com **dia fixo ativo** recebem recompensa alta somente no dia fixado.
   - Famílias **flexíveis** recebem recompensa conforme o peso de risco, o dia ideal, a distância até o dia ideal e o atraso.
   - O atraso gera um bônus por dia, limitado por um teto.
   - Recompensas abaixo de `epsilon_fraction` do máximo são zeradas.

3. **Tempos de deslocamento.** Solicita uma matriz assimétrica de durações ao endpoint `/table` do OSRM (perfil `foot`). A matriz é guardada em estrutura contígua e convertida de segundos para minutos.

4. **Construção GRASP.** Mantém uma rota independente para cada combinação dia/agente e uma máscara global de famílias já usadas. Cada candidato é pontuado por:

   ```text
   recompensa / (deslocamento + tempo de atendimento)
   ```

   O melhor candidato global elegível é inserido na própria rota. Só são aceitas inserções que ainda permitam retornar à UBS dentro do turno.

5. **Busca local.** Refina cada rota com 2-Opt, inserção e substituição. Os movimentos exigem ganho mínimo (`min_gain`) e respeitam o limite do turno. Famílias com dia fixo ativo não são substituídas.

6. **Iterações.** Repete construção e refinamento `n_iter` vezes, com sub-seeds determinísticas derivadas de `seed`, e mantém a semana com a maior recompensa total.

7. **Relatório operacional.** Calcula demanda × capacidade, percentual de visitas no dia ideal, distribuição de atrasos, visitas por dia e alertas de dias fixos inviáveis.

## Configuração

Os valores padrão ficam em `acs_routing/config.py` e podem ser sobrescritos por JSON ou TOML (via `--config`). **Campos desconhecidos geram erro.**

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
|---|---:|---|
| `shift_minutes` | `360` | Duração máxima do turno (min) |
| `n_iter` | `50` | Iterações do GRASP |
| `alpha` | `0.3` | Mantido por compatibilidade; a construção atual é gulosa |
| `seed` | `42` | Semente determinística |
| `service_time` | R0–R3: `10/15/20/30` | Minutos de atendimento por visita |
| `risk_weight` | R0–R3: `1/2/4/8` | Peso de cada classe de risco |
| `target_interval` | R0–R3: `90/60/30/14` | Dias entre visitas |
| `a_fixed` / `a_flex` | `2500` / `100` | Escala das recompensas fixa / flexível |
| `delay_bonus_per_day` / `delay_bonus_cap` | `0.02` / `1.25` | Bônus por dia de atraso e teto |
| `sigma` | `1.0` | Largura da gaussiana do dia ideal |
| `epsilon_fraction` | `0.01` | Corte de recompensas desprezíveis |
| `use_neighbor_prefilter` / `neighbor_count` | `False` / `50` | Pré-filtro geográfico opcional |
| `k` | `14` | Estimativa de visitas/dia, usada apenas no relatório |
| `osrm_profile` | `foot` | Perfil de roteamento do OSRM |
| `initial_date` | hoje | Início da semana planejada |
| `initial_last_visit_date` | `2026-01-01` | Data assumida quando não há última visita |

> **Importante:** tempos de atendimento, pesos de risco e intervalos-alvo são **premissas configuráveis** e devem ser validados com a unidade de saúde antes de qualquer uso operacional.

## OSRM

O fluxo operacional usa uma instância OSRM com perfil de caminhada:

```powershell
osrm-extract -p /opt/foot.lua region.osm.pbf
osrm-partition region.osrm
osrm-customize region.osrm
osrm-routed --algorithm mld --max-table-size 1000 region.osrm
```

Para validar o servidor, a partir de `acs_routing/`:

```powershell
python -m scripts.validate_osrm `
  --osrm-url http://localhost:5000 `
  --coords-file coordinates.csv
```

O CSV de coordenadas do validador deve conter as colunas `lat,lon`, com a **UBS na primeira linha**. O validador verifica o formato da matriz, a diagonal zero, a assimetria e a consistência com chamadas `/route`.

## Validação

Depois de salvar um plano, é possível verificá-lo de forma independente:

```powershell
python -m acs_routing.main `
  --config config.toml `
  --families-file families.csv `
  --ubs=-23.55,-46.63 `
  --osrm-url http://localhost:5000 `
  --state-file plan.json

python -m scripts.validate_plan `
  --plan-file plan.json `
  --config config.toml `
  --ubs=-23.55,-46.63 `
  --osrm-url http://localhost:5000
```

O validador verifica restrições rígidas, totais persistidos e o limite de optimalidade da recompensa primária. A optimalidade global só é certificada quando o plano atinge a soma da maior recompensa possível de cada família elegível. Tempo de deslocamento e equilíbrio de carga são reportados separadamente, pois **não** são o objetivo de seleção atual do GRASP.

## Organização dos módulos

| Módulo | Função |
|---|---|
| `config.py` | Configurações imutáveis e carga JSON/TOML |
| `models.py` | `Family`, `Route`, `WeekState` e mapeamento de IDs para nós da matriz |
| `families_loader.py` | Leitura e validação do CSV de famílias |
| `risk.py` | Pontuação e classificação Coelho-Savassi |
| `reward.py` | Recompensas fixas/flexíveis, periodicidade, dia ideal e atraso |
| `travel_matrix.py` | Matriz assimétrica e cliente OSRM `/table` |
| `construction.py` | Construção simultânea de rotas por dia/agente |
| `local_search.py` | 2-Opt, inserção e substituição |
| `grasp.py` | Iterações e seleção da melhor semana |
| `route_utils.py` | Cálculo de duração e deltas de movimentos |
| `weekly_planner.py` | Orquestração semanal e exclusão de visitas concluídas |
| `state.py` | Persistência JSON e atualização de visitas |
| `reports.py` | Relatórios operacionais |
| `validation.py` | Verificações independentes de rota, atribuição, tempo, recompensa e objetivo principal |
| `main.py` | Ponto de entrada da CLI |
| `scripts/validate_osrm.py` | Validação de um servidor OSRM em execução |
| `scripts/validate_plan.py` | Validação de um plano salvo |

## Estado atual e limitações

### Implementado

- Planejamento semanal multiagente (`--agents-per-day`), sem repetição de famílias na semana.
- Classificação de risco, recompensas com dia fixo/flexível e bônus de atraso.
- Construção GRASP e busca local (2-Opt, inserção, substituição) respeitando o turno de cada rota.
- Persistência de estado em arquivo JSON e incorporação de visitas realizadas via CSV.
- Relatório operacional semanal e validadores independentes (`validate_osrm`, `validate_plan`).
- Testes de regressão para alocação multiagente, unicidade de famílias, limites individuais de turno, relatórios e comportamento padrão de um agente.

### Ainda não validado

- O caminho de integração com o OSRM e o validador live **ainda não foram executados contra um servidor real**, pois não havia serviço OSRM configurado durante a implementação.
- Distribuições reais de risco, valores das sentinelas, tempos de atendimento e intervalos-alvo precisam ser validados com dados da unidade de saúde.
- Os valores da classificação Coelho-Savassi precisam ser confirmados com a referência de 2004.

### Trabalho futuro (não implementado)

- Busca local **entre dias**.
- Substituição da persistência em arquivos JSON/CSV por uma **camada de banco de dados**.
- Execução da validação OSRM ao vivo como etapa de verificação.
