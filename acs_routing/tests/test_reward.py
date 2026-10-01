from datetime import date

from acs_routing.config import Config
from acs_routing.models import Family
from acs_routing.reward import delay_bonus, family_reward, one_sided_gaussian


def config() -> Config:
    return Config(
        target_interval={"R0": 30, "R1": 21, "R2": 14, "R3": 7},
        n_iter=1,
        alpha=0.3,
        seed=1,
    )


def test_one_sided_gaussian_rises_and_flattens():
    assert one_sided_gaussian(-2, 0, 1) < one_sided_gaussian(-1, 0, 1)
    assert one_sided_gaussian(0, 0, 1) == 1
    assert one_sided_gaussian(2, 0, 1) == 1


def test_delay_bonus_is_capped():
    assert delay_bonus(100, config()) == 1.25


def test_fixed_reward_margin():
    fixed = Family(1, 0, 0, {}, "R0", 1, date(2026, 1, 1))
    flexible = Family(2, 0, 0, {}, "R3", None, date(2026, 1, 1))
    assert family_reward(fixed, 1, date(2026, 1, 5), config()) > family_reward(
        flexible, 1, date(2026, 1, 5), config()
    )


def test_flexible_risk_classes_have_the_same_effective_window():
    low_risk = Family(1, 0, 0, {}, "R0", None, date(2025, 12, 8))
    high_risk = Family(2, 0, 0, {}, "R3", None, date(2025, 12, 31))
    settings = config()
    low_days = [
        day
        for day in range(1, settings.week_days + 1)
        if family_reward(low_risk, day, date(2026, 1, 5), settings) > 0
    ]
    high_days = [
        day
        for day in range(1, settings.week_days + 1)
        if family_reward(high_risk, day, date(2026, 1, 5), settings) > 0
    ]
    assert len(low_days) == len(high_days)
    assert len(low_days) == 5


def test_flexible_r0_peak_reward_is_not_zeroed():
    family = Family(1, 0, 0, {}, "R0", None, date(2025, 12, 8))
    assert family_reward(family, 3, date(2026, 1, 5), config()) > 0
