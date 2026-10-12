"""Typed outcomes for insufficient data and unsupported provider capabilities."""
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

@dataclass(frozen=True)
class InsufficientData:
    reason: str
    home_matches: int
    away_matches: int
    required_matches: int

@dataclass(frozen=True)
class Unsupported:
    capability: str
    reason: str

@dataclass(frozen=True)
class Available(Generic[T]):
    value: T
