"""Load family records from validated CSV input."""

import csv
from datetime import date
from pathlib import Path
from typing import Any

from .models import Family
from .risk import SENTINEL_POINTS, classify, compute_score


_REQUIRED_COLUMNS = {"id", "lat", "lon"}
_OPTIONAL_COLUMNS = {"fixed_day", "last_visit_date", "people_per_room"}
_SENTINEL_COLUMNS = set(SENTINEL_POINTS) - {
    "people_per_room_gt_1",
    "people_per_room_eq_1",
}


def _parse_binary(value: str, column: str) -> bool:
    """Parse a sentinel value represented by 0 or 1."""
    if value not in {"0", "1"}:
        raise ValueError(f"{column} must be 0 or 1")
    return value == "1"


def load_families(
    path: str | Path,
    initial_last_visit_date: date | None = None,
) -> list[Family]:
    """Load and validate families from a CSV file."""
    errors: list[str] = []
    families: list[Family] = []
    seen_ids: set[int] = set()
    with Path(path).open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = (_REQUIRED_COLUMNS | _SENTINEL_COLUMNS) - columns
        if missing:
            raise ValueError("Missing required CSV columns: " + ", ".join(sorted(missing)))
        if "people_per_room" not in columns and not {
            "people_per_room_gt_1",
            "people_per_room_eq_1",
        } <= columns:
            raise ValueError(
                "CSV requires people_per_room or both people_per_room_gt_1 and "
                "people_per_room_eq_1"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                family_id = int(row["id"])
                latitude = float(row["lat"])
                longitude = float(row["lon"])
                if family_id in seen_ids:
                    raise ValueError("duplicate family id")
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    raise ValueError("coordinates are outside valid ranges")
                seen_ids.add(family_id)
                fixed_day = int(row["fixed_day"]) if row.get("fixed_day") else None
                fixed_period = (
                    int(row["fixed_period_weeks"])
                    if row.get("fixed_period_weeks")
                    else None
                )
                fixed_phase = (
                    int(row["fixed_phase_weeks"])
                    if row.get("fixed_phase_weeks")
                    else None
                )
                if fixed_day is not None and fixed_day not in range(1, 6):
                    raise ValueError("fixed_day must be between 1 and 5")
                if fixed_day is not None and (fixed_period is None or fixed_phase is None):
                    raise ValueError(
                        "fixed_day requires fixed_period_weeks and fixed_phase_weeks"
                    )
                if fixed_period is not None and fixed_period <= 0:
                    raise ValueError("fixed_period_weeks must be positive")
                if fixed_phase is not None and fixed_period is not None and not 0 <= fixed_phase < fixed_period:
                    raise ValueError("fixed_phase_weeks must be within the fixed period")
                last_visit_date = (
                    date.fromisoformat(row["last_visit_date"])
                    if row.get("last_visit_date")
                    else initial_last_visit_date
                )
                sentinels: dict[str, Any] = {
                    name: _parse_binary(row[name], name) for name in _SENTINEL_COLUMNS
                }
                if row.get("people_per_room"):
                    people_per_room = float(row["people_per_room"])
                    sentinels["people_per_room_gt_1"] = people_per_room > 1
                    sentinels["people_per_room_eq_1"] = people_per_room == 1
                else:
                    sentinels["people_per_room_gt_1"] = _parse_binary(
                        row["people_per_room_gt_1"], "people_per_room_gt_1"
                    )
                    sentinels["people_per_room_eq_1"] = _parse_binary(
                        row["people_per_room_eq_1"], "people_per_room_eq_1"
                    )
                families.append(
                    Family(
                        family_id,
                        latitude,
                        longitude,
                        sentinels,
                        classify(compute_score(sentinels)),
                        fixed_day,
                        last_visit_date,
                        fixed_period,
                        fixed_phase,
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"row {row_number}: {error}")
    if errors:
        raise ValueError("Invalid family CSV:\n" + "\n".join(errors))
    if not families:
        raise ValueError("Family CSV contains no family rows")
    return families
