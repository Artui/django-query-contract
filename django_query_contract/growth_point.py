"""One scale factor, and everything the block did at it."""

from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.query_capture import QueryCapture


@dataclass(frozen=True, slots=True)
class GrowthPoint:
    """A single point on a growth curve: one world, one run of the block.

    The capture is kept whole rather than reduced to its count, and that is what
    makes a growth failure actionable instead of merely true. "Four statements
    at factor 1, one thousand and three at factor 10" says a count grew; the
    capture behind the larger point says *which statement* grew and from which
    line, through the same N+1 detector and the same report every other face of
    this package uses.

    It also carries the ceiling. A growth run is the regime where Django's own
    query log stops being able to count -- a per-row statement over a thousand
    rows at a factor or two more is thousands of statements in one block -- so
    the point where a growth curve gets interesting is the point where
    ``assertNumQueries`` would have started under-reporting, and
    ``capture.exceeded_ceilings`` says so.

    Nothing retains a point beyond the assertion that made it. A capture at a
    high factor is large -- one record per statement, with up to ``stack_depth``
    frames each -- so a growth measurement is a local value in the test that
    asked for it, never stashed anywhere with a longer life.
    """

    factor: int
    """The scale factor this world was built at. The curve's x-axis."""

    rows: int | None
    """How many rows the world reported holding, or ``None`` when it reported none.

    A diagnostic, not the x-axis: the caller passed the factor in and already
    knows it, while the row count is what the database actually took. ``None``
    when the world yielded something that is not a whole number -- a
    hand-written ``@contextmanager`` that simply ``yield``s is a legitimate
    implementation of the seam and gives no number, so the report says how big
    the world was only when it was told.
    """

    capture: QueryCapture
    """Every statement the block executed in this world, closed and readable."""

    @property
    def count(self) -> int:
        """How many statements the block executed here. The curve's y-axis."""
        return len(self.capture)
