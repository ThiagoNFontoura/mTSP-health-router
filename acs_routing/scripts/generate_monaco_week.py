"""Generate a deterministic five-day Monaco dataset for integration tests."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path


HEADERS = [
    "id",
    "lat",
    "lon",
    "bedridden",
    "physical_disability",
    "mental_disability",
    "poor_sanitation",
    "severe_malnutrition",
    "drug_addiction",
    "unemployment",
    "illiteracy",
    "under_6_months",
    "over_70_years",
    "hypertension",
    "diabetes",
    "people_per_room",
    "last_visit_date",
]


def main() -> None:
    """Write 100 R0 families, with 20 becoming due on each weekday."""
    output = Path(__file__).resolve().parents[1] / "families_monaco_week.csv"
    monday_due_date = date(2026, 10, 5)
    r0_interval_days = 90
    rows: list[dict[str, object]] = []

    for family_id in range(1, 101):
        grid_index = family_id - 1
        row_index, column_index = divmod(grid_index, 10)
        ideal_day_offset = grid_index % 5
        due_date = monday_due_date + timedelta(days=ideal_day_offset)
        rows.append(
            {
                "id": family_id,
                "lat": f"{43.7335 + row_index * 0.0009:.6f}",
                "lon": f"{7.4190 + column_index * 0.0011:.6f}",
                "bedridden": 0,
                "physical_disability": 0,
                "mental_disability": 0,
                "poor_sanitation": 0,
                "severe_malnutrition": 0,
                "drug_addiction": 0,
                "unemployment": 0,
                "illiteracy": 0,
                "under_6_months": 0,
                "over_70_years": 0,
                "hypertension": 0,
                "diabetes": 0,
                "people_per_room": 0.8,
                "last_visit_date": (
                    due_date - timedelta(days=r0_interval_days)
                ).isoformat(),
            }
        )

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Created {output} with {len(rows)} families")


if __name__ == "__main__":
    main()
