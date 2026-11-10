from __future__ import annotations

from django_query_contract.reporting.format_capture_report import format_capture_report
from django_query_contract.types.growth import Growth
from django_query_contract.types.growth_point import GrowthPoint
from django_query_contract.types.query_growth import QueryGrowth

# Printed under every rendering, holding or failing, and it is not decoration.
# The one mistake this whole harness exists to make unavailable is measuring the
# world's loader instead of the block -- a capture opened around ``world(factor)``
# counts inserts that grow with the factor and reports a confident O(N) for an
# O(1) block. The API makes that unwritable, which leaves one gap: a reader who
# does not know the API did that has no way to tell these counts apart from the
# ones the mistake produces, and will not go and read a docs page to find out.
# So the numbers say what they are, in the place the numbers are.
_PROVENANCE = (
    "Every count above is of the block alone: each capture was opened inside "
    "world(factor),\nafter that world had been built, so the statements that built it are "
    "not in these numbers."
)


def format_query_growth(
    measured: QueryGrowth,
    growth: Growth,
    *,
    max_findings: int = 3,
    max_sql: int = 160,
) -> str:
    """Describe ``measured`` as a curve, and say whether it kept ``growth``."""
    violation = measured.first_violation(growth)
    if violation is None:
        lines = [f"The query count stayed inside {growth.value} across every scale factor."]
    else:
        lines = [growth.headline]
    lines.append("")
    lines.extend(_curve_lines(measured))

    if violation is not None:
        smaller, larger = violation
        lines.append("")
        lines.append(growth.explain(smaller, larger))
        report = format_capture_report(larger.capture, max_findings=max_findings, max_sql=max_sql)
        if report:
            lines.append("")
            lines.append(f"At factor {larger.factor} the block ran:")
            lines.append(report)

    lines.append("")
    lines.append(_PROVENANCE)
    return "\n".join(lines)


def _curve_lines(measured: QueryGrowth) -> list[str]:
    """The table: one row per factor, columns aligned on their widest entry."""
    points = measured.points
    factor_width = max(len(str(point.factor)) for point in points)
    count_width = max(len(str(point.count)) for point in points)
    rows_width = max(
        (len(str(point.rows)) for point in points if point.rows is not None), default=0
    )
    return [
        f"  factor {str(point.factor).rjust(factor_width)}"
        f"{_rows_column(point, rows_width)}"
        f"   {str(point.count).rjust(count_width)} statements"
        for point in points
    ]


def _rows_column(point: GrowthPoint, width: int) -> str:
    """How big this world was, when any world in the curve said."""
    if not width:
        return ""
    size = "-" if point.rows is None else str(point.rows)
    return f"   {size.rjust(width)} rows"
