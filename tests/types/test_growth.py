"""The two growth claims, and the exact arithmetic behind each.

Every rule here is integer arithmetic on counted integers, which is the whole
reason a growth assertion in this package is not flaky. So the tests are about
boundaries: the pair that just holds, and the pair one statement past it.
"""

from __future__ import annotations

import pytest

from django_query_contract import Growth
from tests.growth_worlds import point

pytestmark = pytest.mark.django_db


def test_constant_permits_an_unchanged_count() -> None:
    assert Growth.CONSTANT.permits(point(1, 4), point(10, 4))


def test_constant_refuses_a_single_extra_statement() -> None:
    """One statement, not a percentage, and that is deliberate.

    One extra statement at ten times the data is what an N+1 over one row looks
    like, and a threshold generous enough to absorb it is a threshold that
    misses the defect at small factors.
    """
    assert not Growth.CONSTANT.permits(point(1, 4), point(10, 5))


def test_constant_refuses_a_count_that_fell() -> None:
    """A count that goes *down* with the data is not constant either.

    It is the signature of a per-process cache that the first run filled, which
    is a real thing to be told about rather than a happy accident to absorb.
    """
    assert not Growth.CONSTANT.permits(point(1, 5), point(10, 4))


def test_linear_permits_exactly_proportional_growth() -> None:
    assert Growth.LINEAR.permits(point(1, 3), point(10, 30))


def test_linear_permits_an_affine_count() -> None:
    """``a + b*N``: a fixed preamble plus per-row work is the ordinary bulk shape.

    Three statements at factor 1 and twenty-one at factor 10 is one listing
    query plus one per author, which is what a real batched write looks like.
    The rule has to accept it, or ``LINEAR`` describes nothing anybody writes.
    """
    assert Growth.LINEAR.permits(point(1, 3), point(10, 21))


def test_linear_permits_a_constant_count() -> None:
    """An upper bound, not a band. Growing less than allowed is never the defect."""
    assert Growth.LINEAR.permits(point(1, 4), point(10, 4))


def test_linear_holds_at_the_boundary_and_fails_one_past_it() -> None:
    """Where the cross-multiplied rule actually cuts, checked on both sides."""
    assert Growth.LINEAR.permits(point(2, 3), point(6, 9))
    assert not Growth.LINEAR.permits(point(2, 3), point(6, 10))


def test_linear_refuses_quadratic_growth() -> None:
    assert not Growth.LINEAR.permits(point(1, 5), point(4, 65))


def test_each_claim_has_its_own_headline() -> None:
    """A reader is told which claim broke before they are told any numbers."""
    assert Growth.CONSTANT.headline == "The query count is not constant across the scale factors."
    assert Growth.LINEAR.headline == "The query count grows faster than the data."


def test_the_constant_explanation_carries_both_counts() -> None:
    explained = Growth.CONSTANT.explain(point(1, 4), point(10, 1003))

    assert "Factor 1 ran 4 and factor 10 ran 1003." in explained


def test_the_linear_explanation_names_the_count_that_would_have_held() -> None:
    """Naming a bound is actionable where "too many" is not.

    The bound is the same floor division the rule permits, so the number printed
    is the number the arithmetic used rather than a second calculation that
    could disagree with it.
    """
    explained = Growth.LINEAR.explain(point(1, 5), point(10, 401))

    assert "that allows 50 at factor 10; 401 ran." in explained


def test_the_claims_are_named_by_the_words_a_failure_prints() -> None:
    assert Growth.CONSTANT.value == "constant"
    assert Growth.LINEAR.value == "linear"
