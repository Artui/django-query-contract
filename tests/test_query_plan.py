"""One statement's plan, or the stated reason there is not one."""

from __future__ import annotations

import pytest

from django_query_contract import PlanNode, QueryPlan
from tests.plan_payloads import SPILLED_SORT, WHALE_JOIN


def test_a_plan_unwraps_the_list_postgres_returns() -> None:
    """The single-element list is PostgreSQL's shape, and one place reads it."""
    plan = QueryPlan.from_explain(WHALE_JOIN, analyzed=True)

    assert plan.root is not None
    assert plan.root.node_type == "Nested Loop"
    assert plan.analyzed is True
    assert plan.refusal is None


def test_the_nodes_of_a_plan_are_its_whole_tree() -> None:
    plan = QueryPlan.from_explain(WHALE_JOIN, analyzed=True)

    assert len(plan.nodes) == 4
    assert plan.nodes[0].node_type == "Nested Loop"


def test_a_refusal_is_a_value_and_not_an_absence() -> None:
    """ "Nobody asked" and "we declined" have to stay distinguishable.

    A record whose ``plan`` is ``None`` was never asked; a record whose plan has
    no root was asked and declined, and the sentence saying why is the difference
    between a report that can explain itself and one that cannot.
    """
    plan = QueryPlan.refused("executemany has no single plan.")

    assert plan.root is None
    assert plan.analyzed is False
    assert plan.refusal == "executemany has no single plan."
    assert plan.nodes == ()
    assert plan.worst_estimate is None


def test_the_worst_estimate_is_an_argmax_and_therefore_needs_no_threshold() -> None:
    plan = QueryPlan.from_explain(WHALE_JOIN, analyzed=True)

    worst = plan.worst_estimate

    assert worst is not None
    error, node = worst
    assert node.node_type == "Nested Loop"
    assert error == pytest.approx(20323 / 20)


def test_the_worst_estimate_prefers_the_earlier_node_on_a_tie() -> None:
    """Tree order, which is the order the plan was printed in.

    Ties are the ordinary case -- a plan of one node, or a chain that all agreed
    -- and any other tie-break would be a ranking this package has no basis for.
    """
    plan = QueryPlan.from_explain(
        [
            {
                "Plan": {
                    "Node Type": "Limit",
                    "Plan Rows": 5,
                    "Actual Rows": 10,
                    "Plans": [
                        {"Node Type": "Seq Scan", "Plan Rows": 5, "Actual Rows": 10},
                    ],
                }
            }
        ],
        analyzed=True,
    )

    worst = plan.worst_estimate

    assert worst is not None
    assert worst[1].node_type == "Limit"


def test_a_plan_with_no_measurements_has_no_worst_estimate() -> None:
    plan = QueryPlan.from_explain(
        [{"Plan": {"Node Type": "Seq Scan", "Plan Rows": 5}}], analyzed=False
    )

    assert plan.root is not None
    assert plan.worst_estimate is None


def test_a_plan_can_be_built_from_nodes_a_caller_holds() -> None:
    """It is a plain frozen record, and the parser is one way in rather than the way in."""
    node = PlanNode.from_explain(SPILLED_SORT[0]["Plan"])

    plan = QueryPlan(root=node, analyzed=True)

    assert plan.nodes[0].sort_space_type == "Disk"
    assert plan.refusal is None
