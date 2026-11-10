from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django_query_contract.types.plan_node import PlanNode


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """One statement's execution plan, or the stated reason there is not one."""

    root: PlanNode | None
    """The top of the plan tree. ``None`` when ``refusal`` says why there is none."""

    analyzed: bool
    """Whether the plan carries measurements or only the planner's expectations.

    ``False`` means ``EXPLAIN`` ran without ``ANALYZE``: the shape of the plan is
    real, every ``actual_rows`` is ``None``, and no finding in this package can
    be made from it. That is reported rather than left to be inferred from a
    tree of ``None``s, because a plan with nothing to check against is exactly
    the shape a vacuous pass would take.
    """

    refusal: str | None = None
    """Why this statement was not explained, in a sentence. ``None`` when it was."""

    @classmethod
    def from_explain(cls, payload: Sequence[Any], *, analyzed: bool) -> QueryPlan:
        """Build a plan from the JSON document ``EXPLAIN (FORMAT JSON)`` returns."""
        return cls(root=PlanNode.from_explain(payload[0]["Plan"]), analyzed=analyzed)

    @classmethod
    def refused(cls, reason: str) -> QueryPlan:
        """A plan that was not taken, carrying the reason it was not."""
        return cls(root=None, analyzed=False, refusal=reason)

    @property
    def nodes(self) -> tuple[PlanNode, ...]:
        """Every node in the tree, parents before children. Empty for a refusal."""
        return () if self.root is None else tuple(self.root.walk())

    @property
    def worst_estimate(self) -> tuple[float, PlanNode] | None:
        """How far out this plan's least accurate node was, and which node that is."""
        scored = [
            (error, node) for node in self.nodes if (error := node.estimate_error) is not None
        ]
        if not scored:
            return None
        return max(scored, key=lambda candidate: candidate[0])
