"""Read a capture's plans back as the tables they touched."""

from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.plan_node import PlanNode
from django_query_contract.query_record import QueryRecord
from django_query_contract.relation_access import RelationAccess


def group_by_relation(records: Iterable[QueryRecord]) -> tuple[RelationAccess, ...]:
    """Group the plan nodes in ``records`` by the table each one read.

    "These twelve statements read ``orders``, eleven of them without an index,
    and here is what PostgreSQL threw away" -- the third axis of the same
    capture, after the call path a defect repeats on and the line a statement
    came from. It is the reader the index-advice milestone became once the
    advice itself turned out to need a threshold; the argument is at
    :class:`~django_query_contract.RelationAccess`.

    **It is called ``group_`` and not ``find_``, and that is load bearing here
    more than anywhere.** This finds nothing and accuses nothing. It re-files
    plan nodes under the table they read, which lets a report put a sequential
    read of one table beside an indexed read of the same table -- a juxtaposition
    that would be a false accusation if anything claimed it meant something,
    because two statements filtering different columns are not two measurements
    of one thing.

    **Only nodes that name a relation are grouped.** A join, a sort and an
    aggregate read no table of their own, and inventing one for them would put a
    row in this report that no ``CREATE INDEX`` could ever answer. Unlike
    :func:`~django_query_contract.find_plan_defects`, plans taken without
    ``ANALYZE`` are kept: which table a plan reads is on the plan whether or not
    it was measured, and only the discarded-row counts go missing.

    Takes any iterable of records, so it reads a
    :class:`~django_query_contract.PlanCapture` directly, a slice of one, or the
    records of a single connection. A record with no plan -- every record from
    an ordinary :class:`~django_query_contract.QueryCapture` -- contributes
    nothing, so calling this on a capture that took no plans returns nothing
    rather than raising.

    ```python
    from django_query_contract import PlanCapture, group_by_relation

    with PlanCapture() as capture:
        render_dashboard()

    for access in group_by_relation(capture):
        print(access.relation, access.count, len(access.unindexed_reads))
    ```

    Args:
        records: The executions to read.

    Returns:
        The accesses, ordered by ``count`` descending, then by where each
        relation's first statement appeared, and then -- for the two relations
        one statement read -- by the order the plan listed them.

        **Deliberately not ordered by rows discarded**, which is the order a
        reader would find most useful and is exactly why it is refused: ranking
        tables by how badly they want an index is the judgement this package
        declines to make, and a sort key is a quiet way of making it anyway. A
        count of measurements ranks nothing. There is a test that pulls the two
        orders apart, because a fixture where they agree would pass either way.
    """
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
