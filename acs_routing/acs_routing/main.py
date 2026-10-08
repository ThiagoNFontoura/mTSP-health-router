"""Command-line entry point for real ACS route planning."""

import argparse
import csv
from dataclasses import replace
from datetime import date
from pathlib import Path

from .config import load_config
from .families_loader import load_families
from .models import build_family_index
from .reports import weekly_report
from .state import load_state, save_state, update_completed_visits
from .travel_matrix import TravelMatrix
from .weekly_planner import plan_week


def build_parser() -> argparse.ArgumentParser:
    """Build the real-data command-line parser."""
    parser = argparse.ArgumentParser(description="Plan weekly ACS home visits")
    parser.add_argument("--families-file", required=True, help="CSV family input file")
    parser.add_argument("--ubs", required=True, help="UBS coordinates as latitude,longitude")
    parser.add_argument("--osrm-url", required=True, help="self-hosted OSRM base URL")
    parser.add_argument("--state-file", help="JSON history file")
    parser.add_argument("--completed-file", help="CSV with id,visit_date")
    parser.add_argument("--config", help="JSON or TOML configuration file")
    parser.add_argument(
        "--agents-per-day",
        type=int,
        help="number of ACS agents available each planning day",
    )
    return parser


def _parse_ubs(value: str) -> tuple[float, float]:
    """Parse and validate UBS latitude and longitude."""
    try:
        latitude, longitude = (float(part) for part in value.split(","))
    except ValueError as error:
        raise ValueError("--ubs must be latitude,longitude") from error
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("UBS coordinates are outside valid latitude/longitude ranges")
    return latitude, longitude


def _load_completed(path: str) -> list[tuple[int, date]]:
    """Load completed family IDs and visit dates from CSV."""
    completed: list[tuple[int, date]] = []
    with open(path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not {"id", "visit_date"} <= set(reader.fieldnames):
            raise ValueError("completed CSV requires id and visit_date columns")
        for row_number, row in enumerate(reader, start=2):
            try:
                completed.append((int(row["id"]), date.fromisoformat(row["visit_date"])))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"completed row {row_number}: {error}") from error
    return completed


def main() -> None:
    """Load real data, plan a week, and print routes and report."""
    args = build_parser().parse_args()
    config = load_config(args.config)
    if args.agents_per_day is not None:
        config = replace(config, agents_per_day=args.agents_per_day)
    monday = config.initial_date or date.today()
    families = load_families(args.families_file, config.initial_last_visit_date)
    history = (
        load_state(args.state_file).families
        if args.state_file and Path(args.state_file).exists()
        else None
    )
    if history is not None:
        families = history
    ubs = _parse_ubs(args.ubs)
    coordinates = [ubs] + [(family.lat, family.lon) for family in families]
    matrix = TravelMatrix.from_osrm(
        coordinates,
        args.osrm_url,
        profile=config.osrm_profile,
    )
    completed_ids: set[int] = set()
    if args.completed_file:
        completed_by_date: dict[date, set[int]] = {}
        for family_id, visit_date in _load_completed(args.completed_file):
            completed_by_date.setdefault(visit_date, set()).add(family_id)
        family_ids = {family.id for family in families}
        unknown = set().union(*completed_by_date.values()) - family_ids if completed_by_date else set()
        if unknown:
            raise ValueError("completed CSV contains unknown family IDs")
        for visit_date, ids in completed_by_date.items():
            update_completed_visits(families, ids, visit_date)
        completed_ids = {
            family_id
            for visit_date, ids in completed_by_date.items()
            if visit_date >= monday
            for family_id in ids
        }
    state = plan_week(
        families,
        matrix,
        monday,
        config,
        build_family_index(families),
        excluded_ids=completed_ids,
    )
    if args.state_file:
        save_state(state, args.state_file)
    for route_index, route in enumerate(state.routes):
        day = route.day or (route_index // config.agents_per_day + 1)
        agent = route.agent or (route_index % config.agents_per_day + 1)
        label = f"Day {day}" if config.agents_per_day == 1 else f"Day {day}, Agent {agent}"
        print(
            f"{label}: {route.sequence} "
            f"({route.total_time:.1f} minutes, reward {route.total_reward:.1f})"
        )
    print(weekly_report(families, state, config))


if __name__ == "__main__":
    main()
