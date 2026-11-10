from __future__ import annotations

from django_query_contract import PlanDefect


def test_there_are_exactly_two_kinds_and_that_is_the_design() -> None:
    """A guard on a decision, not on an implementation."""
    assert [defect.name for defect in PlanDefect] == ["PLANNER_BLIND", "SPILLED_TO_DISK"]


def test_each_kind_reads_as_the_sentence_a_report_prints() -> None:
    assert PlanDefect.PLANNER_BLIND.value == "planner blind"
    assert PlanDefect.SPILLED_TO_DISK.value == "spilled to disk"
