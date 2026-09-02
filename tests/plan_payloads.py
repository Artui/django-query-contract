"""Real ``EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)`` output, kept verbatim.

Every payload here came off PostgreSQL 16.3, against a database built by
``django-data-shape`` -- 20,000 parents and 400,000 children on a Zipf fan-out,
loaded and analyzed -- and is checked in exactly as the server wrote it, keys
this package ignores included.

**A test double standing in for a wire format agrees with whatever the double
says**, which is how a parser stays green against a shape no server produces. Two
things keep these honest. They were not typed: they are the server's own JSON,
copied out. And ``tests/test_plan_capture_postgres.py`` asserts against a *live*
plan that every field the parser fills in is one a real server still writes, so a
key renamed upstream fails there rather than agreeing with itself here.

Regenerate by running the statement named above each payload under a server with
those options, and copying the result.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

WHALE_JOIN: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Nested Loop",
            "Parallel Aware": False,
            "Async Capable": False,
            "Join Type": "Inner",
            "Startup Cost": 4.76,
            "Total Cost": 561.08,
            "Plan Rows": 20,
            "Plan Width": 8,
            "Actual Rows": 20323,
            "Actual Loops": 1,
            "Inner Unique": False,
            "Shared Hit Blocks": 2,
            "Shared Read Blocks": 3498,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Parent Relationship": "Outer",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Relation Name": "testapp_author",
                    "Alias": "a",
                    "Startup Cost": 0.0,
                    "Total Cost": 398.0,
                    "Plan Rows": 1,
                    "Plan Width": 8,
                    "Actual Rows": 1,
                    "Actual Loops": 1,
                    "Filter": "((name)::text = '840211.9940649158'::text)",
                    "Rows Removed by Filter": 19999,
                    "Shared Hit Blocks": 0,
                    "Shared Read Blocks": 148,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 0,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 0,
                },
                {
                    "Node Type": "Bitmap Heap Scan",
                    "Parent Relationship": "Inner",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Relation Name": "testapp_book",
                    "Alias": "b",
                    "Startup Cost": 4.76,
                    "Total Cost": 162.65,
                    "Plan Rows": 43,
                    "Plan Width": 16,
                    "Actual Rows": 20323,
                    "Actual Loops": 1,
                    "Recheck Cond": "(author_id = a.id)",
                    "Rows Removed by Index Recheck": 0,
                    "Exact Heap Blocks": 3334,
                    "Lossy Heap Blocks": 0,
                    "Shared Hit Blocks": 2,
                    "Shared Read Blocks": 3350,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 0,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 0,
                    "Plans": [
                        {
                            "Node Type": "Bitmap Index Scan",
                            "Parent Relationship": "Outer",
                            "Parallel Aware": False,
                            "Async Capable": False,
                            "Index Name": "testapp_book_author_id_b4b7b7bf",
                            "Startup Cost": 0.0,
                            "Total Cost": 4.75,
                            "Plan Rows": 43,
                            "Plan Width": 0,
                            "Actual Rows": 20323,
                            "Actual Loops": 1,
                            "Index Cond": "(author_id = a.id)",
                            "Shared Hit Blocks": 2,
                            "Shared Read Blocks": 16,
                            "Shared Dirtied Blocks": 0,
                            "Shared Written Blocks": 0,
                            "Local Hit Blocks": 0,
                            "Local Read Blocks": 0,
                            "Local Dirtied Blocks": 0,
                            "Local Written Blocks": 0,
                            "Temp Read Blocks": 0,
                            "Temp Written Blocks": 0,
                        }
                    ],
                },
            ],
        },
        "Planning": {
            "Shared Hit Blocks": 216,
            "Shared Read Blocks": 49,
            "Shared Dirtied Blocks": 2,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 4.76,
        "Triggers": [],
        "Execution Time": 16.604,
    }
]
"""The join the planner cannot see across: estimated 20 rows, 20,323 arrived.

``SELECT b.id FROM child b INNER JOIN parent a ON (b.parent_id = a.id)
WHERE a.name = <a whale's name>`` -- the shape Django emits for
``Order.objects.filter(customer__name=...)``. The predicate is on the parent, so
the join condition is a column comparison and all the planner has left for it is
``n_distinct``."""

SPILLED_SORT: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Sort",
            "Parallel Aware": False,
            "Async Capable": False,
            "Startup Cost": 82845.28,
            "Total Cost": 83845.28,
            "Plan Rows": 400000,
            "Plan Width": 26,
            "Actual Rows": 400000,
            "Actual Loops": 1,
            "Sort Key": ["title"],
            "Sort Method": "external merge",
            "Sort Space Used": 14208,
            "Sort Space Type": "Disk",
            "Shared Hit Blocks": 3337,
            "Shared Read Blocks": 2,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 7087,
            "Temp Written Blocks": 7632,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Parent Relationship": "Outer",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Relation Name": "testapp_book",
                    "Alias": "testapp_book",
                    "Startup Cost": 0.0,
                    "Total Cost": 7336.0,
                    "Plan Rows": 400000,
                    "Plan Width": 26,
                    "Actual Rows": 400000,
                    "Actual Loops": 1,
                    "Shared Hit Blocks": 3334,
                    "Shared Read Blocks": 2,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 0,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 0,
                }
            ],
        },
        "Planning": {
            "Shared Hit Blocks": 119,
            "Shared Read Blocks": 1,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 0.373,
        "Triggers": [],
        "Execution Time": 2018.175,
    }
]
"""A sort that did not fit in a 64 kB ``work_mem``: ``Sort Space Type: Disk``.

