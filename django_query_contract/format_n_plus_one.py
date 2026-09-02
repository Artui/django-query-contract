"""Render one N+1 finding as the lines a reader can act on."""

from __future__ import annotations

from django_query_contract.n_plus_one import NPlusOne
from django_query_contract.utils import relative_to_cwd, shorten

# How many query indices to name before eliding. Eight is enough to see that the
# executions are consecutive, which is what a reader checks; a hundred of them
# would push the call site off the top of the terminal, and the call site is the
# only part anybody acts on.
_MAX_INDICES = 8


def format_n_plus_one(finding: NPlusOne, *, max_sql: int = 160, label: str = "") -> str:
    """Describe ``finding`` as an indented block, call site first.

    Call site first because that is the whole point. "42 similar queries" with
    no address is the output people turn off; the line that ran the loop is the
    line somebody edits, so it goes above the SQL rather than under it.

    Both reports in this package render a finding through here -- the section
    under a failed query-count assertion and the end-of-run listing -- so the
    two cannot drift into describing the same finding differently.

    Args:
        finding: The finding to describe.
        max_sql: Where to cut a long statement. The records keep the whole thing.
        label: Where the finding came from, when the caller is listing findings
            from more than one block. Omitted entirely when empty, so the block
            reads the same in a report that has only one.

    Returns:
        The block, indented, without a trailing newline.
    """
    site = finding.call_site
    where = (
        relative_to_cwd(str(site))
        if site is not None
        # Everything kept was Django's own. Reported, with the reason, rather
        # than filled in with the innermost frame available: "it came from
        # django/db/models/query.py" is true of every query ever executed.
        #
        # ``stack_truncated`` is deliberately *not* reported per finding on top
        # of this. Under a test runner it is true of every capture and says
        # nothing -- a query executed from a test function sits 38 frames deep,
        # 30 of them pytest's and pluggy's own constant preamble -- so printing
        # it would put a caveat on every line and mean nothing on any of them.
        # It stays on the finding for a reader who wants it, and the docs carry
        # the one case where the window can actually mislead.
        else "no frame outside Django (the capture's stack depth did not reach one)"
    )
    lines = [f"  {finding.count} x  from {where}"]
    if label:
        lines.append(f"       in {label}")
    lines.append(f"       {shorten(finding.fingerprint, max_sql)}")
    lines.append(f"       queries {_indices(finding)}")
    if len(finding.aliases) > 1:
        # The identity is (fingerprint, stack) and deliberately says nothing
        # about the connection, so one line querying two databases stays one
        # finding. That is only honest if the span is reported rather than lost.
        named = ", ".join(f"'{alias}'" for alias in finding.aliases)
        lines.append(f"       across connections {named}")
    return "\n".join(lines)


def _indices(finding: NPlusOne) -> str:
    """``#1, #2, #3`` -- where in the capture these executions were."""
    named = ", ".join(f"#{record.index}" for record in finding.records[:_MAX_INDICES])
    if finding.count > _MAX_INDICES:
        named += ", ..."
    return named
