"""The assertion itself: a query count that keeps its shape as the data grows."""

from __future__ import annotations

import inspect

import pytest

from django_query_contract import Growth, assert_query_growth, measure_query_growth
from tests.growth_worlds import (
    author_world,
    books_for_every_pair,
    books_per_author,
    count_authors,
)
from tests.testapp.models import Author

pytestmark = pytest.mark.django_db


def test_a_flat_block_passes_and_hands_back_what_it_measured() -> None:
    """The same courtesy ``django_assert_num_queries`` does by yielding its context."""
    measured = assert_query_growth(author_world, count_authors, factors=(1, 10))

    assert measured.counts == (1, 1)


def test_the_default_claim_is_constant() -> None:
    """``O(1)`` is what almost every block should be, so it costs no import."""
    signature = inspect.signature(assert_query_growth)

    assert signature.parameters["growth"].default is Growth.CONSTANT


def test_an_n_plus_one_fails_the_constant_claim() -> None:
    with pytest.raises(AssertionError) as raised:
        assert_query_growth(author_world, books_per_author, factors=(1, 10))

    assert "The query count is not constant across the scale factors." in str(raised.value)


def test_the_failure_names_the_count_at_every_factor() -> None:
    """Without both numbers a reader cannot tell ``O(N)`` from noise.

    "The count grew" is the same sentence for a hundredfold N+1 and for one
    extra statement from a cache that filled on the first run.
    """
    with pytest.raises(AssertionError) as raised:
        assert_query_growth(author_world, books_per_author, factors=(1, 10))

    message = str(raised.value)
    assert "factor  1    4 rows    3 statements" in message
    assert "factor 10   40 rows   21 statements" in message
    assert "Factor 1 ran 3 and factor 10 ran 21." in message


def test_the_failure_names_the_statement_that_grew_and_where_it_came_from() -> None:
    """The arithmetic says a count grew; this says which line to go and edit."""
    with pytest.raises(AssertionError) as raised:
        assert_query_growth(author_world, books_per_author, factors=(1, 10))

    message = str(raised.value)
    assert "At factor 10 the block ran:" in message
    assert "N+1 -- one statement shape, executed more than once from one call path:" in message
    assert "20 x  from " in message
    assert "growth_worlds.py" in message


def test_bulk_work_says_so_with_a_linear_claim() -> None:
    """``O(N)`` has to be expressible, or a suite with real batch work asserts nothing."""
    measured = assert_query_growth(
        author_world, books_per_author, growth=Growth.LINEAR, factors=(1, 10)
    )

    assert measured.counts == (3, 21)


def test_a_linear_claim_still_refuses_growth_faster_than_the_data() -> None:
    """The reason ``LINEAR`` is not a way of turning the assertion off."""
    with pytest.raises(AssertionError) as raised:
        assert_query_growth(
            author_world, books_for_every_pair, growth=Growth.LINEAR, factors=(1, 4)
        )

    assert "The query count grows faster than the data." in str(raised.value)


def test_the_failure_says_the_counts_are_of_the_block_alone() -> None:
    """Documented where the user is looking, not only on a docs page.

    The one mistake the harness exists to prevent is measuring the world's
    loader instead of the block, and a reader looking at a growing count has no
    way to tell these numbers from the ones that mistake produces unless the
    numbers say what they are.
    """
    with pytest.raises(AssertionError) as raised:
        assert_query_growth(author_world, books_per_author, factors=(1, 10))

    assert "each capture was opened inside world(factor)" in str(raised.value)


def test_it_raises_a_plain_assertion_error() -> None:
    """pytest is not a dependency of this package, and three of four faces are not pytest."""
    with pytest.raises(AssertionError) as raised:
        assert_query_growth(author_world, books_per_author, factors=(1, 10))

    assert type(raised.value) is AssertionError


def test_there_is_no_way_to_assert_a_fixed_count_here() -> None:
    """The decision that this package ships no second count assertion, as a guard.

    ``django_assert_num_queries`` is the count assertion. A parameter naming a
    number of queries would make this one too, so the signature is checked
    rather than trusted -- and the same rule is what makes fewer than two
    factors an error.
    """
    signature = inspect.signature(assert_query_growth)

    assert not {"num", "count", "queries", "num_queries"} & set(signature.parameters)
    with pytest.raises(ValueError, match="at least two scale factors"):
        assert_query_growth(author_world, count_authors, factors=(5,))


def test_a_warm_up_reaches_the_measurement_underneath() -> None:
    """The flake fix has to be reachable from the assertion, not only the measurement."""
    seen: list[int] = []

    assert_query_growth(
        author_world,
        count_authors,
        factors=(1, 2),
        warm_up=lambda: seen.append(Author.objects.count()),
    )

    assert seen == [2]


def test_the_assertion_and_the_measurement_default_to_the_same_factors() -> None:
    """Two defaults for one thing is how they come to disagree, silently.

    Both would be valid factor lists, so nothing would fail -- the assertion
    would simply be measuring a curve the docs describe differently.
    """
    asserted = inspect.signature(assert_query_growth).parameters["factors"].default
    measured = inspect.signature(measure_query_growth).parameters["factors"].default

    assert asserted is measured
    assert asserted == (1, 10)
