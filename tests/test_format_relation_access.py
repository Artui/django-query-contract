"""The relation report: the evidence for an index, and no recommendation.

This is the milestone that asked whether index advice could be made a claim this
package is willing to state, and concluded it could not. What is checked here is
therefore as much the *wording* as the numbers: the report has to hand a reader
everything a decision needs while saying plainly that it is not making one.
"""

from __future__ import annotations

from django_query_contract import (
    PlanCapture,
    QueryPlan,
    QueryRecord,
    StackFrame,
    format_relation_access,
)
from tests.plan_payloads import BITMAP_AND, PARALLEL_SCAN, SERIAL_SCAN, UNINDEXED_SCAN, WHALE_JOIN

_SQL = "SELECT id FROM testapp_order WHERE reference = %s"

_PKEY = "CREATE UNIQUE INDEX testapp_order_pkey ON public.testapp_order USING btree (id)"
_CUSTOMER = (
    "CREATE INDEX testapp_order_customer_id_5f8a ON public.testapp_order USING btree (customer_id)"
)


def _record(index: int, plan: QueryPlan | None, *, sql: str = _SQL, line: int = 10) -> QueryRecord:
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


def _capture(
    records: list[QueryRecord], *, indexes: dict[str, tuple[str, ...]] | None = None
) -> PlanCapture:
    capture = PlanCapture()
    capture._records = list(records)
    capture._indexes = {} if indexes is None else indexes
    return capture


def _measured(payload: list[dict[str, object]]) -> QueryPlan:
    return QueryPlan.from_explain(payload, analyzed=True)


def test_a_capture_with_no_plans_says_nothing() -> None:
    assert format_relation_access(_capture([_record(0, None)])) == ""


def test_the_report_declines_the_advice_in_the_text_a_reader_will_read() -> None:
    """The declination is not a docstring: it is printed where the numbers are.

    A reader looking at "99,999 rows discarded" will supply the missing verdict
    themselves unless the report says out loud that it is withholding one.
    """
    report = format_relation_access(_capture([_record(0, _measured(UNINDEXED_SCAN))]))

    assert "No index is recommended" in report
    assert "judgement about size" in report


def test_a_table_read_without_an_index_is_named_with_what_the_server_counted() -> None:
    report = format_relation_access(_capture([_record(0, _measured(UNINDEXED_SCAN))]))

    assert "testapp_order" in report
    assert "1 read, 1 without an index" in report
    assert "99,999" in report
    assert "((reference)::text = %s::text)" in report
    assert "views.py:10 in dashboard" in report


def test_the_report_never_prints_a_bound_value() -> None:
    """The rule the whole package states, checked at the one place it would break.

    ``EXPLAIN`` renders the predicate with the value in it, so a report printing
    the filter verbatim would put customer data into CI output on every failing
    test. The redaction happens at parse time; this is the assertion that the
    redaction is what reaches the page.
    """
    report = format_relation_access(_capture([_record(0, _measured(UNINDEXED_SCAN))]))

    assert "601980.6826913885" not in report


def test_a_table_read_through_indexes_names_them_and_counts_no_unindexed_read() -> None:
    report = format_relation_access(_capture([_record(0, _measured(BITMAP_AND))]))

    assert "1 read, none without an index" in report
    assert "dump_mod_100, dump_mod_97" in report


def test_the_indexes_postgres_already_has_are_printed_as_postgres_writes_them() -> None:
    """The only ``CREATE INDEX`` statements this package will ever print.

    The milestone imagined emitting the ones that should exist. What it can
    state instead is the ones that do, in the server's own words, so a reader
    comparing them against the filter above can see what is not covered.
    """
    report = format_relation_access(
        _capture(
            [_record(0, _measured(UNINDEXED_SCAN))],
            indexes={"testapp_order": (_PKEY, _CUSTOMER)},
        )
    )

    assert "PostgreSQL has 2 indexes on testapp_order" in report
    assert _PKEY in report
    assert "USING btree (customer_id)" in report


def test_a_relation_the_catalogue_said_nothing_about_prints_no_index_block() -> None:
    """An empty list would read as "this table has no indexes", which is a different claim."""
    report = format_relation_access(_capture([_record(0, _measured(UNINDEXED_SCAN))]))

    assert "PostgreSQL has" not in report


def test_only_so_many_relations_are_listed_and_the_rest_are_counted() -> None:
    records = [
        _record(0, _measured(UNINDEXED_SCAN)),
        _record(1, _measured(WHALE_JOIN)),
    ]

    report = format_relation_access(_capture(records), max_relations=1)

    assert "and 2 more relations." in report


def test_a_long_index_definition_is_cut_the_same_way_a_long_statement_is() -> None:
    long_index = _PKEY + " WHERE " + "x" * 300

    report = format_relation_access(
        _capture(
            [_record(0, _measured(UNINDEXED_SCAN))],
            indexes={"testapp_order": (long_index,)},
        ),
        max_sql=80,
    )

    assert "... (truncated)" in report
    assert "x" * 300 not in report


def test_a_read_nothing_filtered_names_no_condition_and_no_discarded_rows() -> None:
    report = format_relation_access(_capture([_record(0, _measured(WHALE_JOIN))]))

    assert "testapp_book" in report
    # The bitmap heap scan filtered nothing, so there is nothing to report about
    # what it threw away -- and zero would be a measurement it never made.
    assert "discarded" not in report.split("testapp_book")[1].split("testapp_author")[0]


def test_a_statement_with_no_call_site_is_reported_rather_than_approximated() -> None:
    record = QueryRecord(
        index=0,
        sql=_SQL,
        fingerprint=_SQL,
        alias="default",
        vendor="postgresql",
        many=False,
        param_count=1,
        plan=_measured(UNINDEXED_SCAN),
    )

    report = format_relation_access(_capture([record]))

    assert "no frame outside Django" in report


def test_a_read_split_across_workers_reports_the_whole_read_and_shows_the_arithmetic() -> None:
    """The number a reader acts on is the total, and the printed one is named beside it.

    Without the second line the two payloads below -- one statement, one process
    against three -- would produce reports that disagree by a factor of three
    with nothing in either of them explaining why.
    """
    report = format_relation_access(_capture([_record(0, _measured(PARALLEL_SCAN))]))

    assert "most one read discarded: 1,124,097 rows, keeping 75,903" in report
    assert "3 loops (parallel workers)" in report
    assert "374,699 discarded per loop" in report


def test_the_same_read_in_one_process_prints_no_arithmetic_at_all() -> None:
    """A node that ran once has nothing to decompose, so the line does not appear."""
    report = format_relation_access(_capture([_record(0, _measured(SERIAL_SCAN))]))

    assert "most one read discarded: 1,124,098 rows, keeping 75,902" in report
    assert "per loop" not in report
    assert "loops" not in report
