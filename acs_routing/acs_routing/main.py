"""Command-line entry point for synthetic weekly planning."""

import argparse
import csv
from datetime import date

import numpy as np

from .reports import weekly_report
from .families_loader import load_families
from .models import Family, build_family_index
from .state import load_state, save_state, update_completed_visits
from .synthetic_instance import demo_config, generate_instance
from .travel_matrix import TravelMatrix
from .weekly_planner import plan_week


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Plan weekly ACS home visits")
    parser.add_argument("--synthetic", type=int, default=30, help="family count")
    parser.add_argument("--families-file", help="CSV family input file")
    parser.add_argument("--ubs", help="UBS coordinates as latitude,longitude")
    parser.add_argument("--osrm-url", help="base URL for a self-hosted OSRM instance")
    parser.add_argument("--coords-file", help="CSV file with id,lat,lon and UBS first")
    parser.add_argument("--state-file", help="JSON file used to load and save planning state")
    parser.add_argument("--completed-file", help="CSV file with completed family visits")
    return parser


def _parse_ubs(value: str) -> tuple[float, float]:
    """Parse UBS latitude and longitude."""
    try:
        latitude, longitude = (float(part) for part in value.split(","))
    except ValueError as error:
        raise ValueError("--ubs must be latitude,longitude") from error
    return latitude, longitude


def _load_coordinates(path: str, initial_last_visit_date: date | None) -> tuple[list[Family], list[tuple[float, float]]]:
    """Load UBS-first coordinates and basic family records from CSV."""
    families: list[Family] = []
    coordinates: list[tuple[float, float]] = []
    with open(path, newline="", encoding="utf-8") as file:
        for row_number, row in enumerate(csv.DictReader(file)):
            family_id = int(row["id"])
            coordinates.append((float(row["lat"]), float(row["lon"])))
            if row_number:
                families.append(
                    Family(
                        family_id,
                        float(row["lat"]),
                        float(row["lon"]),
                        {},
                        "R0",
                        None,
                        initial_last_visit_date,
                    )
                )
    if not coordinates:
        raise ValueError("coords-file must contain a UBS row")
    return families, coordinates


def _load_completed(path: str) -> list[tuple[int, date]]:
    """Load completed family IDs and visit dates from CSV."""
    completed: list[tuple[int, date]] = []
    with open(path, newline="", encoding="utf-8") as file:
        for row_number, row in enumerate(csv.DictReader(file), start=2):
            try:
                completed.append((int(row["id"]), date.fromisoformat(row["visit_date"])))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"completed row {row_number}: {error}") from error
    return completed


def main() -> None:
    """Generate a synthetic week and print its routes and report."""
    args = build_parser().parse_args()
    config = demo_config()
    history = None
    if args.state_file:
        try:
            history = load_state(args.state_file)
        except FileNotFoundError:
            pass
    if args.families_file:
        if not args.osrm_url or not args.ubs:
            raise ValueError("--families-file requires --osrm-url and --ubs")
        families = load_families(
            args.families_file, config.initial_last_visit_date
        )
        ubs = _parse_ubs(args.ubs)
        coordinates = [ubs] + [(family.lat, family.lon) for family in families]
        matrix = TravelMatrix.from_osrm(
            coordinates, args.osrm_url, profile=config.osrm_profile
        )
    elif args.coords_file:
        if not args.osrm_url:
            raise ValueError("--osrm-url is required with --coords-file")
        families, coordinates = _load_coordinates(
            args.coords_file, config.initial_last_visit_date
        )
        matrix = TravelMatrix.from_osrm(
            coordinates, args.osrm_url, profile=config.osrm_profile
        )
    else:
        families, matrix = generate_instance(
            args.synthetic,
            np.random.default_rng(config.seed),
            initial_last_visit_date=config.initial_last_visit_date,
        )
    if history is not None:
        families = history.families
    if args.completed_file:
        completed_by_date: dict[date, set[int]] = {}
        for family_id, visit_date in _load_completed(args.completed_file):
            completed_by_date.setdefault(visit_date, set()).add(family_id)
        for visit_date, family_ids in completed_by_date.items():
            update_completed_visits(families, family_ids, visit_date)
        completed_ids = {
            family_id
            for family_ids in completed_by_date.values()
            for family_id in family_ids
        }
    else:
        completed_ids = set()
    monday = config.initial_date or date.today()
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
    for day, route in enumerate(state.routes, start=1):
        print(f"Day {day}: {route.sequence} ({route.total_time:.1f} minutes, reward {route.total_reward:.1f})")
    print(weekly_report(families, state, config))


if __name__ == "__main__":
    main()
