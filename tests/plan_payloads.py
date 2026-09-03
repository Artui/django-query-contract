"""Real ``EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)`` output, kept verbatim.

Every payload here came off PostgreSQL 16.3 and is checked in exactly as the
server wrote it, keys this package ignores included. Most were taken against a
database built by ``django-data-shape`` -- 20,000 parents and 400,000 children on
a Zipf fan-out, loaded and analyzed. The ones that carry more than one loop per
node needed a table big enough for PostgreSQL to reach for several processes, and
that world is not big enough, so they were taken against 1,200,000 rows over
20,000 parents under the same column names; the statement and any settings are
named above each.

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

SERIAL_SCAN: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Aggregate",
            "Strategy": "Plain",
            "Partial Mode": "Simple",
            "Parallel Aware": False,
            "Async Capable": False,
            "Startup Cost": 26644.0,
            "Total Cost": 26644.01,
            "Plan Rows": 1,
            "Plan Width": 8,
            "Actual Rows": 1,
            "Actual Loops": 1,
            "Shared Hit Blocks": 96,
            "Shared Read Blocks": 7548,
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
                    "Relation Name": "testapp_order",
                    "Alias": "testapp_order",
                    "Startup Cost": 0.0,
                    "Total Cost": 25644.0,
                    "Plan Rows": 400000,
                    "Plan Width": 0,
                    "Actual Rows": 75902,
                    "Actual Loops": 1,
                    "Filter": "(md5((reference)::text) < '1'::text)",
                    "Rows Removed by Filter": 1124098,
                    "Shared Hit Blocks": 96,
                    "Shared Read Blocks": 7548,
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
            "Shared Hit Blocks": 62,
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
        "Planning Time": 0.167,
        "Triggers": [],
        "Execution Time": 927.453,
    }
]
"""The same statement over the same rows, with parallelism switched off.

``SELECT COUNT(*) FROM testapp_order WHERE md5(reference) < %s`` over 1,200,000
rows, under ``SET max_parallel_workers_per_gather = 0``. Nothing else differs
from :data:`PARALLEL_SCAN` -- same server, same table, same predicate, same data,
same 75,902 rows matched and 1,124,098 discarded. ``md5()`` is there so the
planner has to guess: it expects 400,000 and is 5.3 times out, which is a real
mistake rather than an artefact and is what makes the pair worth comparing.

**The pair is the milestone in four numbers.** This node says
``Rows Removed by Filter: 1124098`` and ``Actual Rows: 75902``; the same read in
:data:`PARALLEL_SCAN` says 374,699 and 25,301, because three processes each did a
third of it. An assertion written against the numbers here is written against
numbers that plan does not report, and nothing announces the change -- which is
why :attr:`~django_query_contract.PlanNode.total_rows_removed_by_filter` exists.
"""

PARALLEL_SCAN: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Aggregate",
            "Strategy": "Plain",
            "Partial Mode": "Finalize",
            "Parallel Aware": False,
            "Async Capable": False,
            "Startup Cost": 16560.88,
            "Total Cost": 16560.89,
            "Plan Rows": 1,
            "Plan Width": 8,
            "Actual Rows": 1,
            "Actual Loops": 1,
            "Shared Hit Blocks": 0,
            "Shared Read Blocks": 7644,
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
                    "Node Type": "Gather",
                    "Parent Relationship": "Outer",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Startup Cost": 16560.67,
                    "Total Cost": 16560.88,
                    "Plan Rows": 2,
                    "Plan Width": 8,
                    "Actual Rows": 3,
                    "Actual Loops": 1,
                    "Workers Planned": 2,
                    "Workers Launched": 2,
                    "Single Copy": False,
                    "Shared Hit Blocks": 0,
                    "Shared Read Blocks": 7644,
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
                            "Node Type": "Aggregate",
                            "Strategy": "Plain",
                            "Partial Mode": "Partial",
                            "Parent Relationship": "Outer",
                            "Parallel Aware": False,
                            "Async Capable": False,
                            "Startup Cost": 15560.67,
                            "Total Cost": 15560.68,
                            "Plan Rows": 1,
                            "Plan Width": 8,
                            "Actual Rows": 1,
                            "Actual Loops": 3,
                            "Shared Hit Blocks": 0,
                            "Shared Read Blocks": 7644,
                            "Shared Dirtied Blocks": 0,
                            "Shared Written Blocks": 0,
                            "Local Hit Blocks": 0,
                            "Local Read Blocks": 0,
                            "Local Dirtied Blocks": 0,
                            "Local Written Blocks": 0,
                            "Temp Read Blocks": 0,
                            "Temp Written Blocks": 0,
                            "Workers": [],
                            "Plans": [
                                {
                                    "Node Type": "Seq Scan",
                                    "Parent Relationship": "Outer",
                                    "Parallel Aware": True,
                                    "Async Capable": False,
                                    "Relation Name": "testapp_order",
                                    "Alias": "testapp_order",
                                    "Startup Cost": 0.0,
                                    "Total Cost": 15144.0,
                                    "Plan Rows": 166667,
                                    "Plan Width": 0,
                                    "Actual Rows": 25301,
                                    "Actual Loops": 3,
                                    "Filter": "(md5((reference)::text) < '1'::text)",
                                    "Rows Removed by Filter": 374699,
                                    "Shared Hit Blocks": 0,
                                    "Shared Read Blocks": 7644,
                                    "Shared Dirtied Blocks": 0,
                                    "Shared Written Blocks": 0,
                                    "Local Hit Blocks": 0,
                                    "Local Read Blocks": 0,
                                    "Local Dirtied Blocks": 0,
                                    "Local Written Blocks": 0,
                                    "Temp Read Blocks": 0,
                                    "Temp Written Blocks": 0,
                                    "Workers": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        "Planning": {
            "Shared Hit Blocks": 55,
            "Shared Read Blocks": 10,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 0.323,
        "Triggers": [],
        "Execution Time": 340.88,
    }
]
"""The same scan under a ``Gather``: every number on it is one worker's share.

