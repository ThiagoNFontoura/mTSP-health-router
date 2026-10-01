from acs_routing.risk import classify, compute_score


def test_risk_cutoffs():
    assert classify(4) == "R0"
    assert classify(5) == "R1"
    assert classify(6) == "R1"
    assert classify(7) == "R2"
    assert classify(8) == "R2"
    assert classify(9) == "R3"


def test_score_uses_sentinel_points():
    assert compute_score({"bedridden": True, "unemployment": True}) == 5
