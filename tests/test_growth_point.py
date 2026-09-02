"""One point on a growth curve: a factor, a size, and everything the block ran."""

from __future__ import annotations

import pytest

from django_query_contract import GrowthPoint, QueryCapture, find_n_plus_one
from tests.growth_worlds import capture_of, point
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db


def test_the_count_is_the_captures_length() -> None:
    """The y-axis is not stored, it is read, so it cannot disagree with the capture."""
    measured = point(3, 7)

    assert measured.count == 7
    assert len(measured.capture) == 7


def test_a_point_reports_the_size_the_world_gave_it() -> None:
    measured = point(10, 1, rows=1000)

    assert measured.factor == 10
    assert measured.rows == 1000


def test_a_world_that_counted_nothing_leaves_the_size_unknown() -> None:
    """``None`` rather than a guess, for the same reason a missing call site is."""
    assert point(1, 1).rows is None


def test_the_capture_is_whole_enough_to_diagnose_the_growth() -> None:
    """The reason a point keeps the capture rather than only the number.

    "One thousand statements at factor 10" says a count grew. The capture behind
    it says which statement grew and from which line, through the same detector
    every other face of this package reads.
    """
    for name in ("a", "b"):
        Book.objects.create(author=Author.objects.create(name=name), title="b")

    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())
    measured = GrowthPoint(factor=10, rows=None, capture=capture)

    findings = find_n_plus_one(measured.capture)

    assert findings[0].count == 2
    assert findings[0].call_site is not None


def test_a_point_carries_the_ceiling_the_capture_measured() -> None:
    """A growth run is the regime where Django's own query log stops counting.

    A per-row statement over a thousand rows at a factor or two more is
    thousands of statements in one block, which is exactly where
    ``CaptureQueriesContext`` starts under-reporting. The point does not have to
    do anything about that; it has to not lose it.
    """
    measured = GrowthPoint(factor=1, rows=None, capture=capture_of(2))

    assert measured.capture.ceilings != ()
