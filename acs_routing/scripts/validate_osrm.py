"""Validate a self-hosted OSRM foot-profile table and route response."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import requests

from acs_routing.travel_matrix import TravelMatrix


def _coordinates(path: str | Path) -> list[tuple[float, float]]:
    """Read UBS-first latitude/longitude coordinates from CSV."""
    with Path(path).open(newline="", encoding="utf-8") as file:
        return [(float(row["lat"]), float(row["lon"])) for row in csv.DictReader(file)]


def main() -> None:
    """Run OSRM table and route consistency checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--osrm-url", required=True)
    parser.add_argument("--coords-file", required=True)
    args = parser.parse_args()
    coordinates = _coordinates(args.coords_file)
    matrix = TravelMatrix.from_osrm(coordinates, args.osrm_url, profile="foot")
    checks: list[tuple[str, bool, str]] = []
    values = [matrix.seconds(source, destination) for source in range(matrix.size) for destination in range(matrix.size)]
    checks.append(("shape", matrix.size == len(coordinates), f"{matrix.size}x{matrix.size}"))
    checks.append(("zero diagonal", all(matrix.seconds(index, index) == 0 for index in range(matrix.size)), ""))
    checks.append(("positive off-diagonal", all(value > 0 for value in values if value != 0), ""))
    asymmetry = max(
        abs(matrix.seconds(source, destination) - matrix.seconds(destination, source))
        for source in range(matrix.size)
        for destination in range(matrix.size)
    )
    checks.append(("asymmetry present", asymmetry > 0, f"max_delta={asymmetry:.3f}s"))
    checks.append(("no NaN/None", all(value == value for value in values), ""))
    if matrix.size >= 2:
        first = coordinates[0]
        second = coordinates[1]
        url = (
            f"{args.osrm_url.rstrip('/')}"
            f"/route/v1/foot/{first[1]},{first[0]};{second[1]},{second[0]}"
        )
        response = requests.get(url, params={"overview": "false"}, timeout=30.0)
        response.raise_for_status()
        direct_seconds = float(response.json()["routes"][0]["duration"])
        checks.append(
            (
                "route spot check",
                abs(matrix.seconds(0, 1) - direct_seconds) < 1e-3,
                f"table={matrix.seconds(0, 1):.3f}s route={direct_seconds:.3f}s",
            )
        )
    passed = True
    for name, result, detail in checks:
        status = "PASS" if result else "FAIL"
        print(f"{status} {name} {detail}")
        passed &= result
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()