"""Validate a saved multi-agent weekly plan against OSRM and configuration."""

from __future__ import annotations

import argparse
import csv
from datetime import date

from acs_routing.config import load_config
from acs_routing.state import load_state
from acs_routing.travel_matrix import TravelMatrix
from acs_routing.validation import validate_plan


def _completed_ids(path: str | None, monday: date) -> set[int]:
    """Load IDs completed during or after the saved planning week began."""
    if path is None:
        return set()
    completed: set[int] = set()
    with open(path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not {"id", "visit_date"} <= set(reader.fieldnames):
            raise ValueError("completed CSV requires id and visit_date columns")
        for row_number, row in enumerate(reader, start=2):
            try:
                visit_date = date.fromisoformat(row["visit_date"])
                if visit_date >= monday:
                    completed.add(int(row["id"]))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"completed row {row_number}: {error}") from error
    return completed


def _parse_ubs(value: str) -> tuple[float, float]:
    """Parse UBS coordinates as latitude,longitude."""
    try:
        latitude, longitude = (float(part) for part in value.split(","))
    except ValueError as error:
        raise ValueError("--ubs must be latitude,longitude") from error
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("UBS coordinates are outside valid ranges")
    return latitude, longitude


def build_parser() -> argparse.ArgumentParser:
    """Build the saved-plan validation CLI."""
    parser = argparse.ArgumentParser(
        description="Validate a saved weekly plan without modifying it"
    )
    parser.add_argument("--plan-file", required=True, help="saved WeekState JSON")
    parser.add_argument("--ubs", required=True, help="UBS as latitude,longitude")
    parser.add_argument("--osrm-url", required=True, help="OSRM base URL")
    parser.add_argument("--config", help="JSON or TOML configuration file")
    parser.add_argument(
        "--completed-file",
        help="optional CSV with id,visit_date used when the plan was created",
    )
    return parser


def main() -> None:
    """Load, independently recalculate, and report saved-plan validity."""
    args = build_parser().parse_args()
    config = load_config(args.config)
    config.require_runtime_values()
    state = load_state(args.plan_file)
    if state.monday_date is None:
        raise ValueError("saved plan requires monday_date")
    ubs = _parse_ubs(args.ubs)
    coordinates = [ubs] + [(family.lat, family.lon) for family in state.families]
    matrix = TravelMatrix.from_osrm(
        coordinates,
        args.osrm_url,
        profile=config.osrm_profile,
    )
    excluded = _completed_ids(args.completed_file, state.monday_date)
    result = validate_plan(state, matrix, config, excluded)

    for message in result.passed:
        print(f"PASS {message}")
    for message in result.failed:
        print(f"FAIL {message}")
    for message in result.information:
        print(f"INFO {message}")
    raise SystemExit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
