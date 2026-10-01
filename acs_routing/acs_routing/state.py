"""JSON persistence for planning state."""

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from .models import Family, Route, WeekState


def _family_to_json(family: Family) -> dict[str, Any]:
    """Serialize a family to JSON-compatible data."""
    value = asdict(family)
    value["last_visit_date"] = (
        family.last_visit_date.isoformat() if family.last_visit_date else None
    )
    return value


def save_state(state: WeekState, path: str | Path) -> None:
    """Save a week state as JSON."""
    payload = {
        "families": [_family_to_json(family) for family in state.families],
        "routes": [asdict(route) for route in state.routes],
        "monday_date": state.monday_date.isoformat() if state.monday_date else None,
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_state(path: str | Path) -> WeekState:
    """Load a week state from JSON."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    families = [
        Family(
            **{
                **item,
                "last_visit_date": (
                    date.fromisoformat(item["last_visit_date"])
                    if item.get("last_visit_date")
                    else None
                ),
            }
        )
        for item in payload["families"]
    ]
    routes = [Route(**item) for item in payload["routes"]]
    monday = date.fromisoformat(payload["monday_date"]) if payload.get("monday_date") else None
    return WeekState(families, routes, monday)


def update_completed_visits(
    families: list[Family], completed_ids: set[int], visit_date: date
) -> None:
    """Update dates only for visits completed on the planned route."""
    for family in families:
        if family.id in completed_ids:
            family.last_visit_date = visit_date


def record_planned_but_not_completed(
    families: list[Family], planned_ids: set[int]
) -> None:
    """Keep prior dates for planned visits that were not completed."""
    family_ids = {family.id for family in families}
    if not planned_ids <= family_ids:
        raise ValueError("planned_ids contains an unknown family")
