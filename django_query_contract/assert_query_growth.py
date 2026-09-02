"""The growth assertion: a query count keeps its shape as the data grows."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from django_query_contract.format_query_growth import format_query_growth
from django_query_contract.growth import Growth
from django_query_contract.measure_query_growth import measure_query_growth
from django_query_contract.query_growth import QueryGrowth
from django_query_contract.utils import DEFAULT_FACTORS, DEFAULT_STACK_DEPTH, ScaleWorld


def assert_query_growth(
    world: ScaleWorld,
    block: Callable[[], object],
    *,
    growth: Growth = Growth.CONSTANT,
    factors: Sequence[int] = DEFAULT_FACTORS,
    using: str | Iterable[str] | None = None,
    stack_depth: int = DEFAULT_STACK_DEPTH,
    warm_up: Callable[[], object] | None = None,
) -> QueryGrowth:
    """Assert that ``block``'s query count keeps ``growth`` as the world gets bigger.

    ```python
    from django_query_contract import assert_query_growth

    def test_the_listing_does_not_grow(world):
        assert_query_growth(world, lambda: render_author_list())
    ```

    ``world`` is asked for a hundred rows and then a thousand, the block runs in
    each, and the two statement counts have to be equal. If they are not, the
    failure names both counts, the rule they broke and the statement that grew,
    with the line it came from.

    **This is not a count assertion, and it must not become one.**
    ``django_assert_num_queries`` is the count assertion: it is typed, it
    handles ``connection=`` and ``using=`` and a custom note, and it yields the
    captured queries. This package ships no second one and there is deliberately
    no way to spell a fixed count here -- the claim is about how a count
    *changes*, which is why fewer than two factors is refused rather than
    treated as a count of one world. The two compose: assert the count with
    theirs and the shape of it with this, and a failure of either is diagnosed
    by the same capture.

    **What is new here is the growth claim itself.** Ruby has had it since
    ``n_plus_one_control`` -- run the code at several scale factors, assert the
    count is ``O(1)`` -- and no Python package does. It catches what a fixed
    count cannot: a listing asserted at three queries against three fixture rows
    is asserted at three queries against a defect that costs one query per row,
    because at three rows the loop and the prefetch look the same. A growth
    assertion asks the only question that separates them.

    **The capture is opened inside the world, never around it**, which is what
    makes this a function rather than a recipe. See ``measure_query_growth`` for
    the measured reason -- a world's own loader emits statements that grow with
    the factor, so a capture wrapped around the build reports the loader's curve
    as the block's.

    Args:
        world: How to make the world be a given size. ``world(factor)`` returns
            a context manager. Anything of that shape does:
            ``django_data_shape.fixtures.scale_fixture`` yields one, and a
            five-line ``@contextmanager`` in a project's own ``conftest`` is
            another.
        block: What to measure. Called once per factor, with no arguments.
        growth: The bound to hold the count to. ``Growth.CONSTANT`` by default,
            because a count that does not move with the data is what almost
            every block should do and the only interesting question about the
            rest is whether they are bulk work; ``Growth.LINEAR`` is how bulk
            work says so.
        factors: The sizes to measure, strictly ascending, at least two.
        using: Which connections to capture. Every configured one by default.
        stack_depth: Frames kept per statement.
        warm_up: Run once inside the first world before the first measurement
            and not captured, for a block whose first run fills a per-process
            cache. ``warm_up=block`` is the usual form.

    Returns:
        The measurement, so a passing test can go on to read the curve or the
        captures behind it -- the same courtesy ``django_assert_num_queries``
        does by yielding its ``CaptureQueriesContext``.

    Raises:
        AssertionError: If the curve broke ``growth``. A plain ``AssertionError``
            rather than ``pytest.fail``, because pytest is not a dependency of
            this package -- three of the four faces of this capture are not
            pytest -- and a test runner renders one exactly as well.
        ValueError: If ``factors`` is not at least two strictly ascending whole
            numbers of at least one.
    """
    measured = measure_query_growth(
        world,
        block,
        factors=factors,
        using=using,
        stack_depth=stack_depth,
        warm_up=warm_up,
    )
    if not measured.holds(growth):
        raise AssertionError(format_query_growth(measured, growth))
    return measured
