from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from django_query_contract.analysis.measure_query_growth import measure_query_growth
from django_query_contract.reporting.format_query_growth import format_query_growth
from django_query_contract.types.growth import Growth
from django_query_contract.types.query_growth import QueryGrowth
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
    """Assert that ``block``'s query count keeps ``growth`` as the world gets bigger."""
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
