"""Offline processing helpers used by the desktop interface."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from .config import DEFAULT_CONFIG, Config
from .families_loader import load_families
from .models import Family, WeekState, build_family_index
from .reward import family_reward, is_fixed_active
from .risk import risk_weight, service_time
from .reports import weekly_report
from .route_utils import insertion_delta, total_time
from .travel_matrix import TravelMatrix
from .weekly_planner import plan_week


RISK_LABELS = {
    "R0": "normal",
    "R1": "média",
    "R2": "alta",
    "R3": "muito alta",
}

CAR_SPEED_KMH = 30.0


def _virtual_ubs(families: list[Family]) -> tuple[float, float]:
    """Use the geographic centre as the offline route start and end point."""
    return (
        sum(family.lat for family in families) / len(families),
        sum(family.lon for family in families) / len(families),
    )


def _fill_unused_capacity(
    families: list[Family],
    state: WeekState,
    matrix: TravelMatrix,
    config: Config,
    monday: date,
    family_index: dict[int, int],
) -> None:
    """Insert unassigned families into feasible gaps without removing visits."""
    family_by_id = {family.id: family for family in families}
    service_times = {
        family.id: service_time(family.risk_class, config) for family in families
    }
    assigned = {
        family_id
        for route in state.routes
        for family_id in route.sequence
        if family_id != 0
    }

    while True:
        # Minimize added route time as a secondary objective. Risk breaks ties.
        best: tuple[float, int, int, int, int] | None = None
        for family in families:
            if family.id in assigned:
                continue
            fixed_active = is_fixed_active(family, monday)
            for route_index, route in enumerate(state.routes):
                if fixed_active and route.day != family.fixed_day:
                    continue
                for position in range(1, len(route.sequence)):
                    delta = insertion_delta(
                        route.sequence[position - 1],
                        family.id,
                        route.sequence[position],
                        matrix,
                        service_times[family.id],
                        family_index,
                    )
                    if route.total_time + delta > config.shift_minutes:
                        continue
                    candidate = (
                        delta,
                        -risk_weight(family.risk_class, config),
                        family.id,
                        route_index,
                        position,
                    )
                    if best is None or candidate < best:
                        best = candidate

        if best is None:
            break

        _, _, family_id, route_index, position = best
        route = state.routes[route_index]
        selected_family = family_by_id[family_id]

        route.sequence.insert(position, selected_family.id)
        route.total_time = total_time(
            route.sequence,
            matrix,
            service_times,
            family_index,
        )
        route.total_reward += family_reward(
            selected_family,
            route.day or 1,
            monday,
            config,
        )
        assigned.add(selected_family.id)


def process_csv(
    csv_path: str | Path,
    agents_per_day: int,
    shift_minutes: int = 360,
    config: Config = DEFAULT_CONFIG,
) -> tuple[list[Family], WeekState]:
    """Load a family CSV and produce one weekly plan without external services."""
    if agents_per_day <= 0:
        raise ValueError("O número de funcionários deve ser maior que zero.")
    if shift_minutes <= 0:
        raise ValueError("O tempo ativo deve ser maior que zero.")
    effective_config = replace(
        config,
        agents_per_day=agents_per_day,
        shift_minutes=shift_minutes,
    )
    families = load_families(csv_path, effective_config.initial_last_visit_date)
    ubs = _virtual_ubs(families)
    coordinates = [ubs] + [(family.lat, family.lon) for family in families]
    matrix = TravelMatrix.from_coordinates(coordinates, speed_kmh=CAR_SPEED_KMH)
    planning_date = effective_config.initial_date or date.today()
    monday = planning_date - timedelta(days=planning_date.weekday())
    family_index = build_family_index(families)
    state = plan_week(
        families,
        matrix,
        monday,
        effective_config,
        family_index,
    )
    _fill_unused_capacity(
        families,
        state,
        matrix,
        effective_config,
        monday,
        family_index,
    )
    return families, state


def format_plan(
    families: list[Family],
    state: WeekState,
    agents_per_day: int,
    config: Config = DEFAULT_CONFIG,
) -> str:
    """Create a readable list with every health agent and all five weekdays."""
    family_by_id = {family.id: family for family in families}
    lines = [
        f"Famílias carregadas: {len(families)}",
        (
            "Semana iniciada em: "
            + (state.monday_date.strftime("%d/%m/%Y") if state.monday_date else "-")
        ),
        (
            "Rotas calculadas localmente para deslocamento de carro "
            f"({CAR_SPEED_KMH:g} km/h, distância geográfica aproximada)."
        ),
        "",
    ]
    visited: set[int] = set()
    for agent in range(1, agents_per_day + 1):
        lines.append(f"AGENTE {agent}")
        routes_by_day = {
            route.day: route
            for route in state.routes
            if route.agent == agent
        }
        for day in range(1, 6):
            route = routes_by_day.get(day)
            family_ids = (
                [family_id for family_id in route.sequence if family_id != 0]
                if route
                else []
            )
            if not family_ids:
                lines.append(f"  Dia {day} — nenhuma visita programada")
                continue
            lines.append(f"  Dia {day} — {route.total_time:.1f} minutos")
            for position, family_id in enumerate(family_ids, start=1):
                family = family_by_id[family_id]
                priority = RISK_LABELS.get(family.risk_class, family.risk_class)
                lines.append(
                    f"    {position} - Família {family_id} "
                    f"(prioridade {family.risk_class} — {priority})"
                )
                visited.add(family_id)
        lines.append("")
    lines.append(f"Total programado: {len(visited)} de {len(families)} famílias.")
    pending = [family.id for family in families if family.id not in visited]
    if pending:
        lines.append("Não programadas nesta semana: " + ", ".join(map(str, pending)))
    report = weekly_report(
        families,
        state,
        replace(config, agents_per_day=agents_per_day),
    )
    lines.extend(
        [
            "",
            "Indicadores após o cálculo das rotas:",
        ]
    )
    risk_totals = report["risk_family_totals"]
    risk_visited = report["risk_family_visited"]
    risk_percentages = report["risk_family_visit_percentages"]
    for risk_class in ("R1", "R2", "R3"):
        lines.append(
            f"  {risk_class}: {risk_visited.get(risk_class, 0)} de "
            f"{risk_totals.get(risk_class, 0)} famílias visitadas "
            f"({risk_percentages.get(risk_class, 0.0):.1f}%)"
        )
    lines.append(
        "  Famílias de dia fixo não atendidas no dia previsto: "
        f"{report['active_fixed_not_served']}"
    )
    lines.append(
        "  Famílias atrasadas por intervalo entre visitas não atendidas: "
        f"{report['overdue_not_served']}"
    )
    lines.append(
        "  Maior atraso entre as famílias não atendidas: "
        f"{report['max_overdue_days_since_last_visit']} dias desde a última visita"
    )
    return "\n".join(lines)