``SELECT COUNT(*) FROM testapp_order WHERE md5(reference) < %s`` over 1,200,000
rows, with no planner settings touched at all -- PostgreSQL reaches for three
processes on a table that size on its own, which is exactly why an assertion
written against a small world stops meaning what it did. :data:`SERIAL_SCAN` is
the identical statement with parallelism switched off.

**The payload the whole per-loop question was decided on**, and it answers it
three ways at once.

- ``Rows Removed by Filter`` is **374,699** where 1,124,098 rows were really
  discarded, and ``Actual Rows`` is **25,301** where 75,902 really matched. Both
  are the truth divided by ``Actual Loops``, which is 3: two workers and the
  leader.
- Multiplying them back gives 1,124,097 and 75,903 -- **each off by one**,
  because PostgreSQL rounds the average before printing it. That is the residue
  :attr:`~django_query_contract.PlanNode.total_actual_rows` documents, and it is
  bounded by half a loop.
- ``Plan Rows`` is **166,667** against the serial plan's **400,000**, and
  400,000 / 166,667 is **2.4** -- two workers plus the 0.4 the planner credits
  the leader with. Multiplying by 3 instead gives 500,001, which is not a number
  anybody predicted. The consequence is measurable on
  :attr:`~django_query_contract.PlanNode.estimate_error`: the planner was 5.3
  times out and this node reports **6.6**, because its estimate was divided by
  2.4 and its measurement by 3.
"""

NESTED_LOOP_INNER: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Nested Loop",
            "Parallel Aware": False,
            "Async Capable": False,
            "Join Type": "Inner",
            "Startup Cost": 0.43,
            "Total Cost": 48853.6,
            "Plan Rows": 400020,
            "Plan Width": 8,
            "Actual Rows": 75600,
            "Actual Loops": 1,
            "Inner Unique": False,
            "Shared Hit Blocks": 70990,
            "Shared Read Blocks": 8499,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 37,
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
                    "Relation Name": "testapp_customer",
                    "Alias": "testapp_customer",
                    "Startup Cost": 0.0,
                    "Total Cost": 409.0,
                    "Plan Rows": 6667,
                    "Plan Width": 8,
                    "Actual Rows": 1260,
                    "Actual Loops": 1,
                    "Filter": "(md5((name)::text) < '1'::text)",
                    "Rows Removed by Filter": 18740,
                    "Shared Hit Blocks": 0,
                    "Shared Read Blocks": 109,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 1,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 0,
                },
                {
                    "Node Type": "Index Scan",
                    "Parent Relationship": "Inner",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Scan Direction": "Forward",
                    "Index Name": "testapp_order_customer_id_idx",
                    "Relation Name": "testapp_order",
                    "Alias": "testapp_order",
                    "Startup Cost": 0.43,
                    "Total Cost": 6.67,
                    "Plan Rows": 60,
                    "Plan Width": 16,
                    "Actual Rows": 60,
                    "Actual Loops": 1260,
                    "Index Cond": "(customer_id = testapp_customer.id)",
                    "Rows Removed by Index Recheck": 0,
                    "Shared Hit Blocks": 70990,
                    "Shared Read Blocks": 8390,
                    "Shared Dirtied Blocks": 0,
                    "Shared Written Blocks": 36,
                    "Local Hit Blocks": 0,
                    "Local Read Blocks": 0,
                    "Local Dirtied Blocks": 0,
                    "Local Written Blocks": 0,
                    "Temp Read Blocks": 0,
                    "Temp Written Blocks": 0,
                },
            ],
        },
        "Planning": {
            "Shared Hit Blocks": 167,
            "Shared Read Blocks": 27,
            "Shared Dirtied Blocks": 2,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 1.374,
        "Triggers": [],
        "Execution Time": 64.285,
    }
]
"""A nested loop whose inner side ran 1,260 times, and the trap that hides in it.

