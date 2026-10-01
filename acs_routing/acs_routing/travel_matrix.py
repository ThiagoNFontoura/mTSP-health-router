"""Asymmetric travel-time storage and OSRM access."""

from pathlib import Path
from typing import Sequence

import numpy as np


class TravelMatrix:
    """Store an asymmetric square matrix in a contiguous vector."""

    def __init__(self, seconds: np.ndarray, size: int):
        values = np.asarray(seconds, dtype=np.float32).reshape(-1)
        if values.size != size * size:
            raise ValueError("Travel vector must contain size * size values")
        self._seconds = np.ascontiguousarray(values)
        self.size = size

    @classmethod
    def from_square(cls, seconds: Sequence[Sequence[float]]) -> "TravelMatrix":
        """Build a matrix from a square seconds matrix."""
        values = np.asarray(seconds, dtype=np.float32)
        if values.ndim != 2 or values.shape[0] != values.shape[1]:
            raise ValueError("Travel matrix must be square")
        return cls(values, values.shape[0])

    def seconds(self, source: int, destination: int) -> float:
        """Return travel time in seconds."""
        return float(self._seconds[source * self.size + destination])

    def d(self, source: int, destination: int) -> float:
        """Return travel time in minutes."""
        return self.seconds(source, destination) / 60.0

    def row_minutes(self, source: int) -> np.ndarray:
        """Return one origin's travel-time row in minutes."""
        start = source * self.size
        return self._seconds[start : start + self.size].astype(np.float64) / 60.0

    def to_ubs_minutes(self) -> np.ndarray:
        """Return travel times from every node to the UBS in minutes."""
        return self._seconds[:: self.size].astype(np.float64) / 60.0

    def nearest_nodes(self, source: int, count: int) -> np.ndarray:
        """Return a precomputed nearest-node list for one origin."""
        distances = self.row_minutes(source).copy()
        distances[source] = np.inf
        return np.argsort(distances)[:count]

    def precompute_nearest_nodes(self, count: int) -> list[np.ndarray]:
        """Return nearest-node lists for every origin."""
        return [self.nearest_nodes(source, count) for source in range(self.size)]

    def save(self, path: str | Path) -> None:
        """Save the contiguous seconds vector to a NumPy file."""
        np.save(path, self._seconds)

    @classmethod
    def load(cls, path: str | Path, size: int) -> "TravelMatrix":
        """Load a vector saved by ``save``."""
        return cls(np.load(path), size)

    @classmethod
    def from_osrm(
        cls,
        coordinates: Sequence[tuple[float, float]],
        base_url: str,
        profile: str = "foot",
        block_size: int = 100,
        timeout: float = 30.0,
        max_table_size: int = 100,
    ) -> "TravelMatrix":
        """Fetch an asymmetric duration matrix from OSRM in blocks."""
        import requests

        if max_table_size < 2:
            raise ValueError("max_table_size must allow at least one source and destination")
        chunk_size = min(block_size, max_table_size // 2)
        size = len(coordinates)
        result = np.zeros((size, size), dtype=np.float32)
        for source_start in range(0, size, chunk_size):
            source_end = min(size, source_start + chunk_size)
            for destination_start in range(0, size, chunk_size):
                destination_end = min(size, destination_start + chunk_size)
                source_ids = range(source_start, source_end)
                destination_ids = range(destination_start, destination_end)
                ids = list(dict.fromkeys([*source_ids, *destination_ids]))
                coordinate_text = ";".join(
                    f"{coordinates[index][1]},{coordinates[index][0]}" for index in ids
                )
                index_by_local = {index: position for position, index in enumerate(ids)}
                sources = ";".join(
                    str(index_by_local[index]) for index in source_ids
                )
                destinations = ";".join(
                    str(index_by_local[index]) for index in destination_ids
                )
                url = f"{base_url.rstrip('/')}/table/v1/{profile}/{coordinate_text}"
                response = requests.get(
                    url,
                    params={"sources": sources, "destinations": destinations},
                    timeout=timeout,
                )
                response.raise_for_status()
                durations = response.json()["durations"]
                result[source_start:source_end, destination_start:destination_end] = durations
        return cls.from_square(result)

    def __len__(self) -> int:
        return self.size
