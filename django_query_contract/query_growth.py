"""A measured growth curve, and whether it stayed inside a claim."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from django_query_contract.growth import Growth
from django_query_contract.growth_point import GrowthPoint


@dataclass(frozen=True, slots=True)
class QueryGrowth:
    """What one block did at several scale factors.

    The measurement, kept separate from the claim on purpose. ``measure_query_growth``
    produces one of these and makes no assertion at all; ``assert_query_growth``
    is a thin layer that measures and then compares against a
    :class:`~django_query_contract.Growth`. That split is the same one the rest
    of the package makes -- a capture is data, a finding is a reading of it, and
    a report is a rendering -- and it is what lets the CI-report face plot a
    curve without a test runner or a claim in the loop.

    A measurement can be compared against more than one claim, which is
    occasionally what you want: a block that fails ``CONSTANT`` and holds
    ``LINEAR`` is bulk work, and a block that fails both is a defect.
    """

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
        """The first consecutive pair of points that broke ``growth``.

        Consecutive pairs decide the whole curve, because both rules are
        transitive: if every step kept the count equal then all of them are
        equal, and if every step left the count-per-unit-of-data no higher than
        the step before then the whole curve did. Checking every pair instead
        would find the same violations and report a wider one, which names two
        worlds that are further apart and is therefore less use to a reader.

        Returns:
            The lower and higher measurement of the first pair that broke the
            claim, or ``None`` when nothing did.
        """
        for smaller, larger in pairwise(self.points):
            if not growth.permits(smaller, larger):
                return smaller, larger
        return None

    def holds(self, growth: Growth) -> bool:
        """Whether the whole curve stayed inside ``growth``."""
        return self.first_violation(growth) is None
