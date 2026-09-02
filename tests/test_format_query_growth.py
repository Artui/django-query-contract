"""The paragraph a growth failure prints, and the table underneath it."""

from __future__ import annotations

import pytest

from django_query_contract import Growth, QueryGrowth, format_query_growth
from tests.growth_worlds import point

pytestmark = pytest.mark.django_db


def test_a_failing_curve_leads_with_the_claim_that_broke() -> None:
    measured = QueryGrowth(points=(point(1, 3, rows=4), point(10, 21, rows=40)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert report.splitlines()[0] == "The query count is not constant across the scale factors."


def test_the_table_aligns_every_factor_size_and_count() -> None:
    """A reader compares numbers by looking down a column, not across a sentence."""
    measured = QueryGrowth(points=(point(1, 3, rows=4), point(10, 21, rows=40)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert "  factor  1    4 rows    3 statements" in report
    assert "  factor 10   40 rows   21 statements" in report


def test_a_curve_whose_worlds_never_counted_themselves_drops_the_size_column() -> None:
    """A column that says "unknown" on every row is a column about the harness."""
    measured = QueryGrowth(points=(point(1, 3), point(10, 21)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert "  factor  1    3 statements" in report
    assert "rows" not in report


def test_a_world_that_counted_nothing_beside_one_that_did_is_marked() -> None:
    """The column stays when any world reported a size, so the rows still line up."""
    measured = QueryGrowth(points=(point(1, 3, rows=4), point(10, 21)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert "  factor  1   4 rows    3 statements" in report
    assert "  factor 10   - rows   21 statements" in report


def test_the_rule_that_broke_is_stated_in_the_numbers_that_broke_it() -> None:
    measured = QueryGrowth(points=(point(1, 3), point(10, 21)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert "Factor 1 ran 3 and factor 10 ran 21." in report


def test_a_linear_failure_names_the_count_that_would_have_held() -> None:
    measured = QueryGrowth(points=(point(1, 5), point(4, 65)))

    report = format_query_growth(measured, Growth.LINEAR)

    assert report.splitlines()[0] == "The query count grows faster than the data."
    assert "that allows 20 at factor 4; 65 ran." in report


def test_the_failing_world_is_described_by_the_report_every_face_uses() -> None:
    """The N+1 under a growth failure reads exactly as it does under a count failure.

    Two renderings of one finding is two chances to describe it differently, and
    a reader has no way to tell which of them is the package's actual opinion.
    """
    measured = QueryGrowth(points=(point(1, 3), point(10, 21)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert "At factor 10 the block ran:" in report
    assert "21 statements captured: 21 on 'default'." in report


def test_a_failing_world_that_ran_nothing_gets_no_empty_heading() -> None:
    """A constant claim reaches this when the count went down to zero.

    A heading over nothing reads as a report that lost its body.
    """
    measured = QueryGrowth(points=(point(1, 3), point(10, 0)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert "Factor 1 ran 3 and factor 10 ran 0." in report
    assert "At factor 10 the block ran:" not in report


def test_a_curve_that_held_is_rendered_too() -> None:
    """A growth measurement is worth printing when it passes.

    A formatter with words only for failure would leave the CI-report face to
    invent a second vocabulary for the same curve.
    """
    measured = QueryGrowth(points=(point(1, 4, rows=4), point(10, 4, rows=40)))

    report = format_query_growth(measured, Growth.CONSTANT)

    assert report.splitlines()[0] == (
        "The query count stayed inside constant across every scale factor."
    )
    assert "  factor 10   40 rows   4 statements" in report
    assert "At factor" not in report


def test_every_rendering_says_the_counts_are_of_the_block_alone() -> None:
    """The provenance line, on a holding curve as well as a failing one.

    It answers the question a growing count raises -- "am I measuring my code or
    the fixture that built the data?" -- in the place the numbers are, because a
    reader who does not already know the harness owns the capture will not go
    and read a docs page to find out.
    """
    failing = format_query_growth(QueryGrowth(points=(point(1, 3), point(10, 21))), Growth.CONSTANT)
    holding = format_query_growth(QueryGrowth(points=(point(1, 4), point(10, 4))), Growth.CONSTANT)

    for report in (failing, holding):
        assert "each capture was opened inside world(factor)" in report
        assert "so the statements that built it are not in these numbers." in report


def test_a_long_statement_is_cut_where_the_caller_says() -> None:
    """Passed through to the shared report rather than re-implemented here."""
    measured = QueryGrowth(points=(point(1, 3), point(10, 21)))

    report = format_query_growth(measured, Growth.CONSTANT, max_sql=20)

    assert "... (truncated)" in report


def test_the_report_carries_no_trailing_newline() -> None:
    """It is embedded in an ``AssertionError``, which supplies its own framing."""
    measured = QueryGrowth(points=(point(1, 3), point(10, 21)))

    assert not format_query_growth(measured, Growth.CONSTANT).endswith("\n")
