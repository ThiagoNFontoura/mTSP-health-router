import os

import pytest

from acs_routing.travel_matrix import TravelMatrix


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("OSRM_URL"), reason="OSRM_URL is not configured")
def test_live_osrm_table():
    """Validate a live self-hosted OSRM table for two coordinates."""
    matrix = TravelMatrix.from_osrm(
        [(0.0, 0.0), (0.001, 0.001)], os.environ["OSRM_URL"], profile="foot"
    )
    assert matrix.size == 2
    assert matrix.seconds(0, 0) == 0
    assert matrix.seconds(0, 1) > 0
