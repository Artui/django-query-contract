from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.types.attribution import Attribution
from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.stack_frame import StackFrame


def group_by_call_site(records: Iterable[QueryRecord]) -> tuple[Attribution, ...]:
    """Group ``records`` by the line that emitted them, busiest line first."""
    buckets: dict[StackFrame | None, list[QueryRecord]] = {}
    for record in records:
        buckets.setdefault(record.call_site, []).append(record)

    attributions = [
        Attribution(call_site=call_site, records=tuple(bucket))
        for call_site, bucket in buckets.items()
    ]
    attributions.sort(key=lambda attribution: (-attribution.count, attribution.first_index))
    return tuple(attributions)
