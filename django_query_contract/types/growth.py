from __future__ import annotations

from enum import Enum

from django_query_contract.types.growth_point import GrowthPoint


class Growth(Enum):
    """The claim a growth assertion makes: an upper bound on how a count may grow."""

    CONSTANT = "constant"
    """``O(1)``: the same statements whatever the data. The common case, and exact."""

    LINEAR = "linear"
    """``O(N)``: at most proportionally more statements for proportionally more data.

    Legitimate for genuine bulk work -- a ``bulk_create`` batched by row count,
    an ``.iterator()`` walking pages -- and it has to be expressible, or a suite
    with real batch work has no way to assert anything about it and asserts
    nothing at all.
    """

    @property
    def headline(self) -> str:
        """The first line of a failure: what the counts did, in one sentence."""
        if self is Growth.CONSTANT:
            return "The query count is not constant across the scale factors."
        return "The query count grows faster than the data."

    def permits(self, smaller: GrowthPoint, larger: GrowthPoint) -> bool:
        """Whether going from ``smaller`` to ``larger`` stayed inside this bound."""
        if self is Growth.CONSTANT:
            return larger.count == smaller.count
        return larger.count * smaller.factor <= smaller.count * larger.factor

    def explain(self, smaller: GrowthPoint, larger: GrowthPoint) -> str:
        """State the rule this pair broke, in the numbers that broke it."""
        if self is Growth.CONSTANT:
            return (
                "A constant count runs the same statements whatever the data, so every "
                f"factor\nhas to produce the same number. Factor {smaller.factor} ran "
                f"{smaller.count} and factor {larger.factor} ran {larger.count}."
            )
        allowed = smaller.count * larger.factor // smaller.factor
        return (
            "A linear count may run at most as many statements per unit of data at "
            f"factor\n{larger.factor} as it did at factor {smaller.factor}. Against "
            f"{smaller.count} statements at factor {smaller.factor},\nthat allows "
            f"{allowed} at factor {larger.factor}; {larger.count} ran."
        )
