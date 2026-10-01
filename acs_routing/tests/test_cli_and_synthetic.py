from datetime import date, timedelta

import numpy as np

from acs_routing.main import build_parser
from acs_routing.config import Config
from acs_routing.risk import SENTINEL_POINTS
from acs_routing.synthetic_instance import generate_instance


def test_cli_accepts_synthetic_count():
    args = build_parser().parse_args(["--synthetic", "20"])
    assert args.synthetic == 20


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
