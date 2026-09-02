"""One relation, every plan node that read it, and what that says and does not say."""

from __future__ import annotations

from copy import deepcopy

from django_query_contract import PlanNode, QueryPlan, QueryRecord, RelationAccess, StackFrame
from tests.plan_payloads import BITMAP_AND, UNINDEXED_SCAN, WHALE_JOIN


def _record(index: int, payload: list[dict[str, object]], *, line: int = 10) -> QueryRecord:
    sql = "SELECT id FROM testapp_order WHERE reference = %s"
    return QueryRecord(
        index=index,
        sql=sql,
        fingerprint=sql,
        alias="default",
        vendor="postgresql",
        many=False,
        param_count=1,
        stack=(StackFrame(filename="/app/views.py", lineno=line, function="dashboard"),),
        plan=QueryPlan.from_explain(payload, analyzed=True),
    )


def _root(payload: list[dict[str, object]]) -> PlanNode:
    return PlanNode.from_explain(payload[0]["Plan"])


def _access(*payloads: list[dict[str, object]]) -> RelationAccess:
    records = tuple(_record(index, payload) for index, payload in enumerate(payloads))
    return RelationAccess(
        relation="testapp_order",
        records=records,
        nodes=tuple(_root(payload) for payload in payloads),
    )


def test_the_count_is_reads_and_not_statements() -> None:
    """A plan that reads one table twice contributes two reads to it.

    Records and nodes are parallel, so a self-join puts the same record in twice.
    Counting statements instead would make the report disagree with itself: the
    reads listed under a relation would outnumber the number beside its name.
    """
    access = _access(UNINDEXED_SCAN, BITMAP_AND)

    assert access.count == 2
    assert access.first_index == 0


def test_a_read_with_no_index_anywhere_under_it_is_an_unindexed_read() -> None:
    access = _access(UNINDEXED_SCAN, BITMAP_AND)

    assert [node.node_type for node in access.unindexed_reads] == ["Seq Scan"]
    assert access.indexes_used == ("dump_mod_100", "dump_mod_97")


def test_the_conditions_are_the_filters_with_their_values_taken_out() -> None:
    access = _access(UNINDEXED_SCAN)

    assert access.conditions == ("((reference)::text = %s::text)",)


def test_one_filter_shape_run_with_two_values_is_one_condition() -> None:
    """What redacting the predicate buys: the group holds together."""
    other = deepcopy(UNINDEXED_SCAN)
    other[0]["Plan"]["Filter"] = "((reference)::text = 'a different value'::text)"

    access = _access(UNINDEXED_SCAN, other)

    assert access.count == 2
    assert len(access.conditions) == 1


def test_the_read_that_discarded_most_is_named_by_an_argmax_and_not_a_cut_off() -> None:
    """An argmax introduces no number; a threshold would be the knob this package refuses."""
    smaller = deepcopy(UNINDEXED_SCAN)
    smaller[0]["Plan"]["Rows Removed by Filter"] = 3

    access = _access(smaller, UNINDEXED_SCAN)
    worst = access.most_rows_discarded

    assert worst is not None
    rows, node = worst
    assert rows == 99999.0
    assert node.actual_rows == 1.0


def test_a_relation_nothing_filtered_has_no_discarded_rows_to_name() -> None:
    """``None`` rather than zero: PostgreSQL emits the key only when it filtered."""
    access = RelationAccess(
        relation="testapp_book",
        records=(_record(0, WHALE_JOIN),),
        nodes=(_root(WHALE_JOIN).children[1],),
    )

    assert access.most_rows_discarded is None
    assert access.conditions == ()


def test_the_lines_that_read_a_relation_are_named_once_each_in_the_order_seen() -> None:
    records = (
        _record(0, UNINDEXED_SCAN),
        _record(1, UNINDEXED_SCAN, line=11),
        _record(2, UNINDEXED_SCAN),
    )
    access = RelationAccess(
        relation="testapp_order",
        records=records,
        nodes=tuple(_root(UNINDEXED_SCAN) for _ in records),
    )

    assert [str(site) for site in access.call_sites] == [
        "/app/views.py:10 in dashboard",
        "/app/views.py:11 in dashboard",
    ]
