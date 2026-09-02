"""A measured curve, and the pair of points that broke a claim."""

from __future__ import annotations

import pytest

from django_query_contract import Growth, QueryGrowth
from tests.growth_worlds import point

pytestmark = pytest.mark.django_db


def test_the_axes_read_back_in_the_order_they_ran() -> None:
    measured = QueryGrowth(points=(point(1, 4), point(10, 9)))

    assert measured.factors == (1, 10)
    assert measured.counts == (4, 9)


def test_a_curve_that_held_has_no_violation() -> None:
    measured = QueryGrowth(points=(point(1, 4), point(10, 4)))

    assert measured.first_violation(Growth.CONSTANT) is None
    assert measured.holds(Growth.CONSTANT)


def test_a_violation_names_both_ends_of_the_pair_that_broke_it() -> None:
    """The pair, not the curve: a message needs two numbers to compare."""
    smaller, larger = point(1, 4), point(10, 9)

    violation = QueryGrowth(points=(smaller, larger)).first_violation(Growth.CONSTANT)

    assert violation == (smaller, larger)


def test_one_measurement_can_be_judged_against_more_than_one_claim() -> None:
    """Why the claim is an argument rather than a field on the measurement.

    A block that fails ``CONSTANT`` and holds ``LINEAR`` is bulk work; one that
    fails both is a defect. Both answers come off one run of the block.
    """
    measured = QueryGrowth(points=(point(1, 3), point(10, 21)))

    assert not measured.holds(Growth.CONSTANT)
    assert measured.holds(Growth.LINEAR)


def test_the_first_failing_pair_is_the_one_reported() -> None:
    """Consecutive pairs, so the two worlds a reader is shown are adjacent.

    The count holds from 1 to 2 and breaks from 2 to 4. Reporting the widest
    span instead would name two worlds further apart and say less about where
    the change happened.
    """
    first, second, third = point(1, 4), point(2, 4), point(4, 9)

    violation = QueryGrowth(points=(first, second, third)).first_violation(Growth.CONSTANT)

    assert violation == (second, third)


def test_a_curve_of_three_that_holds_every_step_holds_overall() -> None:
    """The transitivity that makes checking consecutive pairs sufficient.

    Each step keeps the count per unit of data no higher than the step before,
    so the whole curve does, and the widest pair needs no separate check.
    """
    measured = QueryGrowth(points=(point(1, 10), point(2, 15), point(4, 20)))

    assert measured.holds(Growth.LINEAR)
    assert Growth.LINEAR.permits(measured.points[0], measured.points[2])