``SELECT id FROM child ORDER BY title`` under ``SET work_mem = '64kB'``."""

SPILLED_HASH: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Hash Join",
            "Parallel Aware": False,
            "Async Capable": False,
            "Join Type": "Inner",
            "Startup Cost": 726.99,
            "Total Cost": 13100.21,
            "Plan Rows": 399980,
            "Plan Width": 8,
            "Actual Rows": 399990,
            "Actual Loops": 1,
            "Inner Unique": True,
            "Hash Cond": "(b.author_id = a.id)",
            "Shared Hit Blocks": 3336,
            "Shared Read Blocks": 148,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 1380,
            "Temp Written Blocks": 1380,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Parent Relationship": "Outer",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Relation Name": "testapp_book",
                    "Alias": "b",
                    "Startup Cost": 0.0,
                    "Total Cost": 7336.0,
                    "Plan Rows": 400000,
                    "Plan Width": 16,
                    "Actual Rows": 400000,
                    "Actual Loops": 1,
                    "Shared Hit Blocks": 3336,
                    "Shared Read Blocks": 0,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 0,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 0,
                },
                {
                    "Node Type": "Hash",
                    "Parent Relationship": "Inner",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Startup Cost": 398.0,
                    "Total Cost": 398.0,
                    "Plan Rows": 19999,
                    "Plan Width": 8,
                    "Actual Rows": 19999,
                    "Actual Loops": 1,
                    "Hash Buckets": 4096,
                    "Original Hash Buckets": 4096,
                    "Hash Batches": 16,
                    "Original Hash Batches": 16,
                    "Peak Memory Usage": 84,
                    "Shared Hit Blocks": 0,
                    "Shared Read Blocks": 148,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 0,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 60,
                    "Plans": [
                        {
                            "Node Type": "Seq Scan",
                            "Parent Relationship": "Outer",
                            "Parallel Aware": False,
                            "Async Capable": False,
                            "Relation Name": "testapp_author",
                            "Alias": "a",
                            "Startup Cost": 0.0,
                            "Total Cost": 398.0,
                            "Plan Rows": 19999,
                            "Plan Width": 8,
                            "Actual Rows": 19999,
                            "Actual Loops": 1,
                            "Filter": "(id < 20000)",
                            "Rows Removed by Filter": 1,
                            "Shared Hit Blocks": 0,
                            "Shared Read Blocks": 148,
                            "Shared Dirtied Blocks": 0,
                            "Shared Written Blocks": 0,
                            "Local Hit Blocks": 0,
                            "Local Read Blocks": 0,
                            "Local Dirtied Blocks": 0,
                            "Local Written Blocks": 0,
                            "Temp Read Blocks": 0,
                            "Temp Written Blocks": 0,
                        }
                    ],
                },
            ],
        },
        "Planning": {
            "Shared Hit Blocks": 137,
            "Shared Read Blocks": 16,
            "Shared Dirtied Blocks": 1,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 2.22,
        "Triggers": [],
        "Execution Time": 80.106,
    }
]
"""A hash join in sixteen batches, which is PostgreSQL saying the hash spilled.

``SELECT b.id FROM child b JOIN parent a ON a.id = b.parent_id WHERE a.id < 20000``
under ``SET work_mem = '64kB'``."""


def tail_join() -> list[dict[str, Any]]:
    """``WHALE_JOIN`` with the row counts a tail parent actually produced.

    Derived rather than captured, and derived in code so the difference is
    visible: a second real capture would differ in buffer counts and costs as
    well, and this pair exists to show that **one** number moved while the
    estimate did not. The live pair, differing in everything, is asserted in
    ``tests/test_plan_capture_postgres.py``.

    A function rather than a constant because the payloads here are mutable and a
    module-level copy would be shared between the tests that read it.
    """
    payload = deepcopy(WHALE_JOIN)
    payload[0]["Plan"]["Actual Rows"] = 6
    payload[0]["Plan"]["Plans"][1]["Actual Rows"] = 6
    payload[0]["Plan"]["Plans"][1]["Plans"][0]["Actual Rows"] = 6
    return payload


UNINDEXED_SCAN: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Seq Scan",
            "Parallel Aware": False,
            "Async Capable": False,
            "Relation Name": "testapp_order",
            "Alias": "testapp_order",
            "Startup Cost": 0.0,
            "Total Cost": 2090.0,
            "Plan Rows": 1,
            "Plan Width": 8,
            "Actual Rows": 1,
            "Actual Loops": 1,
            "Filter": "((reference)::text = '601980.6826913885'::text)",
            "Rows Removed by Filter": 99999,
            "Shared Hit Blocks": 840,
            "Shared Read Blocks": 0,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning": {
            "Shared Hit Blocks": 3,
            "Shared Read Blocks": 0,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 0.015,
        "Triggers": [],
        "Execution Time": 5.37,
    }
]
"""A table read end to end because nothing indexes the column being filtered.

