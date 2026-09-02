"""Turn captured plans into the paragraph a reader needs, and no verdict."""

from __future__ import annotations

from django_query_contract.find_plan_defects import find_plan_defects
from django_query_contract.plan_capture import PlanCapture
from django_query_contract.plan_defect import PlanDefect
from django_query_contract.plan_finding import PlanFinding
from django_query_contract.plan_node import PlanNode
from django_query_contract.query_plan import QueryPlan
from django_query_contract.query_record import QueryRecord
from django_query_contract.utils import relative_to_cwd, shorten


def format_query_plans(
    capture: PlanCapture,
    *,
    max_findings: int = 5,
    max_estimates: int = 5,
    max_sql: int = 160,
) -> str:
    """Describe what the planner did, what it got wrong, and what was not asked.

    Four blocks, and the order is the argument. The findings come first because
    they are the only claims here that hold by construction. The estimate errors
    come after them and are explicitly *not* claims: they are two numbers
    PostgreSQL printed and the factor between them, ordered so the largest is
    visible, with no rule anywhere deciding which of them is a defect. The
    statements that carried no plan are counted last, so a reader can see that
    the numbers above do not cover everything.

    The block about relations with no statistics comes before all of it, because
    it can invalidate all of it: a plan over a table PostgreSQL has never
    analyzed is a guess, and a reader who does not know that will act on it.

    Args:
        capture: A closed :class:`~django_query_contract.PlanCapture`.
        max_findings: How many findings to list before summarising the rest.
        max_estimates: How many statements to name in the estimate-error block.
        max_sql: Where to cut a long statement. The record keeps the whole thing.

    Returns:
        The report, without a trailing newline. Empty when no statement carried a
        plan -- which is every capture that is not a ``PlanCapture``, and a
        ``PlanCapture`` around a block that ran nothing.
    """
    planned = [(record, record.plan) for record in capture.records if record.plan is not None]
    if not planned:
        return ""

    explained = [(record, plan) for record, plan in planned if plan.root is not None]
    refusals = [plan.refusal for _, plan in planned if plan.refusal is not None]

    lines = [
        f"{len(planned)} statements captured, {len(explained)} of them explained"
        f"{'' if capture.analyze else ' without ANALYZE, so nothing here was measured'}."
    ]
    lines.extend(_statistics_lines(capture))
    lines.extend(_finding_lines(capture, max_findings=max_findings, max_sql=max_sql))
    lines.extend(_estimate_lines(explained, max_estimates=max_estimates, max_sql=max_sql))
    lines.extend(_refusal_lines(refusals))
    return "\n".join(lines)


def _statistics_lines(capture: PlanCapture) -> list[str]:
    """Say when the planner was reasoning about tables it knows nothing about."""
    relations = capture.unanalyzed_relations
    if not relations:
        return []
    return [
        f"  PostgreSQL has never gathered statistics for {', '.join(relations)}.",
        "  Every plan below is a guess: the planner is working from a default selectivity "
        "rather than from these tables. Load the rows, then ANALYZE.",
    ]


def _finding_lines(capture: PlanCapture, *, max_findings: int, max_sql: int) -> list[str]:
    """The claims that hold by construction, worst kind first."""
    findings = find_plan_defects(capture.records)
    if not findings:
        return []
    lines = ["", "Plan findings -- what PostgreSQL's own output states:"]
    for finding in findings[:max_findings]:
        lines.append(_finding(finding, max_sql=max_sql))
    if len(findings) > max_findings:
        lines.append(f"  and {len(findings) - max_findings} more findings.")
    return lines


