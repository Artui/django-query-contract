from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from django_query_contract.capture.normalise_sql import normalise_sql


@dataclass(frozen=True, slots=True)
class PlanNode:
    """A single step of a plan: what PostgreSQL chose, and what happened when it ran."""

    node_type: str
    """``Seq Scan``, ``Nested Loop``, ``Sort`` -- PostgreSQL's own name for the step."""

    relation: str | None
    """The table this node reads, when it reads one directly. ``None`` for a join or a sort."""

    index: str | None
    """The index this node reads, when it uses one. ``None`` for a sequential scan."""

    condition: str | None
    """The ``Filter`` this node applied, as a shape: the predicate without its values.

    Half of what index advice is made of -- a filter over a relation, with the
    rows it threw away, is the statement a ``CREATE INDEX`` would answer -- and
    the reason the advice itself is declined is set out at
    :class:`~django_query_contract.RelationAccess`.

    **PostgreSQL renders this predicate with the bound value spelled out, and
    that value is taken back out here.** A parameterised query against a real
    server produces ``Filter: ((reference)::text = '601980.6826913885'::text)``,
    so keeping the string verbatim would put a customer's data on a public
    record for the length of a capture -- in a package that retains no
    parameters anywhere else, and whose own refusal sentence tells the reader so
    when it declines to quote a driver error. The rendering is put through
    :func:`~django_query_contract.normalise_sql`, which is the same small list
    of named rules the statement fingerprint is made with, so a value becomes
    ``%s`` and the column, the operator and the casts survive.

    That redaction is also what makes the predicate a *group*. With the value in
    it, one statement shape run with twelve parameters is twelve different
    conditions and no report could say the twelve executions did the same thing;
    without it, they are one.
    """

    estimated_rows: float
    """``Plan Rows``: how many rows per loop the planner expected this node to produce."""

    actual_rows: float | None
    """``Actual Rows``: how many it produced per loop. ``None`` when the plan was not analyzed."""

    loops: float | None
    """``Actual Loops``: how many times this node was executed. ``None`` without ``ANALYZE``.

    The divisor behind every other measurement on this record, and the field a
    reader of a small database never has to think about because it is 1 there.
    """

    parallel_aware: bool
    """``Parallel Aware``: whether this node is one process's share of a parallel scan.

    **Why a loop count is not self-explanatory.** More than one loop has two
    quite different causes, and this is the only field that tells them apart. A
    parallel-aware node ran once in each participating process, so its ``loops``
    is a count of processes and the work was divided; a node under a nested loop
    ran once per outer row, so its ``loops`` is a measurement of the outer side
    and the work was repeated. The totals are the same arithmetic either way --
    see :attr:`total_actual_rows` -- but :attr:`estimate_error` is only
    comparable in the second case, for the reason set out on it.

    ``False`` for every node of a plan taken without ``ANALYZE`` as well, which
    is correct rather than a default: parallelism is a property of the plan and
    ``EXPLAIN`` prints ``Parallel Aware`` whether or not it measured anything.
    """

    rows_removed_by_filter: float | None
    """How many rows this node read and discarded, per loop, when it filtered.

    Per loop, and therefore the number that reads as 374,699 on a scan that
    discarded 1,124,098 rows because three parallel workers each did a third of
    it. :attr:`total_rows_removed_by_filter` is the one to assert on.
    """

    sort_method: str | None
    """``quicksort``, ``external merge`` -- how a sort node sorted. ``None`` if it is not one."""

    sort_space_type: str | None
    """``Memory`` or ``Disk``: where a sort node's working space came from."""

    sort_space_used_kb: float | None
    """How much of that space it used, in kilobytes."""

    hash_batches: int | None
    """How many batches a hash node needed. More than one means it did not fit in ``work_mem``.

    Reads ``Hash Batches`` from a hash join and ``HashAgg Batches`` from a hash
    aggregate, because they are the same fact under two names and a reader
    asking "did this spill" should not have to know which node type produced it.
    """

    disk_usage_kb: float | None
    """``Disk Usage``: the temporary space a hash aggregate spilled, in kilobytes."""

    shared_hit_blocks: int | None
    """Buffer pages this node found in cache. ``None`` when ``BUFFERS`` was not asked for."""

    shared_read_blocks: int | None
    """Buffer pages this node had to read. The number a plan finding quotes as heap blocks."""

    children: tuple[PlanNode, ...]
    """The nodes feeding this one, in the order PostgreSQL listed them."""

    @classmethod
    def from_explain(cls, node: Mapping[str, Any]) -> PlanNode:
        """Build a node, and its children, from one ``Plan`` object of the JSON output."""
        return cls(
            node_type=str(node.get("Node Type", "")),
            relation=_text(node.get("Relation Name")),
            index=_text(node.get("Index Name")),
            condition=_condition(node.get("Filter")),
            estimated_rows=float(node["Plan Rows"]),
            actual_rows=_number(node.get("Actual Rows")),
            loops=_number(node.get("Actual Loops")),
            parallel_aware=bool(node.get("Parallel Aware", False)),
            rows_removed_by_filter=_number(node.get("Rows Removed by Filter")),
            sort_method=_text(node.get("Sort Method")),
            sort_space_type=_text(node.get("Sort Space Type")),
            sort_space_used_kb=_number(node.get("Sort Space Used")),
            hash_batches=_count(node.get("Hash Batches", node.get("HashAgg Batches"))),
            disk_usage_kb=_number(node.get("Disk Usage")),
            shared_hit_blocks=_count(node.get("Shared Hit Blocks")),
            shared_read_blocks=_count(node.get("Shared Read Blocks")),
            children=tuple(cls.from_explain(child) for child in node.get("Plans", ())),
        )

    def walk(self) -> Iterator[PlanNode]:
        """This node and every node under it, parents before children."""
        yield self
        for child in self.children:
            yield from child.walk()

    @property
    def indexes_used(self) -> tuple[str, ...]:
        """The indexes PostgreSQL read this node's relation through."""
        if self.index is not None:
            return (self.index,)
        return tuple(
            index
            for child in self.children
            if child.relation is None
            for index in child.indexes_used
        )

    @property
    def spilled_to_disk(self) -> bool:
        """Whether this node ran out of ``work_mem`` and used the disk instead."""
        return (
            self.sort_space_type == "Disk"
            or (self.hash_batches is not None and self.hash_batches > 1)
            or (self.disk_usage_kb is not None and self.disk_usage_kb > 0)
        )

    @property
    def total_actual_rows(self) -> float | None:
        """Every row this node produced, across all of its executions."""
        if self.actual_rows is None or self.loops is None:
            return None
        return self.actual_rows * self.loops

    @property
    def total_rows_removed_by_filter(self) -> float | None:
        """Every row this node read and discarded, across all of its executions."""
        if self.rows_removed_by_filter is None or self.loops is None:
            return None
        return self.rows_removed_by_filter * self.loops

    @property
    def estimate_error(self) -> float | None:
        """How many times out the planner's estimate turned out to be, at least 1.0."""
        if self.actual_rows is None:
            return None
        estimated = max(self.estimated_rows, 1.0)
        actual = max(self.actual_rows, 1.0)
        return actual / estimated if actual > estimated else estimated / actual


def _text(value: Any) -> str | None:
    """A string key, or ``None`` when ``EXPLAIN`` did not emit it."""
    return None if value is None else str(value)


def _condition(value: Any) -> str | None:
    """A rendered predicate reduced to its shape, or ``None`` when there was none."""
    return None if value is None else normalise_sql(str(value))


def _number(value: Any) -> float | None:
    """A numeric key as a float, or ``None`` when ``EXPLAIN`` did not emit it."""
    return None if value is None else float(value)


def _count(value: Any) -> int | None:
    """A numeric key that counts whole things, or ``None`` when it was not emitted."""
    return None if value is None else int(value)
