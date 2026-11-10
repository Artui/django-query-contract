from __future__ import annotations

from copy import deepcopy

import pytest

from django_query_contract import PlanNode
from tests.plan_payloads import (
    BITMAP_AND,
    NESTED_LOOP_INNER,
    PARALLEL_SCAN,
    SERIAL_SCAN,
    SPILLED_HASH,
    SPILLED_SORT,
    UNINDEXED_SCAN,
    WHALE_JOIN,
)


def _root(payload: list[dict[str, object]]) -> PlanNode:
    return PlanNode.from_explain(payload[0]["Plan"])


def test_a_node_carries_what_the_planner_said_and_what_happened() -> None:
    root = _root(WHALE_JOIN)

    assert root.node_type == "Nested Loop"
    assert root.estimated_rows == 20.0
    assert root.actual_rows == 20323.0
    assert root.loops == 1.0
    assert root.shared_hit_blocks == 2
    assert root.shared_read_blocks == 3498
    assert root.relation is None
    assert root.index is None


def test_a_scan_carries_its_relation_its_filter_and_what_the_filter_threw_away() -> None:
    """The three things index advice is made of, which is why they are kept."""
    scan = _root(WHALE_JOIN).children[0]

    assert scan.node_type == "Seq Scan"
    assert scan.relation == "testapp_author"
    assert scan.condition == "((name)::text = %s::text)"
    assert scan.rows_removed_by_filter == 19999.0


def test_an_index_node_names_its_index() -> None:
    index_scan = _root(WHALE_JOIN).children[1].children[0]

    assert index_scan.node_type == "Bitmap Index Scan"
    assert index_scan.index == "testapp_book_author_id_b4b7b7bf"


def test_walk_yields_the_whole_tree_parents_before_children() -> None:
    root = _root(WHALE_JOIN)

    assert [node.node_type for node in root.walk()] == [
        "Nested Loop",
        "Seq Scan",
        "Bitmap Heap Scan",
        "Bitmap Index Scan",
    ]


def test_a_plan_taken_without_analyze_has_no_measurements_and_says_so() -> None:
    """Every ``Actual`` key is absent without ANALYZE, and absent is not zero."""
    node = PlanNode.from_explain({"Node Type": "Seq Scan", "Plan Rows": 100})

    assert node.estimated_rows == 100.0
    assert node.actual_rows is None
    assert node.loops is None
    assert node.estimate_error is None
    assert node.spilled_to_disk is False
    assert node.children == ()


def test_a_node_with_no_type_is_parsed_rather_than_refused() -> None:
    """The one key with a default that could hide a parser bug, pinned deliberately."""
    node = PlanNode.from_explain({"Plan Rows": 1})

    assert node.node_type == ""


def test_a_plan_row_count_is_required_because_an_estimate_is_what_a_plan_is() -> None:
    with pytest.raises(KeyError):
        PlanNode.from_explain({"Node Type": "Seq Scan"})


def test_a_sort_that_went_to_disk_says_so_in_postgres_own_words() -> None:
    sort = _root(SPILLED_SORT)

    assert sort.node_type == "Sort"
    assert sort.sort_method == "external merge"
    assert sort.sort_space_type == "Disk"
    assert sort.sort_space_used_kb == 14208.0
    assert sort.spilled_to_disk is True


def test_a_sort_that_stayed_in_memory_is_not_a_spill() -> None:
    node = PlanNode.from_explain(
        {
            "Node Type": "Sort",
            "Plan Rows": 10,
            "Sort Method": "quicksort",
            "Sort Space Type": "Memory",
            "Sort Space Used": 25,
        }
    )

    assert node.spilled_to_disk is False


def test_a_hash_in_more_than_one_batch_is_a_spill() -> None:
    hashed = [node for node in _root(SPILLED_HASH).walk() if node.node_type == "Hash"]

    assert len(hashed) == 1
    assert hashed[0].hash_batches == 16
    assert hashed[0].spilled_to_disk is True


def test_a_hash_in_one_batch_is_not() -> None:
    node = PlanNode.from_explain({"Node Type": "Hash", "Plan Rows": 10, "Hash Batches": 1})

    assert node.spilled_to_disk is False


