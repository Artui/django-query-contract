"""The plan report: findings first, then numbers nobody is allowed to judge.

The captures here are assembled from a real server's payloads rather than taken
from one, for the reason ``test_find_plan_defects.py`` sets out. What is being
checked is the wording and the ordering, and both are decisions this package
argues for at length -- so they get a test that fails when they change silently.
"""

from __future__ import annotations

from django_query_contract import (
    PlanCapture,
    QueryPlan,
    QueryRecord,
    StackFrame,
    format_query_plans,
)
from tests.plan_payloads import SPILLED_SORT, WHALE_JOIN, tail_join

_SQL = "SELECT b.id FROM child b JOIN parent a ON (b.parent_id = a.id) WHERE a.name = %s"


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


def _capture(records: list[QueryRecord], *, unanalyzed: tuple[str, ...] = ()) -> PlanCapture:
    """A closed capture holding these records.

    Assembled rather than run: taking these plans needs a PostgreSQL server, and
    this file is about what the renderer says rather than about where the plans
    came from.
    """
    capture = PlanCapture()
    capture._records = list(records)
    capture._unanalyzed = unanalyzed
    return capture


def _measured(payload: list[dict[str, object]]) -> QueryPlan:
    return QueryPlan.from_explain(payload, analyzed=True)


def test_a_capture_with_no_plans_says_nothing() -> None:
    """Every ordinary capture, so silence has to be the answer rather than a header."""
    assert format_query_plans(_capture([_record(0, None)])) == ""


def test_the_report_counts_what_it_explained_against_what_it_captured() -> None:
    report = format_query_plans(
        _capture(
            [
                _record(0, _measured(WHALE_JOIN)),
                _record(1, QueryPlan.refused("executemany has no single plan.")),
            ]
        )
    )

    assert report.splitlines()[0] == "2 statements captured, 1 of them explained."


def test_a_capture_without_analyze_says_nothing_here_was_measured() -> None:
    """Otherwise an empty findings section reads as a clean bill of health."""
    capture = _capture([_record(0, QueryPlan.from_explain(WHALE_JOIN, analyzed=False))])
    capture._analyze = False

    report = format_query_plans(capture)

    assert "without ANALYZE, so nothing here was measured" in report


def test_the_blindness_finding_prints_the_shared_estimate_and_the_truths() -> None:
    report = format_query_plans(
        _capture(
            [
                _record(0, _measured(WHALE_JOIN)),
                _record(1, _measured(tail_join()), line=11),
            ]
        )
    )

    assert "Plan findings -- what PostgreSQL's own output states:" in report
    assert "planner blind  2 executions, one estimate of 20 rows, actuals 20,323, 6" in report
    assert "app/views.py:10 in dashboard, /app/views.py:11 in dashboard" in report
    assert "queries #0, #1" in report


def test_a_spill_prints_what_postgres_said_about_it() -> None:
    report = format_query_plans(
        _capture([_record(0, _measured(SPILLED_SORT), sql="SELECT id FROM child ORDER BY title")])
    )

    assert "spilled to disk  Sort, external merge, 14,208 kB" in report


def test_a_finding_with_no_call_site_says_so_rather_than_naming_django() -> None:
    """ "It came from django/db/models/query.py" is true of every query ever run."""
    stackless = QueryRecord(
        index=0,
        sql=_SQL,
        fingerprint=_SQL,
        alias="default",
        vendor="postgresql",
        many=False,
        param_count=1,
        plan=_measured(SPILLED_SORT),
    )

    report = format_query_plans(_capture([stackless]))

    assert "no frame outside Django" in report


def test_the_estimate_block_reports_the_factor_and_judges_nothing() -> None:
    """The caveat is printed with the numbers, because the commonest big ratio is innocent."""
    report = format_query_plans(_capture([_record(0, _measured(WHALE_JOIN))]))

    assert "Where the planner was furthest out (reported, not judged" in report
    assert "LIMIT is meant to fall short" in report
    assert "1,016.1x  #0  Nested Loop: expected 20 rows, 20,323 arrived" in report


def test_the_estimate_block_names_the_relation_when_the_node_reads_one() -> None:
    plan = QueryPlan.from_explain(
        [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "testapp_order",
                    "Plan Rows": 1,
                    "Actual Rows": 5000,
                }
            }
        ],
        analyzed=True,
    )

    report = format_query_plans(_capture([_record(0, plan)]))

    assert "Seq Scan on testapp_order: expected 1 rows, 5,000 arrived" in report


def test_the_estimate_block_lists_the_worst_first_and_elides_the_rest() -> None:
    small = QueryPlan.from_explain(
        [{"Plan": {"Node Type": "Seq Scan", "Plan Rows": 10, "Actual Rows": 11}}], analyzed=True
    )
    records = [_record(index, small, sql=f"SELECT {index}") for index in range(5)]
    records.append(_record(5, _measured(WHALE_JOIN)))

    report = format_query_plans(_capture(records), max_estimates=2)

    body = report.split("Where the planner was furthest out")[1]
    assert body.index("#5") < body.index("#0")
    assert "and 4 more statements." in report


def test_only_so_many_findings_are_listed_before_the_rest_are_counted() -> None:
    records = [
        _record(index, _measured(SPILLED_SORT), sql=f"SELECT {index} ORDER BY title")
        for index in range(4)
    ]

    report = format_query_plans(_capture(records), max_findings=2)

    assert report.count("spilled to disk") == 2
    assert "and 2 more findings." in report


def test_a_long_statement_is_cut_in_the_report_and_kept_on_the_record() -> None:
    long_sql = "SELECT " + "x" * 400
    record = _record(0, _measured(SPILLED_SORT), sql=long_sql)

    report = format_query_plans(_capture([record]), max_sql=40)

    assert "... (truncated)" in report
    assert record.sql == long_sql


def test_what_was_not_explained_is_counted_by_the_reason_it_was_not() -> None:
    """A reader has to be able to see how much of the block the numbers do not cover."""
    refusal = QueryPlan.refused("a statement that does not begin with SELECT was not explained.")
    report = format_query_plans(
        _capture([_record(0, refusal), _record(1, refusal), _record(2, _measured(WHALE_JOIN))])
    )

    assert "2 statement(s) carried no plan:" in report
    assert "2 x  a statement that does not begin with SELECT" in report


def test_a_relation_with_no_statistics_is_named_before_anything_else() -> None:
    """It can invalidate every number under it, so it goes above them."""
    report = format_query_plans(
        _capture([_record(0, _measured(WHALE_JOIN))], unanalyzed=("testapp_order",))
    )

    lines = report.splitlines()
    assert "never gathered statistics for testapp_order" in lines[1]
    assert "Every plan below is a guess" in lines[2]
    # Above the numbers, because it can invalidate all of them.
    assert lines.index([line for line in lines if "furthest out" in line][0]) > 2


def test_a_report_over_plans_with_no_measurements_has_no_estimate_block() -> None:
    """Nothing to be wrong about, so nothing is printed rather than a row of zeroes."""
    planned = QueryPlan.from_explain(
        [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "child", "Plan Rows": 400000}}],
        analyzed=False,
    )
    capture = _capture([_record(0, planned)])
    capture._analyze = False

    report = format_query_plans(capture)

    assert "Where the planner was furthest out" not in report
    assert "nothing here was measured" in report
