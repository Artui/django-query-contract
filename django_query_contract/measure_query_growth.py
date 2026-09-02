"""Run one block against several sizes of world and record what it cost."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from itertools import pairwise

from django_query_contract.growth_point import GrowthPoint
from django_query_contract.query_capture import QueryCapture
from django_query_contract.query_growth import QueryGrowth
from django_query_contract.utils import DEFAULT_FACTORS, DEFAULT_STACK_DEPTH, ScaleWorld


def measure_query_growth(
    world: ScaleWorld,
    block: Callable[[], object],
    *,
    factors: Sequence[int] = DEFAULT_FACTORS,
    using: str | Iterable[str] | None = None,
    stack_depth: int = DEFAULT_STACK_DEPTH,
    warm_up: Callable[[], object] | None = None,
) -> QueryGrowth:
    """Run ``block`` once in each sized world and return the curve.

    The measurement half of the growth assertion, and the half with no claim in
    it: this says what happened, ``assert_query_growth`` says whether that was
    allowed, and the two are separate so a CI report can plot a curve without
    asserting anything.

    ```python
    from django_query_contract import measure_query_growth

    measured = measure_query_growth(world, lambda: render_author_list())
    print(measured.factors, measured.counts)
    ```

    **The capture is opened inside the world, and that is the point of this
    function existing rather than a recipe.** Building a world runs statements
    of its own -- on any backend without ``COPY``, which is most of them, one
    insert per batch of rows -- so a capture wrapped around ``world(factor)``
    counts the loader's statements along with the block's, and *those* grow with
    the factor. Measured against ``django-data-shape`` and reported by its own
    author: a two-table world captured from outside runs 8 statements at factor
    1 and 17 at factor 10 on SQLite, flat at 9 on PostgreSQL where ``COPY`` does
    not pass through Django's cursor wrapper at all. A harness reading that
    curve reports a confident ``O(N)`` for a block that is ``O(1)`` -- the
    harness measuring its own loader and calling it the subject.

    So the harness owns the capture. A caller hands over a world and a block and
    never writes ``QueryCapture`` at all, which is what makes the mistake
    unavailable rather than merely discouraged. There is deliberately no
    parameter for passing a capture in.

    **Why two points and an exact comparison, rather than a fitted curve.** A
    fit would use every measurement and give a slope and a goodness of fit, and
    then need three thresholds to turn those into a verdict: how near zero is
    flat, how linear is linear, how good a fit has to be before the answer is
    believed. Each is a knob, each is wrong for somebody, and a growth assertion
    that fails once a fortnight for reasons nobody can reproduce is deleted --
    taking with it the one assertion in this package that no other Python
    package makes. Comparing counts instead is integer arithmetic on integers
    that were counted rather than estimated: it is exact, it cannot be flaky
    about anything except the block itself, and every part of a failure can be
    printed. It is cruder, and crude is the correct trade here.

    **What the factors mean.** Factor 1 is the world the declaration describes,
    so the declaration should be the smallest world that still means something.
    A hundred rows against a thousand is the regime this is for; the
    two-million-row database that makes a query *plan* realistic is a different
    assertion with a different cost, and it does not vary a factor at all.

    **The one way this can still be flaky, and its fix.** A block whose first
    run populates a per-process cache -- a content-type lookup, a memoised
    settings read -- emits one statement more at the factor that ran first, and
    a suite where an earlier test happened to fill that cache passes while a
    suite that runs this test alone fails. That is the ``warm_up`` argument, and
    the usual value for it is ``block`` itself.

    Args:
        world: How to make the world be a given size:
            ``world(factor)`` returns a context manager, entered around the
            block and exited to undo it. Anything of that shape does, which is
            deliberate -- ``django_data_shape.fixtures.scale_fixture`` yields one
            and a five-line ``@contextmanager`` in a project's own ``conftest``
            is another, so this works on a backend that package refuses and in a
            project that has never heard of it. What it yields is read as the
            number of rows the world holds and reported as a diagnostic; a world
            that yields nothing is fine and reports no size.
        block: What to measure. Called once per factor, with no arguments, and
            its return value is ignored.
        factors: The sizes to measure, strictly ascending, at least two.
        using: Which connections to capture, as ``QueryCapture`` takes it.
            Every configured one by default, because a block that queries a
            second database grows on that one too.
        stack_depth: Frames kept per statement. The knob that matters most here:
            a growth run captures the block once per factor, so the largest
            world sets the cost and a block that is genuinely ``O(N)`` may
            capture thousands of statements.
        warm_up: Run once inside the first world, before the first measurement,
            and not captured. For a block whose first run fills a per-process
            cache. ``warm_up=block`` is the usual form.

    Returns:
        The curve, one :class:`~django_query_contract.GrowthPoint` per factor.

    Raises:
        ValueError: If ``factors`` is not at least two strictly ascending whole
            numbers of at least one.
    """
    checked = _checked_factors(factors)
    points: list[GrowthPoint] = []
    # Consumed by the first world rather than tested against a loop index, so
    # the branch is "is there still a warm-up owed" and not "which iteration is
    # this" -- one condition, and it stays right if the loop ever changes shape.
    owed_warm_up = warm_up
    for factor in checked:
        with world(factor) as rows:
            if owed_warm_up is not None:
                owed_warm_up()
                owed_warm_up = None
            capture = QueryCapture(using=using, stack_depth=stack_depth)
            with capture:
                block()
        points.append(GrowthPoint(factor=factor, rows=_row_count(rows), capture=capture))
    return QueryGrowth(points=tuple(points))


def _checked_factors(factors: Sequence[int]) -> tuple[int, ...]:
    """Refuse a factor list that cannot carry a growth claim, saying which rule it broke."""
    checked = tuple(factors)
    if len(checked) < 2:
        raise ValueError(
            f"A growth assertion needs at least two scale factors, because the claim is "
            f"about how a count changes between worlds of different sizes; got {checked}. "
            "One factor would be a count assertion, and django_assert_num_queries is the "
            "count assertion -- this package ships no second one."
        )
    if any(factor < 1 for factor in checked) or any(
        later <= earlier for earlier, later in pairwise(checked)
    ):
        raise ValueError(
            f"Scale factors must be strictly ascending whole numbers of at least 1; got "
            f"{checked}. They are refused rather than sorted because the order given is "
            "the order that runs, and the first run is the one that pays for whatever a "
            "per-process cache populates -- so reordering them silently would move a "
            "statement from one measurement to another."
        )
    return checked


def _row_count(rows: object) -> int | None:
    """How big the world said it was, or ``None`` when it did not say.

    The seam's context manager yields the number of rows the world holds, and a
    hand-written implementation of it -- the five-line ``@contextmanager`` this
    is meant to accept -- has no reason to have counted them and will simply
    ``yield``. Tolerating that is what keeps the seam open to an implementation
    that has not installed anything: the number is a diagnostic printed in a
    report, and a report that says nothing about the size is better than one
    that says ``None rows`` or a harness that refuses to measure over it.
    """
    return rows if isinstance(rows, int) else None
