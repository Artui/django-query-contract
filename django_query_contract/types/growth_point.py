from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.capture.query_capture import QueryCapture


@dataclass(frozen=True, slots=True)
class GrowthPoint:
    """A single point on a growth curve: one world, one run of the block."""

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
