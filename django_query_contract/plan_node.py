"""One node of an execution plan, as PostgreSQL reported it."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from django_query_contract.normalise_sql import normalise_sql


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

    **Row counts are per loop, and that is the one thing about this record that
    changes meaning as a database grows.** PostgreSQL divides a node's actual row
    count by ``Actual Loops`` before printing it, and does the same to
    ``Rows Removed by Filter``. In a small world every node runs once, ``loops``
    is 1, and the printed number is the whole truth. In a big one the same
    statement is handed to three processes, or the same scan is run once per
    outer row, and the printed number becomes a share -- with nothing in the plan
    announcing the change except the loop count nobody was reading.

    Measured, and the pair is checked in: the same
    ``SELECT COUNT(*) ... WHERE md5(reference) < %s`` over 1,200,000 rows reports
    ``Rows Removed by Filter: 1124098`` in one process and ``374699`` in three.
    So :attr:`total_actual_rows` and :attr:`total_rows_removed_by_filter` are
    here, and they are what a report and an assertion should read.

    **The estimate is not totalled, and refusing that is the harder half of the
    decision.** The two multiplications are not the same one:

    - Under a ``Gather``, ``loops`` counts the processes that actually ran, while
      the planner divided its estimate by ``parallel_workers`` plus the fraction
      of a worker it credits the leader with -- 2.4 for two workers, against a
      loop count of 3. Measured on the pair above: 400,000 estimated serially,
      166,667 on the parallel node, and 400,000 / 166,667 is 2.4 exactly. The
      divisor is not in the output, so no arithmetic here recovers it.
    - Under a nested loop, ``loops`` is the number of *outer rows that arrived*,
      which is a measurement. Multiplying a per-loop estimate by it produces a
      number the planner never predicted -- measured on an inner node estimating
      60 rows over 1,260 loops, the product is 75,600, which is exactly what the
      join measured while the planner's own estimate for it was 400,020.

    A ``total_estimated_rows`` would therefore be wrong under a ``Gather`` and
    would agree with the measurement under a nested loop, which is worse: it
    would read as perfect agreement on the plan the planner got most wrong.
    """

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
            condition=_condition(node.get("Filter")),
            # The one key with no default worth defending: a plan node always
            # carries an estimate, because an estimate is what a plan is. A zero
            # here would be a parser bug wearing a plausible number.
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
        """The indexes PostgreSQL read this node's relation through. Empty means none.

        **Not the same question as :attr:`index`, and the difference is what
        keeps a report from crying wolf.** PostgreSQL splits a bitmap read
        across two nodes: the ``Bitmap Heap Scan`` names the table and carries no
        ``Index Name`` at all, while the ``Bitmap Index Scan`` beneath it names
        the index and no table. Put a ``BitmapAnd`` between them -- two indexes
        combined -- and the index is two levels down. A reading that looked only
        at the node itself would report a table PostgreSQL reached through two
        indexes as one it read end to end, which is the single worst thing this
        report could say.

        So it walks down, and stops at the next node that names a relation:
        that node is a different read of a different table, and its index
        belongs to it. Both payloads that pin this are a real server's output.

        Order is the order PostgreSQL listed the nodes in, and duplicates are
        possible in principle -- the same index reached twice under one
        ``BitmapOr`` -- so a caller wanting a set should say so.
        """
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
    def total_actual_rows(self) -> float | None:
        """Every row this node produced, across all of its executions.

        :attr:`actual_rows` multiplied by :attr:`loops`, which is the number a
        reader means when they say "how many rows did this read return" and the
        number an assertion written against a one-loop plan was really making a
        claim about. Where ``loops`` is 1 it is :attr:`actual_rows` unchanged, so
        adopting it costs nothing on the small worlds where the two agree.

        **It is a reconstruction and not a measurement, and the difference is
        one row.** PostgreSQL divides the count by the loop count and rounds
        before printing, so multiplying back can be out by up to half a loop in
        either direction: measured on a three-process scan that really produced
        75,902 rows, the node says 25,301 and this says 75,903. The residue is
        bounded by ``loops / 2`` and it is stated here rather than hidden,
        because the alternative -- an exact total -- is a number the server does
        not print at all.

        ``None`` without a measurement or without a loop count. A missing loop
        count is not treated as 1: this record is public and a caller may have
        built one from something that is not this parser, and turning a gap in
        the input into a number is the move this package refuses everywhere else.
        """
        if self.actual_rows is None or self.loops is None:
            return None
        return self.actual_rows * self.loops

    @property
    def total_rows_removed_by_filter(self) -> float | None:
        """Every row this node read and discarded, across all of its executions.

        The same multiplication as :attr:`total_actual_rows`, with the same
        rounding residue, over the number a report quotes when it says how much
        of a table a read threw away. That number is the one that moves most
        alarmingly when a world gets big enough to be scanned in parallel, and
        it moves *downwards*: a scan discarding 1,124,098 rows in one process
        reports 374,699 in three.

        ``None`` when this node applied no filter. PostgreSQL emits
        ``Rows Removed by Filter`` only where it applied one, so a zero here
        would be a measurement it never made.
        """
        if self.rows_removed_by_filter is None or self.loops is None:
            return None
        return self.rows_removed_by_filter * self.loops

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

        **On a parallel-aware node it is inflated, and by a bounded amount.** The
        two numbers are both per loop, but they were divided by different
        denominators: the measurement by the processes that ran, the estimate by
        ``parallel_workers`` plus the fraction of a worker the planner credits
        the leader with. Measured, two workers means dividing the estimate by 2.4
        and the measurement by 3, so a node the planner priced within 1% reports
        a ratio of about 1.25. The inflation is at most that -- the two divisors
        never differ by more than the leader's share -- so this stays the ratio
        of the two numbers PostgreSQL printed, and :attr:`parallel_aware` is on
        the record so a report can say which nodes it applies to. There is no
        repair available: the divisor the planner used is not in the output.

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


def _condition(value: Any) -> str | None:
    """A rendered predicate reduced to its shape, or ``None`` when there was none.

    The one place a bound value could enter this package's records. See
    :attr:`PlanNode.condition` for why it does not.
    """
    return None if value is None else normalise_sql(str(value))


def _number(value: Any) -> float | None:
    """A numeric key as a float, or ``None`` when ``EXPLAIN`` did not emit it."""
    return None if value is None else float(value)


def _count(value: Any) -> int | None:
    """A numeric key that counts whole things, or ``None`` when it was not emitted."""
    return None if value is None else int(value)
