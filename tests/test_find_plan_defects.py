"""The plan reader: two defects, both decided without a threshold.

The records here are assembled rather than captured, and that is a deliberate
split rather than a shortcut. A plan can only come from PostgreSQL, and this
suite's gate runs on SQLite; the payloads underneath these records are a real
server's own output, and ``tests/test_plan_capture_postgres.py`` runs the same
detector over a live shaped database so the assembly cannot quietly disagree
with the thing it stands in for.
"""

from __future__ import annotations

from django_query_contract import (
    PlanDefect,
    QueryPlan,
    QueryRecord,
    StackFrame,
    find_plan_defects,
)
from tests.plan_payloads import SPILLED_HASH, SPILLED_SORT, WHALE_JOIN, tail_join

_SQL = "SELECT b.id FROM child b INNER JOIN parent a ON (b.parent_id = a.id) WHERE a.name = %s"


def _record(
    index: int,
    plan: QueryPlan | None,
    *,
    sql: str = _SQL,
    line: int = 10,
) -> QueryRecord:
    """One execution, with a stack a call site can be read off."""
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


def test_one_estimate_and_two_truths_is_a_finding() -> None:
    """The defect the shaped-database dependency exists for.

    Two executions of one statement shape, both priced at 20 rows, one producing
    20,323 and the other 6. There is no threshold in that sentence: the grouping
    is an equality and the finding is an inequality.
    """
    records = [_record(0, _measured(WHALE_JOIN)), _record(1, _measured(tail_join()), line=11)]

    (finding,) = [
        found for found in find_plan_defects(records) if found.defect is PlanDefect.PLANNER_BLIND
    ]

    assert finding.count == 2
    assert finding.estimated_rows == 20.0
    assert finding.actual_rows == (20323.0, 6.0)
    assert finding.first_index == 0


def test_one_estimate_and_one_truth_is_not() -> None:
    """Two executions the planner priced alike that really were alike. Nothing to say."""
    records = [_record(0, _measured(WHALE_JOIN)), _record(1, _measured(WHALE_JOIN), line=11)]

    assert [
        found for found in find_plan_defects(records) if found.defect is PlanDefect.PLANNER_BLIND
    ] == []


def test_a_single_execution_is_never_blindness() -> None:
    """One measurement cannot separate "the planner is wrong" from "this row is unusual".

    The same rule as the growth assertion, which refuses to make a claim from one
    world. Two executions are what turn an estimate into a claim about a shape.
    """
    records = [_record(0, _measured(WHALE_JOIN))]

    assert find_plan_defects(records) == ()


def test_two_executions_the_planner_priced_differently_are_not_blindness() -> None:
    """The planner told them apart, which is the opposite of the accusation."""
    other = _measured(tail_join())
    assert other.root is not None
    differently = QueryPlan.from_explain(
        [
            {
                "Plan": {
                    "Node Type": "Nested Loop",
                    "Plan Rows": 5000,
                    "Actual Rows": 6,
                }
            }
        ],
        analyzed=True,
    )
    records = [_record(0, _measured(WHALE_JOIN)), _record(1, differently, line=11)]

    assert find_plan_defects(records) == ()


def test_three_executions_produce_a_finding_for_the_pair_that_shared_an_estimate() -> None:
    """Grouping on the estimate rather than on the fingerprint alone.

    Requiring the whole group to agree would lose the pair that did, for no gain
    -- and the pair that did is the finding.
    """
    apart = QueryPlan.from_explain(
        [{"Plan": {"Node Type": "Nested Loop", "Plan Rows": 900, "Actual Rows": 900}}],
        analyzed=True,
    )
    records = [
        _record(0, _measured(WHALE_JOIN)),
        _record(1, apart, line=11),
        _record(2, _measured(tail_join()), line=12),
    ]

    (finding,) = find_plan_defects(records)

    assert finding.defect is PlanDefect.PLANNER_BLIND
    assert [record.index for record in finding.records] == [0, 2]


def test_blindness_is_keyed_on_the_statement_and_not_on_the_call_stack() -> None:
    """The opposite choice from the N+1 identity, and the same rule behind both.

    A finding is keyed on what the accused can see. The planner is handed SQL and
    never hears about the stack, so two lines emitting one shape are one blind
    spot -- where two lines running one loop are two defects with two fixes.
    """
    records = [
        _record(0, _measured(WHALE_JOIN), line=10),
        _record(1, _measured(tail_join()), line=4000),
    ]

    (finding,) = find_plan_defects(records)

    assert len(finding.call_sites) == 2
    assert {site.lineno for site in finding.call_sites if site is not None} == {10, 4000}


def test_a_sort_that_spilled_is_a_finding_on_its_own() -> None:
    records = [_record(0, _measured(SPILLED_SORT), sql="SELECT id FROM child ORDER BY title")]

    (finding,) = find_plan_defects(records)

    assert finding.defect is PlanDefect.SPILLED_TO_DISK
    assert finding.count == 1
    assert finding.nodes[0].sort_space_type == "Disk"


def test_a_hash_that_spilled_is_found_at_the_node_that_spilled() -> None:
    """One finding per node, not per statement: a plan can spill in two places."""
    records = [_record(0, _measured(SPILLED_HASH), sql="SELECT b.id FROM child b JOIN parent a")]

    (finding,) = [
        found for found in find_plan_defects(records) if found.defect is PlanDefect.SPILLED_TO_DISK
    ]

    assert finding.nodes[0].node_type == "Hash"
    assert finding.nodes[0].hash_batches == 16


def test_findings_come_back_blindness_first_then_spills_in_capture_order() -> None:
    records = [
        _record(0, _measured(SPILLED_SORT), sql="SELECT id FROM child ORDER BY title"),
        _record(1, _measured(WHALE_JOIN)),
        _record(2, _measured(tail_join()), line=11),
    ]

    found = find_plan_defects(records)

    assert [finding.defect for finding in found] == [
        PlanDefect.PLANNER_BLIND,
        PlanDefect.SPILLED_TO_DISK,
    ]
    assert found[0].first_index == 1
    assert found[1].first_index == 0


def test_a_record_with_no_plan_contributes_nothing() -> None:
    """Every record of an ordinary capture, so this has to be quiet rather than loud."""
    assert find_plan_defects([_record(0, None), _record(1, None)]) == ()


def test_a_refused_statement_contributes_nothing() -> None:
    records = [_record(0, QueryPlan.refused("not a SELECT")), _record(1, QueryPlan.refused("x"))]

    assert find_plan_defects(records) == ()


def test_a_plan_taken_without_analyze_yields_no_finding_at_all() -> None:
    """Not even a spill: every key a spill is read from arrives with ANALYZE.

    Reported by the renderer rather than passed over in silence, because a plan
    with nothing to check against is exactly the shape a vacuous pass would take.
    """
    planned = QueryPlan.from_explain(
        [{"Plan": {"Node Type": "Sort", "Plan Rows": 400000, "Sort Space Type": "Disk"}}],
        analyzed=False,
    )
    records = [_record(0, planned), _record(1, planned, line=11)]

    assert find_plan_defects(records) == ()


def test_a_plan_a_caller_built_with_no_root_is_skipped_rather_than_crashing() -> None:
    """``QueryPlan`` is a public record and a caller can hold one it made itself."""
    records = [_record(0, QueryPlan(root=None, analyzed=True))]

    assert find_plan_defects(records) == ()
