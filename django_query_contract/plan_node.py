"""One node of an execution plan, as PostgreSQL reported it."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlanNode:
    """A single step of a plan: what PostgreSQL chose, and what happened when it ran.

    The fields are the subset of ``EXPLAIN (ANALYZE, BUFFERS, TIMING OFF,
    FORMAT JSON)`` this package can say something true about, and every one of
    them was read off a real server rather than off the documentation. What is
    kept and what is dropped both follow one rule.

    **No timings are kept, and the ``TIMING OFF`` in that statement is the same
    decision seen from the other side.** This package's argument is that a
    performance assertion mentioning a number of milliseconds is a flaky test
    with extra steps, so a per-node duration would be a field inviting exactly
    the assertion the package exists to refuse. Turning the instrumentation off
    is therefore not a cost optimisation that happens to agree with the thesis;
    it is the thesis, and the cost saving is the bonus -- ``ANALYZE`` with
    timings on calls ``gettimeofday`` twice per row per node.

    **Rows are floats, not integers.** ``Plan Rows`` is an integer today, but
    ``Actual Rows`` became fractional in PostgreSQL 18 for a node under more
    than one loop, where it is an average. Rounding it here to keep a tidier
    type would make this record quietly lossy on a server that is already
    shipping.

    **Row counts are per loop, on both sides.** PostgreSQL divides a node's
    actual row count by ``Actual Loops`` before printing it, and the estimate it
    prints beside it is also per loop, so the two compare directly and
    :attr:`estimate_error` needs no arithmetic to make them commensurate.
    Multiply either by ``loops`` for the total.
    """

    node_type: str
    """``Seq Scan``, ``Nested Loop``, ``Sort`` -- PostgreSQL's own name for the step."""

    relation: str | None
    """The table this node reads, when it reads one directly. ``None`` for a join or a sort."""

    index: str | None
    """The index this node reads, when it uses one. ``None`` for a sequential scan."""

    condition: str | None
    """The ``Filter`` this node applied, as PostgreSQL rendered it.

    Kept because it is half of what index advice is made of: a filter over a
    relation, with the rows it threw away, is the statement a ``CREATE INDEX``
    would answer. The advice itself is a later milestone; the record carrying
    what it needs is this one.
    """

    estimated_rows: float
    """``Plan Rows``: how many rows per loop the planner expected this node to produce."""

    actual_rows: float | None
    """``Actual Rows``: how many it produced per loop. ``None`` when the plan was not analyzed."""

    loops: float | None
    """``Actual Loops``: how many times this node was executed. ``None`` without ``ANALYZE``."""

    rows_removed_by_filter: float | None
    """How many rows this node read and discarded, per loop, when it filtered."""

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
        """Build a node, and its children, from one ``Plan`` object of the JSON output.

        Every key is read with a default because ``EXPLAIN`` emits a key only
        when it applies: a sequential scan has no ``Index Name``, a plan taken
        without ``ANALYZE`` has no ``Actual Rows``, and a node that never
        filtered has no ``Rows Removed by Filter``. Requiring any of them would
        make this raise on the ordinary plan rather than on the unusual one.
        """
        return cls(
            node_type=str(node.get("Node Type", "")),
            relation=_text(node.get("Relation Name")),
            index=_text(node.get("Index Name")),
            condition=_text(node.get("Filter")),
            # The one key with no default worth defending: a plan node always
            # carries an estimate, because an estimate is what a plan is. A zero
            # here would be a parser bug wearing a plausible number.
            estimated_rows=float(node["Plan Rows"]),
            actual_rows=_number(node.get("Actual Rows")),
            loops=_number(node.get("Actual Loops")),
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
    def spilled_to_disk(self) -> bool:
        """Whether this node ran out of ``work_mem`` and used the disk instead.

        **The one plan defect that needs no threshold of ours, because PostgreSQL
        already applied its own.** A sort that says ``Sort Space Type: Disk``, a
        hash join that needed more than one batch and a hash aggregate that
        reports disk usage are all the server stating that the memory it was
        given was not enough. The number that decided it is ``work_mem``, which
        belongs to the database being tested rather than to this package, so
        there is nothing here to tune and nothing to be wrong about.

        That also means the finding is a claim about a *configuration* as much as
        about a query, which is why nothing in this package fails a test on it.
        """
        return (
            self.sort_space_type == "Disk"
            or (self.hash_batches is not None and self.hash_batches > 1)
            or (self.disk_usage_kb is not None and self.disk_usage_kb > 0)
        )

    @property
    def estimate_error(self) -> float | None:
        """How many times out the planner's estimate turned out to be, at least 1.0.

        **Reported, never classified, and that distinction is the design.** "The
        planner expected 20 rows and 20,323 arrived" is a fact about this plan.
        "An estimate more than 50 times out is a defect" is a policy about size,
        and a policy about size is the knob this package refuses everywhere else.
        So this is a number on a record, ordered by a report and read by a human;
        no code in this package turns it into a verdict.

        There are also ordinary reasons for a large value that have nothing to do
        with a defect. A node under a ``LIMIT`` stops early by design, so its
        actual is *meant* to fall short of its estimate; measured on a plain
        ``[:5]`` query against fifty rows, the scan under the limit reports an
        estimate of 50 against an actual of 5. A rule that flagged that would cry
        wolf on the first query anybody pointed it at.

        Direction is not encoded, because both numbers are on the record and a
        report prints them side by side. ``None`` when the plan was not analyzed:
        without an actual there is nothing to be wrong about.

        Zero actual rows are compared as one. PostgreSQL never estimates below
        one row itself, so one is the floor the planner's own arithmetic uses,
        and a ratio against zero is not a number.
        """
        if self.actual_rows is None:
            return None
        estimated = max(self.estimated_rows, 1.0)
        actual = max(self.actual_rows, 1.0)
        return actual / estimated if actual > estimated else estimated / actual


def _text(value: Any) -> str | None:
    """A string key, or ``None`` when ``EXPLAIN`` did not emit it."""
    return None if value is None else str(value)


def _number(value: Any) -> float | None:
    """A numeric key as a float, or ``None`` when ``EXPLAIN`` did not emit it."""
    return None if value is None else float(value)


def _count(value: Any) -> int | None:
    """A numeric key that counts whole things, or ``None`` when it was not emitted."""
    return None if value is None else int(value)