def test_a_hash_aggregate_spells_the_same_fact_two_other_ways() -> None:
    """``HashAgg Batches`` and ``Disk Usage``, which is how a hash aggregate reports it."""
    node = PlanNode.from_explain(
        {
            "Node Type": "Aggregate",
            "Strategy": "Hashed",
            "Plan Rows": 400000,
            "HashAgg Batches": 1365,
            "Disk Usage": 16880,
        }
    )

    assert node.hash_batches == 1365
    assert node.disk_usage_kb == 16880.0
    assert node.spilled_to_disk is True


def test_a_hash_aggregate_that_used_no_disk_is_not_a_spill() -> None:
    node = PlanNode.from_explain(
        {"Node Type": "Aggregate", "Plan Rows": 10, "HashAgg Batches": 1, "Disk Usage": 0}
    )

    assert node.spilled_to_disk is False


def test_the_estimate_error_is_the_factor_and_nothing_else() -> None:
    """1,016 times out, which is the number the milestone was built to print."""
    root = _root(WHALE_JOIN)

    assert root.estimate_error == pytest.approx(20323 / 20)


def test_an_over_estimate_counts_as_much_as_an_under_estimate() -> None:
    """Unsigned, because both numbers are on the record and the report prints both."""
    node = PlanNode.from_explain({"Node Type": "Seq Scan", "Plan Rows": 1000, "Actual Rows": 10})

    assert node.estimate_error == 100.0


def test_a_node_the_planner_got_right_scores_one() -> None:
    node = PlanNode.from_explain({"Node Type": "Seq Scan", "Plan Rows": 50, "Actual Rows": 50})

    assert node.estimate_error == 1.0


def test_no_rows_at_all_is_compared_against_the_planners_own_floor() -> None:
    """PostgreSQL never estimates below one row, so one is the floor a ratio uses."""
    node = PlanNode.from_explain({"Node Type": "Seq Scan", "Plan Rows": 900, "Actual Rows": 0})

    assert node.estimate_error == 900.0


def test_a_condition_keeps_the_shape_of_the_filter_and_none_of_its_values() -> None:
    """The package retains no parameters, and a rendered Filter is where one hides."""
    scan = _root(UNINDEXED_SCAN)

    assert scan.condition == "((reference)::text = %s::text)"
    assert "601980.6826913885" not in str(scan.condition)


def test_two_executions_that_differed_only_in_a_value_carry_one_condition() -> None:
    """The consequence that makes the predicate groupable at all."""
    shipped = deepcopy(UNINDEXED_SCAN)
    shipped[0]["Plan"]["Filter"] = "((status)::text = 'shipped'::text)"
    pending = deepcopy(UNINDEXED_SCAN)
    pending[0]["Plan"]["Filter"] = "((status)::text = 'pending'::text)"

    assert _root(shipped).condition == _root(pending).condition


def test_a_node_with_no_filter_has_no_condition_rather_than_an_empty_one() -> None:
    assert _root(SPILLED_SORT).condition is None


def test_a_sequential_scan_used_no_index_and_says_so_with_an_empty_tuple() -> None:
    assert _root(UNINDEXED_SCAN).indexes_used == ()


def test_a_node_that_read_its_relation_through_an_index_names_that_index() -> None:
    """The index is on a child node, and the relation is on the parent."""
    heap = _root(WHALE_JOIN).children[1]

    assert heap.node_type == "Bitmap Heap Scan"
    assert heap.relation == "testapp_book"
    assert heap.index is None
    assert heap.indexes_used == ("testapp_book_author_id_b4b7b7bf",)


def test_an_index_two_levels_down_is_still_the_index_that_read_the_table() -> None:
    """A ``BitmapAnd`` puts another node between the table and its indexes."""
    root = _root(BITMAP_AND)

    assert root.relation == "testapp_order"
    assert root.indexes_used == ("dump_mod_100", "dump_mod_97")


def test_a_join_does_not_borrow_the_indexes_of_the_relations_beneath_it() -> None:
    """The walk stops at the next node that names a relation: that is a different read."""
    root = _root(WHALE_JOIN)

    assert root.node_type == "Nested Loop"
    assert root.relation is None
    assert root.indexes_used == ()


def _only(
    payload: list[dict[str, object]], node_type: str, *, parallel: bool | None = None
) -> PlanNode:
    """The single node of a kind in a payload, so a test names a shape not a path."""
    found = [
        node
        for node in _root(payload).walk()
        if node.node_type == node_type and (parallel is None or node.parallel_aware is parallel)
    ]
    assert len(found) == 1, f"{node_type} appears {len(found)} times"
    return found[0]


