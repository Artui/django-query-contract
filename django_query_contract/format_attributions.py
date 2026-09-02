"""Render call-site attributions as the lines a reader can act on."""

from __future__ import annotations

from collections.abc import Sequence

from django_query_contract.attribution import Attribution
from django_query_contract.utils import relative_to_cwd, shorten

# Why this differs from the sentence ``format_n_plus_one`` prints in the same
# position. A finding can only ever hold records that had a stack -- the
# detector skips the ones that did not -- so the only way its call site is
# missing is that the window was too small, and it says exactly that. An
# attribution groups every record it is given, so an unaddressed group here can
# also be one that never had a stack to walk. Naming one cause would be wrong
# half the time, so it names the shape of both.
_NO_CALL_SITE = "no frame outside Django (an empty stack, or a window that did not reach one)"


def format_attributions(
    attributions: Sequence[Attribution],
    *,
    max_sites: int = 5,
    max_sql: int = 160,
) -> str:
    """Describe ``attributions`` as indented blocks, busiest line first.

    A block and no heading, the way :func:`format_n_plus_one` renders a finding,
    because the caller is what knows why it is printing these: the section under
    a failed query-count assertion introduces them as the statements no call
    path repeated, and a report face would introduce them as something else
    again. A heading here would be printed under the caller's own.

    Args:
        attributions: The groups to describe, already ordered -- ``max_sites``
            keeps the front of the sequence, so an unordered one is truncated
            arbitrarily. :func:`~django_query_contract.group_by_call_site`
            returns them busiest first.
        max_sites: How many lines to name before summarising the rest.
        max_sql: Where to cut a long statement. The records keep the whole thing.

    Returns:
        The blocks, indented, without a trailing newline. Empty for an empty
        sequence, so a caller can print a heading only when there is something
        under it.
    """
    lines = [_block(attribution, max_sql=max_sql) for attribution in attributions[:max_sites]]
    if len(attributions) > max_sites:
        lines.append(f"  and {len(attributions) - max_sites} more call site(s).")
    return "\n".join(lines)


def _block(attribution: Attribution, *, max_sql: int) -> str:
    """One line's block: where, then what it ran."""
    site = attribution.call_site
    where = _NO_CALL_SITE if site is None else relative_to_cwd(str(site))
    lines = [
        f"  {attribution.count} x  from {where}",
        f"       {_shapes(attribution, max_sql)}",
    ]
    if len(attribution.aliases) > 1:
        # Nothing else in the block would say so: the group is keyed on the line
        # and says nothing about the connection, exactly as a finding's identity
        # does not.
        named = ", ".join(f"'{alias}'" for alias in attribution.aliases)
        lines.append(f"       across connections {named}")
    return "\n".join(lines)


def _shapes(attribution: Attribution, max_sql: int) -> str:
    """The statement, when there was one, and otherwise how many there were.

    A line that emitted one shape is worth printing in full -- it is the same
    thing a finding prints, and a reader recognises the query. A line that
    emitted five is a loop body or a dispatch point, and five statements under
    one address would bury the addresses either side of it; the count says the
    line is busy, which is the part that decides whether to go and look.
    """
    fingerprints = attribution.fingerprints
    if len(fingerprints) == 1:
        return shorten(fingerprints[0], max_sql)
    return f"{len(fingerprints)} statement shapes"
