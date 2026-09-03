"""One plan defect, with the executions and the nodes it was read off."""

from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.plan_defect import PlanDefect
from django_query_contract.plan_node import PlanNode
from django_query_contract.query_record import QueryRecord
from django_query_contract.stack_frame import StackFrame


@dataclass(frozen=True, slots=True)
class PlanFinding:
    """A defect PostgreSQL's own output states, and the evidence for it.

    :attr:`records` and :attr:`nodes` are parallel: ``nodes[i]`` is the node in
    ``records[i]``'s plan that the finding is about. One shape carries both
    kinds, because both are "these executions, at these nodes" and giving each
    kind its own class would make a report iterate two lists to say one thing.

    A spill has one execution and the node that spilled.
    :attr:`~django_query_contract.PlanDefect.PLANNER_BLIND` has two or more
    executions and each of their root nodes, which is where a plan states how
    many rows the query produces.

    Nothing in this package fails a test on one of these. A finding is a
    diagnosis printed under a failure somebody else's assertion produced, for
    the reason :class:`~django_query_contract.NPlusOne` sets out at length: a
    detector that fails builds is a detector that gets uninstalled.
    """

    defect: PlanDefect
    """Which of the two kinds this is."""

    records: tuple[QueryRecord, ...]
    """The executions this finding is made of, in capture order. At least one."""

    nodes: tuple[PlanNode, ...]
    """The node in each of those executions' plans that the finding is about."""

    @property
    def count(self) -> int:
        """How many executions this finding rests on."""
        return len(self.records)

    @property
    def fingerprint(self) -> str:
        """The normalised SQL shared by every execution here. See ``normalise_sql``."""
        return self.records[0].fingerprint

    @property
    def first_index(self) -> int:
        """Position in the capture of the first execution involved.

        The tie-break that makes an ordering total, so two runs over one capture
        list findings in the same order.
        """
        return self.records[0].index

    @property
    def call_sites(self) -> tuple[StackFrame | None, ...]:
        """The distinct lines these executions came from, in the order first seen.

        A tuple rather than a single frame, because the identity of
        :attr:`~django_query_contract.PlanDefect.PLANNER_BLIND` is the statement
        shape and not the call path -- the planner is handed SQL and never hears
        about the stack -- so one finding can legitimately span several lines. A
        ``None`` in here is a record whose kept frames were all Django's own,
        reported rather than approximated for the reason
        :attr:`~django_query_contract.QueryRecord.call_site` gives.
        """
        return tuple(dict.fromkeys(record.call_site for record in self.records))

    @property
    def estimated_rows(self) -> float:
        """The row count the planner expected, which every node here agrees on.

        For a spill there is one node and this is simply its estimate. For
        blindness the shared estimate is the finding: the grouping keys on it, so
        agreement is true by construction rather than by coincidence.
        """
        return self.nodes[0].estimated_rows

    @property
    def actual_rows(self) -> tuple[float | None, ...]:
        """What each execution actually produced at that node, in capture order.

        **Per loop like every other row count in this package**, which is worth
        saying here rather than leaving to be rediscovered. For
        :attr:`~django_query_contract.PlanDefect.PLANNER_BLIND` it makes no
        difference: those nodes are plan roots, a plan's root runs exactly once,
        and a node that ran once is its own total. A spill is reported on
        whichever node spilled, which can be the inner side of a join that ran
        thousands of times, and there each number here describes one of those
        executions -- :attr:`~django_query_contract.PlanNode.total_actual_rows`
        on the node beside it is the whole of what that read produced.

        ``float | None`` because that is what a node holds, and narrowing it here
        would be this class asserting something about how it was built.
        :func:`~django_query_contract.find_plan_defects` only ever makes a
        finding out of analyzed plans, so every entry is a real measurement --
        but this is a public record and a caller may hold one it built itself.
        """
        return tuple(node.actual_rows for node in self.nodes)
