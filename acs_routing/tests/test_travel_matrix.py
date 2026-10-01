import sys
from types import SimpleNamespace

import numpy as np

from acs_routing.travel_matrix import TravelMatrix


def test_osrm_uses_longitude_latitude_and_respects_table_limit(monkeypatch):
    requests_seen: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self, sources: str, destinations: str):
            self.sources = sources
            self.destinations = destinations

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[list[float]]]:
            source_count = len(self.sources.split(";"))
            destination_count = len(self.destinations.split(";"))
            return {
                "durations": [
                    [float(source * 10 + destination) for destination in range(destination_count)]
                    for source in range(source_count)
                ]
            }

    def fake_get(url: str, params: dict[str, str], timeout: float) -> FakeResponse:
        requests_seen.append((url, params))
        return FakeResponse(params["sources"], params["destinations"])

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fake_get))
    coordinates = [(10.0, 20.0), (11.0, 21.0), (12.0, 22.0), (13.0, 23.0), (14.0, 24.0)]
    matrix = TravelMatrix.from_osrm(
        coordinates,
        "http://osrm.local",
        max_table_size=4,
    )

    assert len(requests_seen) > 1
    assert matrix.size == len(coordinates)
    for url, _ in requests_seen:
        coordinate_text = url.rsplit("/", 1)[-1]
        assert len(coordinate_text.split(";")) <= 4
    assert "/table/v1/foot/20.0,10.0" in requests_seen[0][0]
