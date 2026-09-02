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
        format_relation_access,
        group_by_relation,
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


def test_a_captured_filter_never_carries_the_value_that_was_bound(world, db) -> None:
    """The rule this package states about itself, checked where it would break.

    ``EXPLAIN`` renders a predicate with the parameter substituted -- a real
    server writes ``Filter: ((reference)::text = '601980.6826913885'::text)``
    for a query bound with ``%s``. Every other part of this package retains no
    parameter, and the refusal sentence it prints when it declines to quote a
    driver error tells the reader as much. A plan node is the one place that
    promise could quietly stop being true, so it is checked against a server
    rather than against a payload somebody wrote down.
    """
    reference = Order.objects.values_list("reference", flat=True).first()
    assert reference

    with PlanCapture(using="default") as capture:
        list(Order.objects.filter(reference=reference).values_list("id", flat=True))

    conditions = [
        node.condition
        for record in capture.records
        if record.plan is not None
        for node in record.plan.nodes
        if node.condition is not None
    ]
    assert conditions, "the query did not produce a filter to check"
    assert any("reference" in condition for condition in conditions)
    assert all(reference not in condition for condition in conditions)
    # And the same has to hold of every rendering, not only of the record.
    assert reference not in format_query_plans(capture)
    assert reference not in format_relation_access(capture)


def test_the_indexes_a_relation_already_has_are_read_from_the_catalogue(world, db) -> None:
    """The only ``CREATE INDEX`` statements this package prints: the ones that exist."""
    with PlanCapture(using="default") as capture:
        list(Order.objects.filter(customer_id=1).values_list("id", flat=True))

    definitions = capture.relation_indexes["testapp_order"]

    assert any("testapp_order_pkey" in definition for definition in definitions)
    assert any("customer_id" in definition for definition in definitions)
    # PostgreSQL's own rendering, unedited, so an expression or partial index
    # needs nothing learned here.
    assert all(definition.startswith("CREATE ") for definition in definitions)
    assert "PostgreSQL has" in format_relation_access(capture)


def test_a_table_read_without_an_index_is_named_with_the_line_that_read_it(world, db) -> None:
    """Plans plus call sites, which is what the milestone asked for."""
    reference = Order.objects.values_list("reference", flat=True).first()

    with PlanCapture(using="default") as capture:
        list(Order.objects.filter(reference=reference).values_list("id", flat=True))

    (access,) = [found for found in group_by_relation(capture) if found.relation == "testapp_order"]
    worst = access.most_rows_discarded

    assert access.unindexed_reads
    assert worst is not None
    # 100,000 rows in the world, one of them matching: the server counted the rest.
    assert worst[0] > 99_000
    report = format_relation_access(capture)
    assert "testapp_order" in report
    assert "test_plan_capture_postgres.py" in report
    assert "No index is recommended" in report


def test_the_seq_scan_beside_an_index_scan_rule_would_have_named_a_useless_index(world, db) -> None:
    """Why one candidate for an index finding was declined, run rather than argued.

    The rule considered: a relation read sequentially by one statement while
    another statement in the same capture reaches it by index. That reads like a
    comparison between two measurements rather than a threshold, and it is not
    -- two statements filtering **different columns** of one table are not
    measuring one thing.

    Below, both halves of the rule hold on ``testapp_order`` and the conclusion
    is still wrong: the sequential read keeps every row it looks at, so it is
    the plan PostgreSQL should have chosen and there is no index that improves
    it. The index the rule would have pointed at is on the other statement's
    column.
    """
    with PlanCapture(using="default") as capture:
        list(Order.objects.filter(customer_id=1).values_list("id", flat=True))
        list(Order.objects.filter(reference__isnull=False).values_list("id", flat=True))

    (access,) = [found for found in group_by_relation(capture) if found.relation == "testapp_order"]

    # Both halves of the declined rule are true here.
    assert access.indexes_used
    assert access.unindexed_reads
    # And the read it accuses threw away nothing at all: it wanted the whole
    # table, and got it in one pass.
    assert all(node.rows_removed_by_filter in (None, 0.0) for node in access.unindexed_reads)
    assert any(node.actual_rows == 100_000 for node in access.unindexed_reads)


def test_the_rows_removed_rule_fires_the_same_way_on_five_rows_as_on_a_hundred_thousand(
    world, db
) -> None:
    """Why the other candidate was declined, on two tables three orders apart.

    ``Rows Removed by Filter`` is PostgreSQL's own count, which is what made it
    a candidate: the number is not one this package picked. The *verdict* is
    still one nobody supplied. A five-row table discards four rows in exactly
    the shape a hundred-thousand-row table discards 99,999 -- same node type,
    same key present, same everything a rule could read -- and only a magnitude
    separates them. A magnitude is the knob this package refuses.
    """
    with connection.cursor() as cursor:
        cursor.execute("CREATE TEMPORARY TABLE five_rows (id integer)")
        cursor.execute("INSERT INTO five_rows SELECT generate_series(1, 5)")
        cursor.execute("ANALYZE five_rows")
    reference = Order.objects.values_list("reference", flat=True).first()

    with PlanCapture(using="default") as capture, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM five_rows WHERE id > 4")
        cursor.fetchall()
        list(Order.objects.filter(reference=reference).values_list("id", flat=True))

    by_relation = {found.relation: found for found in group_by_relation(capture)}
    tiny = by_relation["five_rows"].most_rows_discarded
    large = by_relation["testapp_order"].most_rows_discarded

    assert tiny is not None and large is not None
    assert tiny[1].node_type == large[1].node_type == "Seq Scan"
    assert not by_relation["five_rows"].unindexed_reads[0].indexes_used
    assert not by_relation["testapp_order"].unindexed_reads[0].indexes_used
    # Indistinguishable but for the size, which is the whole finding.
    assert tiny[0] == 4.0
    assert large[0] > 99_000
