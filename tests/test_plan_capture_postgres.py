"""Plan capture against a real PostgreSQL, over a database shaped like a real one.

Everything else in this suite drives the plan code with payloads and stub
connections, which is what keeps the coverage gate on the portable matrix. That
leaves exactly one thing unproven: that any of it works against a server. This
module is that proof, and it runs only where there is one --
``QUERY_CONTRACT_TEST_DATABASE=postgres``.

**The world is built by ``django-data-shape`` rather than by a loop, and the
difference is the reason the milestone waited for it.** A uniform fan-out makes
the planner right by construction, because the average is the truth; the defect
this module reproduces is only visible when the fan-out has a head and a tail.
"""

from __future__ import annotations

import psycopg
import pytest
from django.db import DatabaseError, connection, connections

from tests.testapp.models import Customer, Order

pytestmark = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Plan capture is PostgreSQL-only; run with QUERY_CONTRACT_TEST_DATABASE=postgres.",
)

if connection.vendor == "postgresql":
    from django_data_shape import FanOut, Shape, Table, Uniform, Zipf
    from django_data_shape.fixtures import shape_fixture

    from django_query_contract import (
        PlanCapture,
        PlanDefect,
        find_plan_defects,
        format_query_plans,
    )

    # Small enough for a CI job and skewed enough for the planner to be wrong:
    # a Zipf fan-out over five thousand parents, a third of them childless. The
    # numbers are not a threshold anywhere in the package -- they are the size at
    # which the effect was still reproducible when this was written.
    world = shape_fixture(
        Shape(
            Table(Customer, rows=5_000, name=Uniform(1, 1_000_000)),
            Table(
                Order,
                rows=100_000,
                reference=Uniform(1, 1_000_000),
                customer=FanOut(Zipf(1.2), childless=0.35, placement="arrival"),
            ),
            seed=1234,
        )
    )


