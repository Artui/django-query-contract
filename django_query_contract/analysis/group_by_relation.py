from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.types.plan_node import PlanNode
from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.relation_access import RelationAccess


def group_by_relation(records: Iterable[QueryRecord]) -> tuple[RelationAccess, ...]:
    """Group the plan nodes in ``records`` by the table each one read."""
    buckets: dict[str, list[tuple[QueryRecord, PlanNode]]] = {}
    for record in records:
        plan = record.plan
        if plan is None:
            continue
        for node in plan.nodes:
            if node.relation is not None:
                buckets.setdefault(node.relation, []).append((record, node))

    accesses = [
        RelationAccess(
            relation=relation,
            records=tuple(record for record, _ in reads),
            nodes=tuple(node for _, node in reads),
        )
        for relation, reads in buckets.items()
    ]
    accesses.sort(key=lambda access: (-access.count, access.first_index))
    return tuple(accesses)
