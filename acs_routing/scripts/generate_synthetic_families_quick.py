#!/usr/bin/env python3
"""Generate a compact synthetic Porto Alegre family dataset for fast smoke tests."""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path


OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "families_porto_alegre_quick.csv"

SENTINEL_COLUMNS = [
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
    "people_per_room_gt_1",
    "people_per_room_eq_1",
]


def random_bool(probability: float) -> int:
    return 1 if random.random() < probability else 0


def make_family(row_id: int) -> dict[str, str | int]:
    lat = round(random.uniform(-30.09, -29.95), 6)
    lon = round(random.uniform(-51.22, -50.90), 6)

    household_size = random.randint(1, 6)
    people_per_room_gt_1 = 1 if household_size > 1 else 0
    people_per_room_eq_1 = 1 if household_size == 1 else 0

    row = {
        "id": row_id,
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "bedridden": random_bool(0.08),
        "physical_disability": random_bool(0.10),
        "mental_disability": random_bool(0.07),
        "poor_sanitation": random_bool(0.12),
        "severe_malnutrition": random_bool(0.05),
        "drug_addiction": random_bool(0.06),
        "unemployment": random_bool(0.26),
        "illiteracy": random_bool(0.18),
        "under_6_months": random_bool(0.08),
        "over_70_years": random_bool(0.16),
        "hypertension": random_bool(0.22),
        "diabetes": random_bool(0.18),
        "people_per_room_gt_1": people_per_room_gt_1,
        "people_per_room_eq_1": people_per_room_eq_1,
    }

    if random.random() < 0.18:
        row["fixed_day"] = random.randint(1, 5)
        row["fixed_period_weeks"] = random.choice([2, 3, 4])
        row["fixed_phase_weeks"] = random.randint(0, row["fixed_period_weeks"] - 1)
    else:
        row["fixed_day"] = ""
        row["fixed_period_weeks"] = ""
        row["fixed_phase_weeks"] = ""

    days_ago = random.randint(7, 100)
    row["last_visit_date"] = (date.today() - timedelta(days=days_ago)).isoformat()
    return row


def main() -> None:
    random.seed()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "id",
        "lat",
        "lon",
        *SENTINEL_COLUMNS,
        "fixed_day",
        "fixed_period_weeks",
        "fixed_phase_weeks",
        "last_visit_date",
    ]

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row_id in range(1, 51):
            writer.writerow(make_family(row_id))

    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
