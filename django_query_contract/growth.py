"""What a query count is allowed to do as the data grows."""

from __future__ import annotations

from enum import Enum

from django_query_contract.growth_point import GrowthPoint


class Growth(Enum):
    """The claim a growth assertion makes: an upper bound on how a count may grow.

    A growth assertion runs one block against worlds of several sizes and asks
    whether the number of statements it emitted kept its shape. This names the
    shape, and both members are **upper bounds**, which is the decision worth
    stating: ``LINEAR`` is satisfied by a block that turns out to be constant,
    because a count that grows less than allowed is never the defect. Only
    growing *faster* than the claim is.

    **Every rule here is exact integer arithmetic, and that is the whole design.**
    The alternative -- fitting a curve to the counts and deciding whether the
    slope is near enough to zero -- needs a tolerance, a goodness-of-fit floor
    and a rule for what counts as linear, which is three knobs where this has
    none. A growth assertion that is itself flaky is worse than no growth
    assertion, because it gets deleted and takes the idea with it. See
    ``measure_query_growth`` for the rest of that argument.

    The rules are stated over a *pair* of measurements rather than over the whole
    curve because both are transitive: equality is, and so is a non-increasing
    ratio. Checking consecutive pairs therefore decides the whole curve, and the
    pair that failed is the pair a failure message can point at.
    """

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
        """Whether going from ``smaller`` to ``larger`` stayed inside this bound.

        Args:
            smaller: The measurement at the lower factor.
            larger: The measurement at the higher factor.

        Returns:
            ``True`` when the pair is within the bound.
        """
        if self is Growth.CONSTANT:
            # Integer equality. Nothing to tune, nothing to be wrong about, and
            # a single extra statement at the larger factor is a finding rather
            # than noise under a threshold -- which is the point, because one
            # extra statement per row is what an N+1 looks like at factor 1.
            return larger.count == smaller.count
        # ``count / factor`` must not increase, written as a cross-multiplication
        # so it stays in integers and never rounds. An affine count ``a + b*f``
        # always satisfies it, because the constant term is divided by a larger
        # factor on the left; anything super-linear never does.
        return larger.count * smaller.factor <= smaller.count * larger.factor

    def explain(self, smaller: GrowthPoint, larger: GrowthPoint) -> str:
        """State the rule this pair broke, in the numbers that broke it.

        Kept beside :meth:`permits` rather than in the formatter so the sentence
        and the arithmetic cannot drift into describing different rules -- the
        failure a reader would have no way to detect, because the only evidence
        they have is the sentence.
        """
        # Wrapped by hand rather than by ``textwrap``, because the numbers vary in
        # width and a reflow would put a line break wherever they happened to land
        # -- including through the phrase a reader searches for.
        if self is Growth.CONSTANT:
            return (
                "A constant count runs the same statements whatever the data, so every "
                f"factor\nhas to produce the same number. Factor {smaller.factor} ran "
                f"{smaller.count} and factor {larger.factor} ran {larger.count}."
            )
        # Floor division, which is what the cross-multiplied rule above allows:
        # the largest count at the higher factor whose ratio does not exceed the
        # lower factor's.
        allowed = smaller.count * larger.factor // smaller.factor
        return (
            "A linear count may run at most as many statements per unit of data at "
            f"factor\n{larger.factor} as it did at factor {smaller.factor}. Against "
            f"{smaller.count} statements at factor {smaller.factor},\nthat allows "
            f"{allowed} at factor {larger.factor}; {larger.count} ran."
        )
