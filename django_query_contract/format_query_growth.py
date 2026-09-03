"""Render a growth curve as the paragraph a reader needs under a failed claim."""

from __future__ import annotations

from django_query_contract.format_capture_report import format_capture_report
from django_query_contract.growth import Growth
from django_query_contract.growth_point import GrowthPoint
from django_query_contract.query_growth import QueryGrowth

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
    """Describe ``measured`` as a curve, and say whether it kept ``growth``.

    This is the message ``assert_query_growth`` fails with, written as a plain
    function so the CI-report face can render a curve that nobody asserted on.
    It renders a holding curve too, and deliberately: a growth measurement is
    worth printing when it passes, and a formatter that only had words for
    failure would leave the reporting face to invent its own.

    **A growth failure has to name the counts at each factor**, or a reader
    cannot tell a defect from noise -- "the count grew" is the same sentence for
    a hundredfold N+1 and for one extra statement from a cache that filled on
    the first run. So the curve is a table, and under it the rule that was
    broken, stated in the numbers that broke it.

    Under that is the capture from the higher of the two factors that failed,
    rendered by ``format_capture_report`` -- the same report that appears under
    a failing ``django_assert_num_queries``, which means the N+1 that explains
    the growth is described exactly as it would be anywhere else in this
    package, and the reader gets the call site rather than only the arithmetic.

    **The claim is required and has no default**, which is worth saying because
    the obvious reading of "render this measurement" is that a measurement is
    enough. It is not: one curve reads as a pass against
    :attr:`~django_query_contract.Growth.LINEAR` and a failure against
    :attr:`~django_query_contract.Growth.CONSTANT`, and the headline sentence has
    to say which. Defaulting to either would put a claim nobody made into a
    report, which is the whole failure mode this package is about.

    Args:
        measured: The curve.
        growth: The claim to judge it against. Positional, and required -- see
            above.
        max_findings: How many N+1 findings to list from the failing world.
        max_sql: Where to cut a long statement.

    Returns:
        The report, without a trailing newline.
    """
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
        # Empty when the failing world ran no statements at all, which a
        # constant claim reaches when the count went *down* to zero. A heading
        # over nothing would read as a report that lost its body.
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
    # Zero when no world reported a size, which drops the column rather than
    # printing one full of placeholders. A world is allowed not to count its
    # rows -- see ``measure_query_growth`` -- and a table that spends a column
    # saying so on every line is a table about the harness.
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
