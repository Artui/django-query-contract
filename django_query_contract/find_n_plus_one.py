"""Read a capture back as N+1 findings."""

from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.n_plus_one import NPlusOne
from django_query_contract.query_record import QueryRecord
from django_query_contract.stack_frame import StackFrame


def find_n_plus_one(records: Iterable[QueryRecord]) -> tuple[NPlusOne, ...]:
    """Group ``records`` into N+1 findings, most repeated first.

    The whole of the detector, and it is short because the definition is: bucket
    every execution by ``(fingerprint, stack)`` and keep the buckets holding more
    than one. There is no threshold to configure -- "more than once from the same
    place" is what the word means -- and no rule that decides some repetitions
    are interesting and others are not. See :class:`NPlusOne` for why the key is
    the whole stack rather than the call site, and for why a legitimate batched
    write is reported like any other repetition.

    **A record with no call stack is not considered.** It cannot be: the identity
    is half stack, and a record rebuilt from a ``CaptureQueriesContext`` has
    none. Bucketing those together would say "these ran from one place" on the
    strength of knowing nothing about where any of them ran, which is a false
    positive manufactured out of a gap in the input. They are skipped, and
    ``format_capture_report`` says how many were skipped rather than reporting a
    clean bill of health it did not earn.

    Takes any iterable of records, so it reads a
    :class:`~django_query_contract.QueryCapture` directly, a slice of one, or
    the records of a single connection.

    ```python
    from django_query_contract import QueryCapture, find_n_plus_one

    with QueryCapture() as capture:
        render_author_list()

    for finding in find_n_plus_one(capture):
        print(finding.count, finding.call_site, finding.fingerprint)
    ```

    Args:
        records: The executions to group.

    Returns:
        The findings, ordered by ``count`` descending and then by where each
        first appeared in the capture. That second key is what makes the order
        total: no two findings share a first execution, so two runs over one
        capture produce the same list and a report never reshuffles.
    """
    buckets: dict[tuple[str, tuple[StackFrame, ...]], list[QueryRecord]] = {}
    for record in records:
        # An empty stack is the one input this cannot form an identity from, and
        # it arrives from a real place -- ``QueryCapture.from_capture_context``.
        if not record.stack:
            continue
        buckets.setdefault((record.fingerprint, record.stack), []).append(record)

    findings = [
        NPlusOne(fingerprint=fingerprint, stack=stack, records=tuple(bucket))
        for (fingerprint, stack), bucket in buckets.items()
        if len(bucket) > 1
    ]
    findings.sort(key=lambda finding: (-finding.count, finding.first_index))
    return tuple(findings)
