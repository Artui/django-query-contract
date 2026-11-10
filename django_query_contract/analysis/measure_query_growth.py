from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from itertools import pairwise

from django_query_contract.capture.query_capture import QueryCapture
from django_query_contract.types.growth_point import GrowthPoint
from django_query_contract.types.query_growth import QueryGrowth
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
    """Run ``block`` once in each sized world and return the curve."""
    checked = _checked_factors(factors)
    points: list[GrowthPoint] = []
    for factor in checked:
        with world(factor) as rows:
            if warm_up is not None:
                warm_up()
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
    """How big the world said it was, or ``None`` when it did not say."""
    return rows if isinstance(rows, int) else None
