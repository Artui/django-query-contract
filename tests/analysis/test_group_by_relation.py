"""Reading a capture's plans back as the tables they touched."""

from __future__ import annotations

from django_query_contract import (
    QueryCapture,
    QueryPlan,
    QueryRecord,
    StackFrame,
    group_by_relation,
)
from tests.plan_payloads import BITMAP_AND, UNINDEXED_SCAN, WHALE_JOIN

_SQL = "SELECT id FROM testapp_order WHERE reference = %s"


def _record(
    index: int,
    plan: QueryPlan | None,
    *,
    sql: str = _SQL,
    line: int = 10,
) -> QueryRecord:
    return QueryRecord(
        index=index,
        sql=sql,
        fingerprint=sql,
        alias="default",
        vendor="postgresql",
        many=False,
        param_count=1,
        stack=(StackFrame(filename="/app/views.py", lineno=line, function="dashboard"),),
        plan=plan,
    )


def _measured(payload: list[dict[str, object]]) -> QueryPlan:
    return QueryPlan.from_explain(payload, analyzed=True)


def test_every_relation_a_plan_read_gets_a_group() -> None:
    """A join reads two tables, and both are named."""
    accesses = group_by_relation([_record(0, _measured(WHALE_JOIN))])

    assert {access.relation for access in accesses} == {"testapp_author", "testapp_book"}


def test_groups_are_ordered_by_reads_and_then_by_where_the_first_one_appeared() -> None:
    """The same total order attribution uses, and for the same reason.

    Ordering by rows discarded would be a soft verdict -- the report would be
    ranking relations by how badly they need an index, which is exactly the
    judgement this package declines to make. A count of measurements ranks
    nothing.
    """
    records = [
        _record(0, _measured(WHALE_JOIN)),
        _record(1, _measured(UNINDEXED_SCAN)),
        _record(2, _measured(UNINDEXED_SCAN)),
    ]

    accesses = group_by_relation(records)

    assert [(access.relation, access.count) for access in accesses] == [
        ("testapp_order", 2),
        ("testapp_author", 1),
        ("testapp_book", 1),
    ]


def test_the_table_that_discarded_most_is_not_moved_to_the_front() -> None:
    """The order a reader would find most useful, refused on purpose.

    Ranking tables by how many rows they threw away is ranking them by how badly
    they want an index, which is the judgement this package declines to make --
    and a sort key is a quiet way of making it anyway. So the two orders are
    pulled apart here: ``testapp_order`` discards five times what
    ``testapp_author`` does and still comes last, because it was read once and
    the others twice.
    """
    records = [
        _record(0, _measured(UNINDEXED_SCAN)),
        _record(1, _measured(WHALE_JOIN)),
        _record(2, _measured(WHALE_JOIN)),
    ]

    accesses = group_by_relation(records)

    discarded = {
        access.relation: access.most_rows_discarded and access.most_rows_discarded[0]
        for access in accesses
    }
    assert discarded["testapp_order"] == 99999.0
    assert discarded["testapp_author"] == 19999.0
    assert [access.relation for access in accesses] == [
        "testapp_author",
        "testapp_book",
        "testapp_order",
    ]


def test_two_relations_one_statement_read_come_out_in_the_order_the_plan_listed_them() -> None:
    """Where this ordering differs from attribution's, and it is not a tie left open.

    An attribution's first statement is unique to it, so ``count`` and that
    index are a total order. A statement reads *several* relations, so two
    groups can share a first statement and both keys tie. Plan order settles it
    -- parents before children, the order ``EXPLAIN`` printed -- which is
    deterministic and is the order a reader of the plan already has.
    """
    accesses = group_by_relation([_record(0, _measured(WHALE_JOIN))])

    assert [access.first_index for access in accesses] == [0, 0]
    assert [access.relation for access in accesses] == ["testapp_author", "testapp_book"]


def test_a_plan_that_reads_one_relation_twice_contributes_two_reads() -> None:
    payload = [{"Plan": dict(WHALE_JOIN[0]["Plan"])}]
    payload[0]["Plan"]["Plans"] = [
        dict(WHALE_JOIN[0]["Plan"]["Plans"][0]),
        dict(WHALE_JOIN[0]["Plan"]["Plans"][0]),
    ]

    (access,) = group_by_relation([_record(0, QueryPlan.from_explain(payload, analyzed=True))])

    assert access.relation == "testapp_author"
    assert access.count == 2
    assert len(access.records) == 2


def test_a_record_with_no_plan_contributes_nothing_rather_than_raising() -> None:
    """Every record of an ordinary capture, which is the common case."""
    assert group_by_relation([_record(0, None)]) == ()


def test_a_refused_statement_read_no_relation_anybody_can_name() -> None:
    refused = QueryPlan.refused("executemany was not explained.")

    assert group_by_relation([_record(0, refused)]) == ()


def test_a_plan_taken_without_analyze_still_says_which_tables_it_would_read() -> None:
    """Unlike a defect, an access needs no measurement: the plan names the table.

    ``find_plan_defects`` skips an unanalyzed plan because neither defect is
    decidable without an actual row count. This is a grouping and not a
    detector, so it reports what the plan says and lets the report note that
    nothing under it was measured.
    """
    (access,) = group_by_relation([_record(0, QueryPlan.from_explain(BITMAP_AND, analyzed=False))])

    assert access.relation == "testapp_order"
    assert access.indexes_used == ("dump_mod_100", "dump_mod_97")


def test_it_reads_a_capture_directly() -> None:
    assert group_by_relation(QueryCapture()) == ()
