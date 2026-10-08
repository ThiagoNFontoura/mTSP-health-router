"""Offline processing helpers used by the desktop interface."""

from dataclasses import replace
from datetime import date
from pathlib import Path

from .config import DEFAULT_CONFIG, Config
from .families_loader import load_families
from .models import Family, WeekState, build_family_index
from .travel_matrix import TravelMatrix
from .weekly_planner import plan_week


RISK_LABELS = {
    "R0": "normal",
    "R1": "média",
    "R2": "alta",
    "R3": "muito alta",
}


def _virtual_ubs(families: list[Family]) -> tuple[float, float]:
    """Use the geographic centre as the offline route start and end point."""
    return (
        sum(family.lat for family in families) / len(families),
        sum(family.lon for family in families) / len(families),
    )


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
    matrix = TravelMatrix.from_coordinates(coordinates)
    monday = effective_config.initial_date or date.today()
    state = plan_week(
        families,
        matrix,
        monday,
        effective_config,
        build_family_index(families),
    )
    return families, state


def format_plan(
    families: list[Family],
    state: WeekState,
    agents_per_day: int,
) -> str:
    """Create a readable list with every employee and all five weekdays."""
    family_by_id = {family.id: family for family in families}
    lines = [
        f"Famílias carregadas: {len(families)}",
        "Rotas calculadas localmente (distâncias geográficas aproximadas).",
        "",
    ]
    visited: set[int] = set()
    for agent in range(1, agents_per_day + 1):
        lines.append(f"FUNCIONÁRIO {agent}")
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
    return "\n".join(lines)
