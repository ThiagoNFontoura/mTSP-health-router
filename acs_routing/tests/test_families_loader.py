from datetime import date

import pytest

from acs_routing.families_loader import load_families
from acs_routing.risk import SENTINEL_POINTS


def test_load_families_csv_computes_risk(tmp_path):
    sentinel_columns = sorted(
        set(SENTINEL_POINTS) - {"people_per_room_gt_1", "people_per_room_eq_1"}
    )
    header = ",".join(["id", "lat", "lon", "fixed_day", "last_visit_date", "people_per_room", *sentinel_columns])
    values = ["10", "-1.0", "2.0", "3", "2026-01-01", "2.0", *("1" for _ in sentinel_columns)]
    path = tmp_path / "families.csv"
    path.write_text(header + "\n" + ",".join(values) + "\n", encoding="utf-8")

    families = load_families(path)

    assert families[0].id == 10
    assert families[0].fixed_day == 3
    assert families[0].last_visit_date == date(2026, 1, 1)
    assert families[0].risk_class == "R3"
    assert families[0].sentinels["people_per_room_gt_1"] is True


def test_load_families_reports_row_errors(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text(
        "id,lat,lon,people_per_room,bedridden,physical_disability,mental_disability,poor_sanitation,severe_malnutrition,drug_addiction,unemployment,illiteracy,under_6_months,over_70_years,hypertension,diabetes\n"
        "bad,0,0,1,0,0,0,0,0,0,0,0,0,0,0,2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="row 2"):
        load_families(path)
