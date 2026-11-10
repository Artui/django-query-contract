from __future__ import annotations

from collections.abc import Sequence

from django_query_contract.source_location.relative_to_cwd import relative_to_cwd
from django_query_contract.types.attribution import Attribution
from django_query_contract.utils import shorten

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
    """Describe ``attributions`` as indented blocks, busiest line first."""
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
        named = ", ".join(f"'{alias}'" for alias in attribution.aliases)
        lines.append(f"       across connections {named}")
    return "\n".join(lines)


def _shapes(attribution: Attribution, max_sql: int) -> str:
    """The statement, when there was one, and otherwise how many there were."""
    fingerprints = attribution.fingerprints
    if len(fingerprints) == 1:
        return shorten(fingerprints[0], max_sql)
    return f"{len(fingerprints)} statement shapes"
