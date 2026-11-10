from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.types.plan_defect import PlanDefect
from django_query_contract.types.plan_node import PlanNode
from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.stack_frame import StackFrame


@dataclass(frozen=True, slots=True)
class PlanFinding:
    """A defect PostgreSQL's own output states, and the evidence for it."""

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
        """Position in the capture of the first execution involved."""
        return self.records[0].index

    @property
    def call_sites(self) -> tuple[StackFrame | None, ...]:
        """The distinct lines these executions came from, in the order first seen."""
        return tuple(dict.fromkeys(record.call_site for record in self.records))

    @property
    def estimated_rows(self) -> float:
        """The row count the planner expected, which every node here agrees on."""
        return self.nodes[0].estimated_rows

    @property
    def actual_rows(self) -> tuple[float | None, ...]:
        """What each execution actually produced at that node, in capture order."""
        return tuple(node.actual_rows for node in self.nodes)
