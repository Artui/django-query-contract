from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from django.db import transaction

from django_query_contract import QueryCapture, measure_query_growth
from tests.growth_worlds import (
    author_world,
    books_per_author,
    count_authors,
    misreporting_world,
    row_by_row_world,
    sizeless_world,
)
from tests.testapp.models import Author, Customer

pytestmark = pytest.mark.django_db


def test_a_flat_block_measures_the_same_count_at_every_factor() -> None:
    measured = measure_query_growth(author_world, count_authors, factors=(1, 10))

    assert measured.factors == (1, 10)
    assert measured.counts == (1, 1)


def test_a_per_row_block_measures_a_count_that_moves_with_the_data() -> None:
    """The defect, seen. Two authors is three statements; twenty is twenty-one."""
    measured = measure_query_growth(author_world, books_per_author, factors=(1, 10))

    assert measured.counts == (3, 21)


def test_the_size_of_each_world_is_reported_beside_its_count() -> None:
    """A diagnostic rather than the x-axis: the caller already knows the factor."""
    measured = measure_query_growth(author_world, count_authors, factors=(1, 3))

    assert [point.rows for point in measured.points] == [4, 12]


def test_a_world_that_yields_nothing_still_measures() -> None:
    """The five-line ``@contextmanager`` a project will actually write."""
    measured = measure_query_growth(sizeless_world, count_authors, factors=(1, 2))

    assert measured.counts == (1, 1)
    assert [point.rows for point in measured.points] == [None, None]


def test_a_world_that_yields_something_other_than_a_count_reports_no_size() -> None:
    """Tolerated, and reported as unknown rather than printed as a repr."""
    measured = measure_query_growth(misreporting_world, count_authors, factors=(1, 2))

    assert measured.counts == (1, 1)
    assert [point.rows for point in measured.points] == [None, None]


def test_the_worlds_own_statements_are_not_in_the_counts() -> None:
    """The mistake this function exists to make unavailable, both halves of it."""
    measured = measure_query_growth(row_by_row_world, count_authors, factors=(1, 4))

    assert measured.counts == (1, 1)

    from_outside = []
    for factor in (1, 4):
        with QueryCapture(using="default") as capture, row_by_row_world(factor):
            count_authors()
        from_outside.append(len(capture))

    assert from_outside[0] < from_outside[1]


def test_a_warm_up_runs_once_inside_every_world_and_is_not_counted() -> None:
    """The one flake a growth assertion has, and the argument that answers it."""
    seen: list[int] = []

    def warm_up() -> None:
        seen.append(Author.objects.count())

    measured = measure_query_growth(author_world, count_authors, factors=(1, 2, 5), warm_up=warm_up)

    assert seen == [2, 4, 10]
    assert measured.counts == (1, 1, 1)


def test_a_warm_up_that_writes_a_row_is_not_undone_for_the_next_world() -> None:
    """A world torn down by a rollback takes the warm-up's row with it."""

    def first_call_writes() -> None:
        Customer.objects.get_or_create(name="seen")
        list(Author.objects.all())

    measured = measure_query_growth(
        author_world, first_call_writes, warm_up=first_call_writes, factors=(1, 10)
    )

    assert measured.counts == (2, 2)


def test_the_factors_run_in_the_order_they_were_given() -> None:
    asked: list[int] = []

    @contextmanager
    def recording_world(factor: int) -> Iterator[int]:
        asked.append(factor)
        with transaction.atomic():
            yield 0
            transaction.set_rollback(True)

    measure_query_growth(recording_world, count_authors, factors=(1, 2, 5))

    assert asked == [1, 2, 5]


def test_the_capture_honours_the_stack_depth_it_was_given() -> None:
    """The knob that matters most here: the block is captured once per factor."""
    measured = measure_query_growth(author_world, books_per_author, factors=(1, 2), stack_depth=3)

    assert all(len(record.stack) <= 3 for record in measured.points[1].capture)


def test_the_capture_can_be_narrowed_to_one_connection() -> None:
    measured = measure_query_growth(author_world, count_authors, factors=(1, 2), using="default")

    assert [ceiling.alias for ceiling in measured.points[0].capture.ceilings] == ["default"]


def test_one_factor_is_refused_because_it_would_be_a_count_assertion() -> None:
    """The structural guard on the decision that this ships no count assertion."""
    with pytest.raises(ValueError, match="at least two scale factors"):
        measure_query_growth(author_world, count_authors, factors=(1,))


def test_a_descending_factor_list_is_refused_rather_than_sorted() -> None:
    """Sorting would move a statement between measurements without saying so."""
    with pytest.raises(ValueError, match="strictly ascending"):
        measure_query_growth(author_world, count_authors, factors=(10, 1))


def test_a_repeated_factor_is_refused() -> None:
    """Two measurements of the same world compare a world with itself."""
    with pytest.raises(ValueError, match="strictly ascending"):
        measure_query_growth(author_world, count_authors, factors=(2, 2))


def test_a_factor_below_one_is_refused() -> None:
    """A factor multiplies a declaration, so there is no world below the declaration."""
    with pytest.raises(ValueError, match="strictly ascending"):
        measure_query_growth(author_world, count_authors, factors=(0, 1))
