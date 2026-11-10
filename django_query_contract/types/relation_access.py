from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.types.plan_node import PlanNode
from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.stack_frame import StackFrame


@dataclass(frozen=True, slots=True)
class RelationAccess:
    """How one table was reached, by which statements, and from which lines."""

    relation: str
    """The table, under the name PostgreSQL printed in the plan."""

    records: tuple[QueryRecord, ...]
    """The executions that read it, in capture order. At least one."""

    nodes: tuple[PlanNode, ...]
    """The node in each of those plans that did the reading."""

    @property
    def count(self) -> int:
        """How many times this relation was read."""
        return len(self.nodes)

    @property
    def first_index(self) -> int:
        """Position in the capture of the first statement that read this relation."""
        return self.records[0].index

    @property
    def call_sites(self) -> tuple[StackFrame | None, ...]:
        """The distinct lines these reads came from, in the order first seen."""
        return tuple(dict.fromkeys(record.call_site for record in self.records))

    @property
    def indexes_used(self) -> tuple[str, ...]:
        """Every index PostgreSQL read this relation through, in the order first seen."""
        return tuple(dict.fromkeys(index for node in self.nodes for index in node.indexes_used))

    @property
    def unindexed_reads(self) -> tuple[PlanNode, ...]:
        """The reads that reached this table without an index, in plan order."""
        return tuple(node for node in self.nodes if not node.indexes_used)

    @property
    def conditions(self) -> tuple[str, ...]:
        """The distinct predicates applied to this relation, in the order first seen."""
        return tuple(
            dict.fromkeys(node.condition for node in self.nodes if node.condition is not None)
        )

    @property
    def most_rows_discarded(self) -> tuple[float, PlanNode] | None:
        """The most rows any one read of this table threw away, and which read."""
        scored = [
            (rows, node)
            for node in self.nodes
            if (rows := node.total_rows_removed_by_filter) is not None
        ]
        if not scored:
            return None
        return max(scored, key=lambda candidate: candidate[0])
