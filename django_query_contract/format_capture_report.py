"""Turn a capture into the paragraph a reader needs under a failed assertion."""

from __future__ import annotations

from django_query_contract.find_n_plus_one import find_n_plus_one
from django_query_contract.format_attributions import format_attributions
from django_query_contract.format_n_plus_one import format_n_plus_one
from django_query_contract.group_by_call_site import group_by_call_site
from django_query_contract.query_capture import QueryCapture


def format_capture_report(
    capture: QueryCapture,
    *,
    max_findings: int = 5,
    max_call_sites: int = 5,
    max_sql: int = 160,
) -> str:
    """Describe what a capture saw, worst N+1 first.

    This is the diagnosis half of the bargain with ``django_assert_num_queries``:
    that fixture builds its message inline and calls ``pytest.fail()``, so there
    is no hook inside it and no reason to want one. The user keeps writing the
    assertion they already write, and a failure gains this underneath it.

    It names an N+1 rather than merely reporting repetition, which is what it
    did before the detector existed. The claim is safe to make because of how
    the finding is defined -- more than one execution of one statement shape
    from one call stack, with no threshold and no rule about lazy loads -- and
    because nothing here fails a test on one. See
    :class:`~django_query_contract.NPlusOne`.

    Args:
        capture: A closed capture.
        max_findings: How many findings to list before summarising the rest.
        max_call_sites: How many lines to name when attributing the statements
            no finding accounted for.
        max_sql: Where to cut a long statement. The record keeps the whole thing.

    Returns:
        The report, without a trailing newline. Empty when there is nothing to
        say -- no statements and no ceiling crossed. There is deliberately no
        early return for that case: an explicit guard here was provably dead,
        because both halves below already produce nothing from nothing.
    """
    lines = _ceiling_lines(capture)
    if capture.records:
        if lines:
            lines.append("")
        lines.extend(
            _finding_lines(
                capture,
                max_findings=max_findings,
                max_call_sites=max_call_sites,
                max_sql=max_sql,
            )
        )
    return "\n".join(lines)


def _ceiling_lines(capture: QueryCapture) -> list[str]:
    """The honest half: say when a count taken from Django's log is wrong."""
    lines: list[str] = []
    for ceiling in capture.exceeded_ceilings:
        lines.append(
            f"Query log ceiling exceeded on '{ceiling.alias}': "
            f"{ceiling.executions} statements executed, but connection.queries_log holds at "
            f"most {ceiling.limit} and already held {ceiling.log_length_at_enter}, so a "
            f"CaptureQueriesContext over this block reports {ceiling.visible}."
        )
        lines.append(
            "  Above that ceiling assertNumQueries and django_assert_num_queries under-report, "
            "and with a full log they report zero for a block that ran queries."
        )
    return lines


def _finding_lines(
    capture: QueryCapture, *, max_findings: int, max_call_sites: int, max_sql: int
) -> list[str]:
    """What ran, which of it was an N+1, where the rest came from, and what was left.

    The counts add up to the number of statements captured, on purpose. A report
    that lists the interesting queries and stays quiet about the rest invites the
    reader to assume the rest were fine, and this package's whole argument is
    against measurements that quietly stop describing everything.

    Attributing the leftovers is what closes the other half of that. Before it,
    a capture named a call site only where a finding rendered one, so the case
    this section exists for -- a count assertion that failed with no N+1 in the
    capture at all -- printed a number of unexplained statements and not one
    line of code. The statements a finding already accounts for are left out
    rather than attributed twice: the finding named their call site three lines
    higher up.
    """
    records = capture.records
    by_alias: dict[str, int] = {}
    for record in records:
        by_alias[record.alias] = by_alias.get(record.alias, 0) + 1
    counted = ", ".join(f"{count} on '{alias}'" for alias, count in by_alias.items())
    lines = [f"{len(records)} statements captured: {counted}."]

    findings = find_n_plus_one(records)
    # A record with no stack is not an absence of an N+1, it is an absence of
    # the evidence, so it is counted separately from the queries that were
    # looked at and found innocent.
    stackless = sum(1 for record in records if not record.stack)
    # By index rather than by re-deriving the detector's key, so this asks only
    # "which statements did the findings already speak for" and does not grow a
    # second copy of what a finding *is*. An index is unique within a capture --
    # it is the position the capture assigned -- and this takes a capture.
    accounted = {record.index for finding in findings for record in finding.records}
    others = [record for record in records if record.stack and record.index not in accounted]

    if findings:
        lines.append("")
        lines.append("N+1 -- one statement shape, executed more than once from one call path:")
        for finding in findings[:max_findings]:
            lines.append(format_n_plus_one(finding, max_sql=max_sql))
        if len(findings) > max_findings:
            lines.append(f"  and {len(findings) - max_findings} more findings.")
    elif others:
        # Worth saying out loud under a failed count assertion: the extra
        # queries are not a loop, so the fix is not a prefetch.
        lines.append("")
        lines.append("No N+1: no statement shape repeated from a single call path.")

    if others:
        lines.append(
            f"  {len(others)} statement(s) were not repeated from any one call path. "
            "They came from:"
        )
        lines.append(
            format_attributions(
                group_by_call_site(others), max_sites=max_call_sites, max_sql=max_sql
            )
        )
    if stackless:
        lines.append(
            f"  {stackless} statement(s) carried no call stack and were not grouped: "
            "a capture rebuilt from a CaptureQueriesContext has none to give."
        )
    return lines