@pytest.fixture
def whale_and_tail(world, db):
    """The busiest customer and the quietest one, by the number of orders they own.

    Read out of the built world rather than assumed: the fan-out assigns range
    sizes across the parent keys it queried, so which parent is a whale is a
    property of the seed and not of the primary key.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT customer_id, count(*) FROM testapp_order GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
        )
        whale_id, whale_rows = cursor.fetchone()
        cursor.execute(
            "SELECT customer_id, count(*) FROM testapp_order GROUP BY 1 ORDER BY 2 ASC LIMIT 1"
        )
        tail_id, tail_rows = cursor.fetchone()
    assert whale_rows > tail_rows * 10, "the shaped world is not skewed enough to test with"
    return Customer.objects.get(pk=whale_id), Customer.objects.get(pk=tail_id)


def _join_through_the_parent(customer: Customer) -> int:
    """Count a customer's orders through a join on the parent, not on the foreign key.

    The predicate has to be on the *parent* table for this to matter. Filtering
    on ``customer_id`` directly lets the planner use the child column's own
    histogram and it gets the answer nearly right; joining makes the condition a
    column comparison, where all it has left is ``n_distinct``.
    """
    return len(
        list(Order.objects.filter(customer__name=customer.name).values_list("id", flat=True))
    )


def test_the_planner_gives_one_estimate_to_two_very_different_truths(whale_and_tail) -> None:
    """The finding this milestone exists for, reproduced end to end."""
    whale, tail = whale_and_tail

    with PlanCapture(using="default") as capture:
        whale_orders = _join_through_the_parent(whale)
        tail_orders = _join_through_the_parent(tail)

    findings = [
        finding
        for finding in find_plan_defects(capture)
        if finding.defect is PlanDefect.PLANNER_BLIND
    ]

    assert whale_orders > tail_orders * 10
    assert len(findings) == 1, format_query_plans(capture)
    finding = findings[0]
    assert finding.count == 2
    assert set(finding.actual_rows) == {float(whale_orders), float(tail_orders)}
    # The estimate is shared by construction: the grouping keys on it. What is
    # worth asserting is that the planner really was that far out, which is the
    # claim the whole milestone rests on.
    assert max(finding.actual_rows) > finding.estimated_rows * 10


def test_every_key_the_parser_reads_is_a_key_this_server_writes(whale_and_tail) -> None:
    """The payload tests elsewhere use a double, and this is what keeps it honest.

    A test double standing in for a wire format agrees with whatever the double
    says, which is how a parser can be green against a shape no server produces.
    So the fields the parser fills in from a real plan are checked here against a
    real plan, on a real server, rather than against the fixture.
    """
    whale, _ = whale_and_tail

    with PlanCapture(using="default") as capture:
        _join_through_the_parent(whale)

    plan = capture.records[-1].plan
    assert plan is not None and plan.root is not None and plan.analyzed
    nodes = plan.nodes
    assert any(node.relation == "testapp_order" for node in nodes)
    assert all(node.node_type for node in nodes)
    assert all(node.actual_rows is not None for node in nodes)
    assert all(node.loops is not None for node in nodes)
    assert all(node.shared_hit_blocks is not None for node in nodes)
    assert all(node.shared_read_blocks is not None for node in nodes)
    assert any(node.index is not None for node in nodes)


def test_a_spilled_sort_is_found(world, db) -> None:
    """``work_mem`` shrunk until PostgreSQL says the sort went to disk."""
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL work_mem = '64kB'")

    with PlanCapture(using="default") as capture:
        list(Order.objects.order_by("reference").values_list("id", flat=True))

    spills = [
        finding
        for finding in find_plan_defects(capture)
        if finding.defect is PlanDefect.SPILLED_TO_DISK
    ]
    assert spills, format_query_plans(capture)
    assert any(node.sort_space_type == "Disk" for finding in spills for node in finding.nodes)


def test_explain_is_invisible_to_the_count_assertion_it_composes_with(
    world, db, django_assert_num_queries
) -> None:
    """The one thing plan capture must not do: change what somebody else is counting.

    ``django_assert_num_queries`` counts through ``connection.queries_log``, and
    the plan is taken on the driver connection underneath Django's cursor, so
    neither the ``EXPLAIN`` nor the savepoints around it reach that log. Asserted
    rather than reasoned about, because the alternative -- ``connection.cursor()``
    -- would have been the obvious implementation and would have inflated every
    count in a suite that turned this on.
    """
    with PlanCapture(using="default") as capture, django_assert_num_queries(1):
        list(Order.objects.all()[:5])

    assert len(capture) == 1
    assert capture.records[0].plan is not None
    assert capture.records[0].plan.root is not None


def test_a_statement_postgres_cannot_explain_costs_a_plan_and_not_the_transaction(
    world, db
) -> None:
    """The savepoint is load bearing, and this is what it buys.

    Driven at the ``EXPLAIN`` rather than through a statement, because a
    statement PostgreSQL cannot explain is a statement it cannot run either --
    the user's own execution would poison the transaction before this package
    got a chance to. What has to be true is narrower and this is exactly it: an
    ``EXPLAIN`` that fails leaves the connection usable.
    """
    capture = PlanCapture(using="default")

    plan = capture._explain(connections["default"], "SELECT * FROM a_table_that_is_not_there", None)

    assert plan.root is None
    assert plan.refusal is not None
    assert "UndefinedTable" in plan.refusal
    # And the message is the class name only: a driver error can quote a bound
    # value, and this package retains none.
    assert "a_table_that_is_not_there" not in plan.refusal
    # The transaction survived, which is the whole point.
    assert Order.objects.count() == 100_000


def test_without_the_savepoint_that_same_failure_poisons_the_transaction(world, db) -> None:
    """The falsification of the test above, run rather than argued.

    The same ``EXPLAIN``, on the same connection, without the savepoint around
    it: the transaction is aborted and the next ordinary query fails. This test
    leaves its own transaction broken on purpose, which is fine because
    pytest-django rolls it back and a rollback is one of the two commands an
    aborted transaction still accepts.
    """
    cursor = connections["default"].connection.cursor()
    with pytest.raises(psycopg.errors.UndefinedTable):
        cursor.execute("EXPLAIN (FORMAT JSON) SELECT * FROM a_table_that_is_not_there")
    cursor.close()

    with pytest.raises(DatabaseError):
        Order.objects.count()


def test_a_table_nobody_analyzed_is_named_as_one(world, db) -> None:
    """The half of "never pass vacuously" that a vendor check cannot reach."""
    with connection.cursor() as cursor:
        cursor.execute("CREATE TEMPORARY TABLE unanalyzed_rows (id integer)")
        cursor.execute("INSERT INTO unanalyzed_rows SELECT generate_series(1, 1000)")

    with PlanCapture(using="default") as capture, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM unanalyzed_rows")
        cursor.fetchall()

    assert "unanalyzed_rows" in capture.unanalyzed_relations
    assert "never gathered statistics" in format_query_plans(capture)


def test_the_shaped_world_is_analyzed_and_says_so(world, db) -> None:
    """The other side of the same claim: a world this package's sibling built is not a guess."""
    with PlanCapture(using="default") as capture:
        list(Order.objects.all()[:5])

    assert capture.unanalyzed_relations == ()


def test_a_capture_over_a_connection_that_is_not_postgres_is_refused(db) -> None:
    """The refusal, driven through the real registry rather than through a stub.

    On this run ``default`` is PostgreSQL and ``other`` is SQLite, so the default
    ``PlanCapture()`` -- every configured connection -- has to refuse, and it has
    to name the connection it refused rather than the one it liked.
    """
    capture = PlanCapture()

    refusal = capture.refusal()

    assert refusal is not None
    assert "'other'" in refusal
    assert connections["other"].vendor == "sqlite"
