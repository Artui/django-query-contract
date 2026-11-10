from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from django_query_contract.types.growth import Growth
from django_query_contract.types.growth_point import GrowthPoint


@dataclass(frozen=True, slots=True)
class QueryGrowth:
    """What one block did at several scale factors."""

    points: tuple[GrowthPoint, ...]
    """One per scale factor, in the order they ran, which is ascending by factor."""

    @property
    def factors(self) -> tuple[int, ...]:
        """The factors measured, ascending."""
        return tuple(point.factor for point in self.points)

    @property
    def counts(self) -> tuple[int, ...]:
        """The statement count at each factor, in the same order as ``factors``."""
        return tuple(point.count for point in self.points)

    def first_violation(self, growth: Growth) -> tuple[GrowthPoint, GrowthPoint] | None:
        """The first consecutive pair of points that broke ``growth``."""
        for smaller, larger in pairwise(self.points):
            if not growth.permits(smaller, larger):
                return smaller, larger
        return None

    def holds(self, growth: Growth) -> bool:
        """Whether the whole curve stayed inside ``growth``."""
        return self.first_violation(growth) is None
