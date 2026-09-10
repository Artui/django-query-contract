"""One plan defect, and the evidence it carries."""

from __future__ import annotations

from django_query_contract import (
    PlanDefect,
    PlanFinding,
    PlanNode,
    QueryPlan,
    QueryRecord,
    StackFrame,
)
from tests.plan_payloads import WHALE_JOIN, tail_join

_SQL = "SELECT b.id FROM child b JOIN parent a ON (b.parent_id = a.id) WHERE a.name = %s"


def _record(index: int, payload: list[dict[str, object]], *, line: int, stack: bool = True):
    plan = QueryPlan.from_explain(payload, analyzed=True)
    frames = (StackFrame(filename="/app/views.py", lineno=line, function="dashboard"),)
    return QueryRecord(
        index=index,
        sql=_SQL,
        fingerprint=_SQL,
        alias="default",
        vendor="postgresql",
        many=False,
        param_count=1,
        stack=frames if stack else (),
        plan=plan,
    )


def _blind() -> PlanFinding:
    first = _record(3, WHALE_JOIN, line=10)
    second = _record(9, tail_join(), line=11)
    assert first.plan is not None and first.plan.root is not None
    assert second.plan is not None and second.plan.root is not None
    return PlanFinding(
        defect=PlanDefect.PLANNER_BLIND,
        records=(first, second),
        nodes=(first.plan.root, second.plan.root),
    )


def test_a_finding_counts_the_executions_it_rests_on() -> None:
    finding = _blind()

    assert finding.count == 2
    assert finding.fingerprint == _SQL
    assert finding.first_index == 3


def test_the_shared_estimate_and_the_truths_that_disagreed_with_it() -> None:
    finding = _blind()

    assert finding.estimated_rows == 20.0
    assert finding.actual_rows == (20323.0, 6.0)


def test_the_call_sites_are_every_line_involved_in_the_order_first_seen() -> None:
    finding = _blind()

    sites = finding.call_sites

    assert len(sites) == 2
    assert [site.lineno for site in sites if site is not None] == [10, 11]


def test_two_executions_from_one_line_name_that_line_once() -> None:
    """Deduplicated, because a report naming one address twice reads as two."""
    first = _record(0, WHALE_JOIN, line=10)
    second = _record(1, tail_join(), line=10)
    assert first.plan is not None and first.plan.root is not None
    assert second.plan is not None and second.plan.root is not None

    finding = PlanFinding(
        defect=PlanDefect.PLANNER_BLIND,
        records=(first, second),
        nodes=(first.plan.root, second.plan.root),
    )

    assert len(finding.call_sites) == 1


def test_a_record_with_no_frame_outside_django_reports_that_rather_than_guessing() -> None:
    record = _record(0, WHALE_JOIN, line=10, stack=False)
    assert record.plan is not None and record.plan.root is not None

    finding = PlanFinding(
        defect=PlanDefect.SPILLED_TO_DISK, records=(record,), nodes=(record.plan.root,)
    )

    assert finding.call_sites == (None,)


def test_a_finding_a_caller_built_from_an_unmeasured_node_says_so() -> None:
    """``actual_rows`` reports what the nodes hold rather than asserting how it was built.

    ``find_plan_defects`` only makes findings out of measured plans, so this
    cannot arrive from inside the package -- but ``PlanFinding`` is public and
    narrowing the type here would be this record making a claim about its author.
    """
    record = _record(0, WHALE_JOIN, line=10)
    node = PlanNode.from_explain({"Node Type": "Sort", "Plan Rows": 10})

    finding = PlanFinding(defect=PlanDefect.SPILLED_TO_DISK, records=(record,), nodes=(node,))

    assert finding.actual_rows == (None,)
    assert finding.estimated_rows == 10.0
