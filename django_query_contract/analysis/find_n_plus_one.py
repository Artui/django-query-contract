from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.types.n_plus_one import NPlusOne
from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.stack_frame import StackFrame


def find_n_plus_one(records: Iterable[QueryRecord]) -> tuple[NPlusOne, ...]:
    """Group ``records`` into N+1 findings, most repeated first."""
    buckets: dict[tuple[str, tuple[StackFrame, ...]], list[QueryRecord]] = {}
    for record in records:
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
