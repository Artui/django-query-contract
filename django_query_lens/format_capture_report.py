"""Turn a capture into the paragraph a reader needs under a failed assertion."""

from __future__ import annotations

import os

from django_query_lens.query_capture import QueryCapture
from django_query_lens.query_record import QueryRecord


def format_capture_report(
    capture: QueryCapture,
    *,
    max_shapes: int = 5,
    max_sql: int = 160,
) -> str:
    """Describe what a capture saw, ordered by what repeated most.

    This is the diagnosis half of the bargain with ``django_assert_num_queries``:
    that fixture builds its message inline and calls ``pytest.fail()``, so there
    is no hook inside it and no reason to want one. The user keeps writing the
    assertion they already write, and a failure gains this underneath it.

    It reports repetition and does not name it. Deciding that a repeated
    statement *is* an N+1 needs the call stack as well as the fingerprint, and
    that judgement is a later milestone -- shipping it as a hint here would be
    the heuristic four dead detectors died of.

    Args:
        capture: A closed capture.
        max_shapes: How many repeated shapes to list before summarising the rest.
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
        lines.extend(_shape_lines(capture, max_shapes=max_shapes, max_sql=max_sql))
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


def _shape_lines(capture: QueryCapture, *, max_shapes: int, max_sql: int) -> list[str]:
    """The repetition half: which shapes ran more than once, and from where."""
    by_alias: dict[str, int] = {}
    for record in capture.records:
        by_alias[record.alias] = by_alias.get(record.alias, 0) + 1
    counted = ", ".join(f"{count} on '{alias}'" for alias, count in by_alias.items())
    lines = [f"{len(capture.records)} statements captured: {counted}."]

    groups = sorted(
        capture.by_fingerprint().items(),
        # Descending by repeat count, then by first appearance so the order is
        # total and the report does not reshuffle between two identical runs.
        key=lambda item: (-len(item[1]), item[1][0].index),
    )
    repeated = [group for group in groups if len(group[1]) > 1]
    once = len(groups) - len(repeated)

    if repeated:
        lines.append("")
        lines.append("Repeated statement shapes:")
        for fingerprint, records in repeated[:max_shapes]:
            lines.extend(_group_lines(fingerprint, records, max_sql=max_sql))
        if len(repeated) > max_shapes:
            lines.append(f"  and {len(repeated) - max_shapes} more repeated shapes.")
    if once:
        lines.append(f"  {once} shape(s) ran once.")
    return lines


def _group_lines(fingerprint: str, records: tuple[QueryRecord, ...], *, max_sql: int) -> list[str]:
    """One repeated shape: how often, where from, and which queries."""
    indices = ", ".join(f"#{record.index}" for record in records[:8])
    if len(records) > 8:
        indices += ", ..."
    lines = [f"  {len(records)} x  {indices}", f"       {_shorten(fingerprint, max_sql)}"]
    # One call site per distinct site rather than one per query: a genuine N+1
    # has one, and a shape reached from several places is worth seeing as such.
    sites = {str(record.call_site) for record in records if record.call_site is not None}
    if sites:
        for site in sorted(sites):
            lines.append(f"       from {_relative(site)}")
    else:
        lines.append("       from no frame outside Django (stack empty or truncated)")
    return lines


def _shorten(text: str, limit: int) -> str:
    """Cut a statement to ``limit`` characters, saying that it was cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + " ... (truncated)"


def _relative(site: str) -> str:
    """Shorten a call site to a path relative to the working directory when it is under it.

    Only when it is under it: ``os.path.relpath`` will happily walk out of the
    tree with a row of ``..`` segments, which is longer than the absolute path
    and harder to read.
    """
    root = os.getcwd() + os.sep
    if site.startswith(root):
        return site[len(root) :]
    return site
