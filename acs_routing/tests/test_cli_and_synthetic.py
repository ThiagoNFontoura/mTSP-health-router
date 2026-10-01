from datetime import date, timedelta

import numpy as np

from acs_routing.main import _load_completed, build_parser
from acs_routing.config import Config
from acs_routing.risk import SENTINEL_POINTS
from acs_routing.synthetic_instance import generate_instance


def test_cli_accepts_synthetic_count():
    args = build_parser().parse_args(["--synthetic", "20"])
    assert args.synthetic == 20


def test_completed_visit_exclusion_is_current_week_only(tmp_path):
    path = tmp_path / "completed.csv"
    path.write_text(
        "id,visit_date\n10,2026-01-04\n20,2026-01-05\n",
        encoding="utf-8",
    )
    records = _load_completed(str(path))
    monday = date(2026, 1, 5)
    excluded = {family_id for family_id, visit_date in records if visit_date >= monday}
    assert excluded == {20}


def test_synthetic_instance_has_all_sentinel_types_and_date_situations():
    families, _ = generate_instance(20, np.random.default_rng(42))
    assert set(SENTINEL_POINTS) <= set(families[0].sentinels)
    reference = date(2026, 1, 5)
    intervals = Config().target_interval
    day_offsets = [
        (family.last_visit_date + timedelta(days=intervals[family.risk_class]) - reference).days
        for family in families
    ]
    assert any(offset > 0 for offset in day_offsets)
    assert any(offset == 0 for offset in day_offsets)
    assert any(-5 < offset < 0 for offset in day_offsets)
    assert any(offset <= -5 for offset in day_offsets)


def test_synthetic_typical_and_peak_risk_proportions():
    for scenario, targets in (
        ("typical", {"R1": 0.55, "R2": 0.30, "R3": 0.15}),
        ("peak", {"R1": 9 / 22, "R2": 11 / 22, "R3": 2 / 22}),
    ):
        families, _ = generate_instance(900, np.random.default_rng(42), scenario=scenario)
        counts = {risk_class: sum(family.risk_class == risk_class for family in families) for risk_class in ("R1", "R2", "R3")}
        classified = sum(counts.values())
        if scenario == "typical":
            assert abs(classified / 900 - 0.06) <= 0.02
        else:
            assert abs(classified / 900 - (22 / 227)) <= 0.02
        for risk_class, share in targets.items():
            assert abs(counts[risk_class] / classified - share) <= 0.02
