"""The two kinds of plan defect, and the fact that there are two."""

from __future__ import annotations

from django_query_contract import PlanDefect


def test_there_are_exactly_two_kinds_and_that_is_the_design() -> None:
    """A guard on a decision, not on an implementation.

    The plan this package was built from listed four candidate findings. Two of
    them -- a sequential scan over a row threshold, and a nested loop with a
    large inner -- are numbers wearing a description, and a number is the knob
    this package refuses. A third member appearing here without that argument
    being revisited is the thing worth failing a build over.
    """
    assert [defect.name for defect in PlanDefect] == ["PLANNER_BLIND", "SPILLED_TO_DISK"]


def test_each_kind_reads_as_the_sentence_a_report_prints() -> None:
    assert PlanDefect.PLANNER_BLIND.value == "planner blind"
    assert PlanDefect.SPILLED_TO_DISK.value == "spilled to disk"
