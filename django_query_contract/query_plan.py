"""What PostgreSQL said it would do with one statement, and what it then did."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django_query_contract.plan_node import PlanNode


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """One statement's execution plan, or the stated reason there is not one.

    Hangs off :attr:`~django_query_contract.QueryRecord.plan`, so a plan travels
    with the statement it belongs to and with the call stack that emitted it.
    That pairing is the whole point: an index recommendation is a plan plus an
    address, and a plan in a list of its own would have to be joined back to the
    statement by index before anything could be said about it.

    **A refusal is a value here, not an absence.** ``EXPLAIN ANALYZE`` executes
    the statement it is given, so this package runs it only on a statement that
    is known not to change anything, and there are several ordinary reasons a
    statement is skipped. Recording those as ``plan=None`` would make "nobody
    asked for plans" and "we declined to explain this one" the same observation,
    and a report could then only say nothing about either. So a skipped
    statement carries a plan whose :attr:`root` is ``None`` and whose
    :attr:`refusal` is the sentence saying why, and ``plan is None`` means one
    thing only: this capture was not a
    :class:`~django_query_contract.PlanCapture`.
    """

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
        """Build a plan from the JSON document ``EXPLAIN (FORMAT JSON)`` returns.

        That document is a list holding a single object, whose ``Plan`` key is
        the root node. The list is PostgreSQL's own shape and is unwrapped here
        rather than by the caller, so the one place that knows the wire format is
        the one place that reads it.
        """
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
        """How far out this plan's least accurate node was, and which node that is.

        An argmax rather than a cut-off, and that is deliberate: every measured
        plan has exactly one node the planner was most wrong about, so naming it
        introduces no number. Whether being wrong by that much matters is left to
        the reader, for the reasons
        :attr:`~django_query_contract.PlanNode.estimate_error` sets out.

        The factor comes back beside the node rather than being read off it
        again, so a caller cannot end up holding a node it has to re-test for a
        measurement this property already established it has.

        ``None`` for a refusal and for a plan taken without ``ANALYZE``, where
        there is no actual to be wrong about.
        """
        # ``max`` takes the first of a tie, and the tie-break is therefore tree
        # order: parents before children, which is the order the plan was
        # printed in. Ties are common -- a plan of one node, or a chain of nodes
        # that all agreed -- and any other tie-break would invent a ranking.
        scored = [
            (error, node) for node in self.nodes if (error := node.estimate_error) is not None
        ]
        if not scored:
            return None
        return max(scored, key=lambda candidate: candidate[0])