``SELECT id FROM testapp_order WHERE reference = <a reference>`` -- one row kept,
99,999 discarded, and PostgreSQL is the one that counted them.

Kept here because it is the payload the index-advice question was decided on,
and the decision was to decline. The server supplies the number of rows it threw
away; it does not supply the verdict that throwing them away was wrong. The
identically shaped plan over a five-row table discards four, and only a magnitude
separates the two. See :class:`~django_query_contract.RelationAccess`.

Note also what the ``Filter`` carries: the bound value, spelled out. That is why
:attr:`~django_query_contract.PlanNode.condition` normalises it away.
"""

BITMAP_AND: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Bitmap Heap Scan",
            "Parallel Aware": False,
            "Async Capable": False,
            "Relation Name": "testapp_order",
            "Alias": "testapp_order",
            "Startup Cost": 24.24,
            "Total Cost": 64.68,
            "Plan Rows": 11,
            "Plan Width": 8,
            "Actual Rows": 10,
            "Actual Loops": 1,
            "Recheck Cond": "((mod(id, '100'::bigint) = 5) AND (mod(id, '97'::bigint) = 3))",
            "Rows Removed by Index Recheck": 0,
            "Exact Heap Blocks": 10,
            "Lossy Heap Blocks": 0,
            "Shared Hit Blocks": 13,
            "Shared Read Blocks": 6,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
            "Plans": [
                {
                    "Node Type": "BitmapAnd",
                    "Parent Relationship": "Outer",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Startup Cost": 24.24,
                    "Total Cost": 24.24,
                    "Plan Rows": 11,
                    "Plan Width": 0,
                    "Actual Rows": 0,
                    "Actual Loops": 1,
                    "Shared Hit Blocks": 3,
                    "Shared Read Blocks": 6,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 0,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 0,
                    "Plans": [
                        {
                            "Node Type": "Bitmap Index Scan",
                            "Parent Relationship": "Member",
                            "Parallel Aware": False,
                            "Async Capable": False,
                            "Index Name": "dump_mod_100",
                            "Startup Cost": 0.0,
                            "Total Cost": 11.52,
                            "Plan Rows": 963,
                            "Plan Width": 0,
                            "Actual Rows": 1000,
                            "Actual Loops": 1,
                            "Index Cond": "(mod(id, '100'::bigint) = 5)",
                            "Shared Hit Blocks": 3,
                            "Shared Read Blocks": 3,
                            "Shared Dirtied Blocks": 0,
                            "Shared Written Blocks": 0,
                            "Local Hit Blocks": 0,
                            "Local Read Blocks": 0,
                            "Local Dirtied Blocks": 0,
                            "Local Written Blocks": 0,
                            "Temp Read Blocks": 0,
                            "Temp Written Blocks": 0,
                        },
                        {
                            "Node Type": "Bitmap Index Scan",
                            "Parent Relationship": "Member",
                            "Parallel Aware": False,
                            "Async Capable": False,
                            "Index Name": "dump_mod_97",
                            "Startup Cost": 0.0,
                            "Total Cost": 12.47,
                            "Plan Rows": 1090,
                            "Plan Width": 0,
                            "Actual Rows": 1031,
                            "Actual Loops": 1,
                            "Index Cond": "(mod(id, '97'::bigint) = 3)",
                            "Shared Hit Blocks": 0,
                            "Shared Read Blocks": 3,
                            "Shared Dirtied Blocks": 0,
                            "Shared Written Blocks": 0,
                            "Local Hit Blocks": 0,
                            "Local Read Blocks": 0,
                            "Local Dirtied Blocks": 0,
                            "Local Written Blocks": 0,
                            "Temp Read Blocks": 0,
                            "Temp Written Blocks": 0,
                        },
                    ],
                }
            ],
        },
        "Planning": {
            "Shared Hit Blocks": 18,
            "Shared Read Blocks": 2,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 0.077,
        "Triggers": [],
        "Execution Time": 0.188,
    }
]
"""Two indexes combined, so the index that read the table is two levels down.

``SELECT id FROM testapp_order WHERE mod(id, 100) = 5 AND mod(id, 97) = 3``,
after ``CREATE INDEX ... ON testapp_order (mod(id, 100))`` and the same on
``mod(id, 97)``, under ``SET LOCAL enable_indexscan = off``,
``enable_indexonlyscan = off`` and ``enable_seqscan = off`` -- the settings that
make the planner prefer a combination it would otherwise cost out.

**The shape that makes
:attr:`~django_query_contract.PlanNode.indexes_used` walk rather than look.**
The node naming the relation is the ``Bitmap Heap Scan`` and it carries no
``Index Name`` at all; the two indexes are under a ``BitmapAnd`` beneath it. A
reading that looked only at the node itself, or only at its direct children,
would report this table as read without an index -- which is the one thing the
report must never say about a read PostgreSQL performed through two.
"""