def _finding(finding: PlanFinding, *, max_sql: int) -> str:
    """One finding as an indented block, headline first."""
    if finding.defect is PlanDefect.PLANNER_BLIND:
        actuals = ", ".join(_rows(value) for value in finding.actual_rows)
        headline = (
            f"  planner blind  {finding.count} executions, one estimate of "
            f"{_rows(finding.estimated_rows)} rows, actuals {actuals}"
        )
    else:
        node = finding.nodes[0]
        headline = f"  spilled to disk  {node.node_type}{_spill_detail(node)}"
    named = ", ".join(f"#{record.index}" for record in finding.records)
    return "\n".join(
        [
            headline,
            f"       {shorten(finding.fingerprint, max_sql)}",
            f"       from {_sites(finding)}",
            f"       queries {named}",
        ]
    )


def _spill_detail(node: PlanNode) -> str:
    """What the node said about how it spilled, in whichever vocabulary it used."""
    parts = [
        part
        for part in (
            node.sort_method,
            None if node.sort_space_used_kb is None else f"{_rows(node.sort_space_used_kb)} kB",
            None if node.hash_batches is None else f"{node.hash_batches} batches",
            None if node.disk_usage_kb is None else f"{_rows(node.disk_usage_kb)} kB on disk",
        )
        if part is not None
    ]
    return f", {', '.join(parts)}" if parts else ""


def _estimate_lines(
    explained: list[tuple[QueryRecord, QueryPlan]], *, max_estimates: int, max_sql: int
) -> list[str]:
    """The planner's biggest misses, reported and left alone.

    Deliberately not a finding and deliberately not sorted into one. Every
    analyzed plan has a node the planner was most wrong about, and printing it is
    a fact; deciding that being wrong by fifty times is a defect and by forty is
    not would be the threshold this package refuses. The caveat is printed with
    the block rather than left to the documentation, because the commonest large
    ratio has no defect under it at all: a node under a ``LIMIT`` stops early by
    design, so its actual is meant to fall short of its estimate.
    """
    scored: list[tuple[float, QueryRecord, PlanNode]] = []
    for record, plan in explained:
        worst = plan.worst_estimate
        # ``None`` exactly when no node carried an actual row count, which is
        # every plan taken without ANALYZE.
        if worst is None:
            continue
        error, node = worst
        scored.append((error, record, node))
    if not scored:
        return []
    scored.sort(key=lambda entry: (-entry[0], entry[1].index))

    lines = [
        "",
        "Where the planner was furthest out (reported, not judged -- a node under a "
        "LIMIT is meant to fall short):",
    ]
    for error, record, node in scored[:max_estimates]:
        lines.append(
            f"  {error:,.1f}x  #{record.index}  {node.node_type}"
            f"{'' if node.relation is None else ' on ' + node.relation}: expected "
            f"{_rows(node.estimated_rows)} rows, {_rows(node.actual_rows)} arrived"
        )
        lines.append(f"       {shorten(record.fingerprint, max_sql)}")
    if len(scored) > max_estimates:
        lines.append(f"  and {len(scored) - max_estimates} more statements.")
    return lines


def _refusal_lines(refusals: list[str]) -> list[str]:
    """Count what was not explained, by the reason it was not.

    Counted rather than listed per statement: the reasons are a closed set of
    two, and a reader needs to know how much of the block the blocks above do not
    describe, not which line each skipped statement was on.
    """
    if not refusals:
        return []
    tallied: dict[str, int] = {}
    for refusal in refusals:
        tallied[refusal] = tallied.get(refusal, 0) + 1
    lines = ["", f"{len(refusals)} statement(s) carried no plan:"]
    lines.extend(f"  {count} x  {reason}" for reason, count in tallied.items())
    return lines


def _sites(finding: PlanFinding) -> str:
    """Every line this finding's executions came from, shortened and deduplicated."""
    return ", ".join(
        "no frame outside Django (the capture's stack depth did not reach one)"
        if site is None
        else relative_to_cwd(str(site))
        for site in finding.call_sites
    )


def _rows(value: float | None) -> str:
    """A row count as a reader wants it, or the fact that it was never measured."""
    return "not measured" if value is None else f"{value:,.0f}"