def test_a_scan_under_a_gather_reports_one_workers_share_of_every_count() -> None:
    """The finding this milestone came from, in the numbers a real server wrote."""
    scan = _only(PARALLEL_SCAN, "Seq Scan")

    assert scan.parallel_aware is True
    assert scan.loops == 3.0
    assert scan.actual_rows == 25301.0
    assert scan.rows_removed_by_filter == 374699.0


def test_the_total_is_the_per_loop_number_multiplied_by_the_loops() -> None:
    """The arithmetic, and it is arithmetic rather than a judgement."""
    scan = _only(PARALLEL_SCAN, "Seq Scan")

    assert scan.total_actual_rows == 75903.0
    assert scan.total_rows_removed_by_filter == 1124097.0
    serial = _only(SERIAL_SCAN, "Seq Scan")
    assert serial.actual_rows == 75902.0
    assert serial.rows_removed_by_filter == 1124098.0
    assert abs(scan.total_actual_rows - serial.actual_rows) <= scan.loops / 2
    assert abs(scan.total_rows_removed_by_filter - serial.rows_removed_by_filter) <= scan.loops / 2


def test_the_same_statement_in_one_process_totals_to_itself() -> None:
    """A node that ran once is its own total, which is why the old readings held."""
    serial = _only(SERIAL_SCAN, "Seq Scan")

    assert serial.parallel_aware is False
    assert serial.loops == 1.0
    assert serial.total_actual_rows == serial.actual_rows
    assert serial.total_rows_removed_by_filter == serial.rows_removed_by_filter


def test_the_inner_side_of_a_nested_loop_totals_to_what_the_join_produced() -> None:
    """The other way a node runs more than once, and the same multiplication."""
    root = _root(NESTED_LOOP_INNER)
    inner = _only(NESTED_LOOP_INNER, "Index Scan")

    assert inner.loops == 1260.0
    assert inner.actual_rows == 60.0
    assert inner.total_actual_rows == 75600.0
    assert root.actual_rows == 75600.0


def test_the_estimate_is_not_totalled_and_the_nested_loop_says_why() -> None:
    """The refusal, checked against the payload that would have made it look right."""
    root = _root(NESTED_LOOP_INNER)
    inner = _only(NESTED_LOOP_INNER, "Index Scan")

    assert not hasattr(inner, "total_estimated_rows")
    assert inner.estimated_rows * inner.loops == root.actual_rows == 75600.0
    assert root.estimated_rows == 400020.0


def test_a_parallel_estimate_is_divided_by_a_number_the_plan_never_prints() -> None:
    """The second half of the refusal, and the half that has no honest repair."""
    parallel = _only(PARALLEL_SCAN, "Seq Scan")
    serial = _only(SERIAL_SCAN, "Seq Scan")

    assert parallel.estimated_rows * parallel.loops == 500001.0
    assert serial.estimated_rows == 400000.0
    assert serial.estimated_rows / parallel.estimated_rows == pytest.approx(2.4, abs=0.001)


def test_a_plan_taken_without_analyze_has_no_totals_either() -> None:
    """No loops means no multiplication, and a total of ``None`` rather than of one."""
    node = PlanNode.from_explain({"Node Type": "Seq Scan", "Plan Rows": 100})

    assert node.loops is None
    assert node.total_actual_rows is None
    assert node.total_rows_removed_by_filter is None
    assert node.parallel_aware is False


def test_a_node_that_never_filtered_has_no_discarded_total() -> None:
    """``Rows Removed by Filter`` is emitted only where a filter ran, and absent is not zero."""
    node = PlanNode.from_explain(
        {"Node Type": "Seq Scan", "Plan Rows": 100, "Actual Rows": 100, "Actual Loops": 4}
    )

    assert node.rows_removed_by_filter is None
    assert node.total_rows_removed_by_filter is None
    assert node.total_actual_rows == 400.0


def test_a_measurement_with_no_loop_count_is_not_multiplied_by_a_guess() -> None:
    """A hand-built record can hold one without the other, and one is not the default."""
    node = PlanNode.from_explain(
        {"Node Type": "Seq Scan", "Plan Rows": 10, "Actual Rows": 10, "Rows Removed by Filter": 3}
    )

    assert node.loops is None
    assert node.total_actual_rows is None
    assert node.total_rows_removed_by_filter is None
