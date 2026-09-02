"""Read a capture back as the lines its statements came from."""

from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.attribution import Attribution
from django_query_contract.query_record import QueryRecord
from django_query_contract.stack_frame import StackFrame


def group_by_call_site(records: Iterable[QueryRecord]) -> tuple[Attribution, ...]:
    """Group ``records`` by the line that emitted them, busiest line first.

    "These forty statements came from these three lines" -- the other axis of
    the grouping the N+1 detector does, and the one that has an answer for
    *every* statement rather than only for a repeated one. Until this existed,
    a capture would name a call site only where a finding rendered one, so a
    failed count assertion with no N+1 in it named no lines at all.

    **It is called ``group_`` and not ``find_``, and the difference is not
    cosmetic.** :func:`~django_query_contract.find_n_plus_one` finds defects and
    its key is the whole call stack. This finds nothing: it re-files the same
    statements under the line that emitted them, which merges call paths a
    finding deliberately keeps apart. Both are true at once, and
    :class:`~django_query_contract.Attribution` sets out why the merge is safe
    here and would be wrong there.

    **Every record ends up in exactly one group, including the ones with no
    call site.** A record with no stack, or whose kept frames were all Django's
    own, joins the single group whose ``call_site`` is ``None``. That group is
    ordered like any other, on its size -- there is no rule here about which
    group is the interesting one, and in a capture rebuilt from a
    ``CaptureQueriesContext`` it is genuinely the headline: nothing in it can be
    placed.

    Takes any iterable of records, so it reads a
    :class:`~django_query_contract.QueryCapture` directly, a slice of one, or
    the records of a single connection.

    ```python
    from django_query_contract import QueryCapture, group_by_call_site

    with QueryCapture() as capture:
        render_author_list()

    for attribution in group_by_call_site(capture):
        print(attribution.count, attribution.call_site)
    ```

    Args:
        records: The executions to attribute.

    Returns:
        The attributions, ordered by ``count`` descending and then by where each
        line's first statement appeared in the capture. That second key is what
        makes the order total: no two groups share a first statement, so two
        runs over one capture produce the same list and a report never
        reshuffles.
    """
    buckets: dict[StackFrame | None, list[QueryRecord]] = {}
    for record in records:
        # ``call_site`` rather than a rule of this module's own. It is the one
        # place the package decides which frame is the interesting one, and a
        # second copy of that decision here is how a report would come to name
        # one line under a finding and a different line in the attribution of
        # the very same statement.
        buckets.setdefault(record.call_site, []).append(record)

    attributions = [
        Attribution(call_site=call_site, records=tuple(bucket))
        for call_site, bucket in buckets.items()
    ]
    attributions.sort(key=lambda attribution: (-attribution.count, attribution.first_index))
    return tuple(attributions)
