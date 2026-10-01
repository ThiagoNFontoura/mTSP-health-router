"""Data models for weekly route planning."""

from dataclasses import dataclass, field
from datetime import date
from collections.abc import Mapping, Sequence
from typing import Any


@dataclass
class Family:
    """Describe one household visited by an agent."""

    id: int
    lat: float
    lon: float
    sentinels: dict[str, Any]
    risk_class: str
    fixed_day: int | None
    last_visit_date: date | None
    fixed_period_weeks: int | None = None
    fixed_phase_weeks: int | None = None


@dataclass
class Route:
    """Describe one route, including the UBS at both ends."""

    sequence: list[int] = field(default_factory=list)
    total_time: float = 0.0
    total_reward: float = 0.0


@dataclass
class WeekState:
    """Store families and routes for one planning week."""

    families: list[Family] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    monday_date: date | None = None


def build_family_index(families: Sequence[Family]) -> dict[int, int]:
    """Map family IDs to matrix nodes, reserving node zero for the UBS."""
    return {family.id: position + 1 for position, family in enumerate(families)}


def node_index(family_id: int, family_index: Mapping[int, int]) -> int:
    """Translate a family ID to its matrix node, preserving UBS node zero."""
    return 0 if family_id == 0 else family_index[family_id]