``SELECT o.id FROM testapp_order o INNER JOIN testapp_customer c
ON (o.customer_id = c.id) WHERE md5(c.name) < %s``, under
``SET enable_hashjoin = off``, ``enable_mergejoin = off`` and
``max_parallel_workers_per_gather = 0`` -- the settings that make the planner
choose the join shape this payload is about. ``md5()`` is there to make the outer
predicate opaque, so the planner has to guess how many rows it keeps.

The inner ``Index Scan`` reports 60 rows and 1,260 loops, and 60 x 1,260 is
**75,600**, which is exactly what the join produced. That is the multiplication
that works.

**And it is why a total built from the estimate would be worse than no total.**
``Plan Rows`` on that node is also 60, so the same multiplication returns 75,600
again -- while the planner's own estimate for the join above it is **400,020**,
because it expected 6,667 outer rows and got 1,260. A "total estimated rows" read
off this node would agree with the measurement to the row, on the most badly
mis-estimated plan in the file.
"""

NESTED_LOOP_FILTERED_INNER: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Nested Loop",
            "Parallel Aware": False,
            "Async Capable": False,
            "Join Type": "Inner",
            "Startup Cost": 4.66,
            "Total Cost": 31426.97,
            "Plan Rows": 5980,
            "Plan Width": 8,
            "Actual Rows": 715,
            "Actual Loops": 1,
            "Inner Unique": False,
            "Shared Hit Blocks": 18645,
            "Shared Read Blocks": 195,
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
                    "Node Type": "Index Only Scan",
                    "Parent Relationship": "Outer",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Scan Direction": "Forward",
                    "Index Name": "testapp_customer_pkey",
                    "Relation Name": "testapp_customer",
                    "Alias": "testapp_customer",
                    "Startup Cost": 0.29,
                    "Total Cost": 9.52,
                    "Plan Rows": 299,
                    "Plan Width": 8,
                    "Actual Rows": 299,
                    "Actual Loops": 1,
                    "Index Cond": "(id < 300)",
                    "Rows Removed by Index Recheck": 0,
                    "Heap Fetches": 0,
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
                {
                    "Node Type": "Bitmap Heap Scan",
                    "Parent Relationship": "Inner",
                    "Parallel Aware": False,
                    "Async Capable": False,
                    "Relation Name": "testapp_order",
                    "Alias": "testapp_order",
                    "Startup Cost": 4.37,
                    "Total Cost": 104.88,
                    "Plan Rows": 20,
                    "Plan Width": 16,
                    "Actual Rows": 2,
                    "Actual Loops": 299,
                    "Recheck Cond": "(customer_id = testapp_customer.id)",
                    "Rows Removed by Index Recheck": 0,
                    "Filter": "(md5((reference)::text) < '0a'::text)",
                    "Rows Removed by Filter": 58,
                    "Exact Heap Blocks": 17940,
                    "Lossy Heap Blocks": 0,
                    "Shared Hit Blocks": 18645,
                    "Shared Read Blocks": 192,
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
                            "Index Name": "testapp_order_customer_id_idx",
                            "Startup Cost": 0.0,
                            "Total Cost": 4.37,
                            "Plan Rows": 60,
                            "Plan Width": 0,
                            "Actual Rows": 60,
                            "Actual Loops": 299,
                            "Index Cond": "(customer_id = testapp_customer.id)",
                            "Shared Hit Blocks": 880,
                            "Shared Read Blocks": 17,
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
            "Shared Hit Blocks": 172,
            "Shared Read Blocks": 30,
            "Shared Dirtied Blocks": 0,
            "Shared Written Blocks": 0,
            "Local Hit Blocks": 0,
            "Local Read Blocks": 0,
            "Local Dirtied Blocks": 0,
            "Local Written Blocks": 0,
            "Temp Read Blocks": 0,
            "Temp Written Blocks": 0,
        },
        "Planning Time": 0.815,
        "Triggers": [],
        "Execution Time": 18.344,
    }
]
"""A nested loop whose inner side both filtered and was mispriced per loop.

``SELECT o.id FROM testapp_order o INNER JOIN testapp_customer c
ON (o.customer_id = c.id) WHERE c.id < 300 AND md5(o.reference) < %s``, under
``SET enable_hashjoin = off``, ``enable_mergejoin = off`` and
``max_parallel_workers_per_gather = 0``. The outer predicate is exact so the loop
count is not in question; the inner one goes through ``md5()`` so the planner has
to fall back on a default selectivity for it.

**The node the report will name, and the one it would name misleadingly.** The
``Bitmap Heap Scan`` is the worst-estimated node in this plan -- 20 expected
against 2 arrived, ten times out -- and it ran 299 times. Printed on its own,
"expected 20 rows, 2 arrived" describes one of 299 executions of a read that
produced 715 rows and discarded 17,342, and nothing in the two numbers says so.

Its total also shows the rounding residue at a larger loop count: 715 rows really
arrived, 715 / 299 is 2.39, the node prints 2, and multiplying back gives 598.
That is 117 out, against a bound of ``loops / 2`` -- 149.5.
"""
