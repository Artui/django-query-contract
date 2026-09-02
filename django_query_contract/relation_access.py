"""One relation, and every plan node in a capture that read it."""

from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.plan_node import PlanNode
from django_query_contract.query_record import QueryRecord
from django_query_contract.stack_frame import StackFrame


@dataclass(frozen=True, slots=True)
class RelationAccess:
    """How one table was reached, by which statements, and from which lines.

    **This is the milestone that was going to be index advice, and it is a
    report instead.** The plan for this package said the output people actually
    want is "these twelve queries sequentially scanned a two-million-row table,
    here are the ``CREATE INDEX`` statements", and that it falls straight out of
    having plans plus call sites. It does not, and the reason is the same rule
    that decided every other question here: **a finding is a fact the server
    states, or an equality over measurements, never a number somebody picked.**

    Three routes to an assertable version were tried against a real server and
    all three ended in a threshold.

    - *A sequential scan on a relation that another captured statement reaches
      by index.* That reads like a comparison between two measurements rather
      than a cut-off, and it is not: two statements filtering **different
      columns** of one table are not measuring the same thing. Measured against
      a server -- one statement reached ``testapp_order`` through the foreign
      key index while another read it end to end for a predicate that kept all
      100,000 of its rows, which is the *correct* plan and the one no index
      improves. Both halves of the rule hold; the index it would point at is on
      the other statement's column.
    - *A filter whose ``Rows Removed by Filter`` the server itself counted.* The
      number is PostgreSQL's, but the verdict is not: a five-row table discards
      four rows in exactly the shape a hundred-thousand-row table discards
      99,999, and only a magnitude separates them. The count does not even order
      the candidates, because the read that discarded **nothing** is the
      whole-table read that was right to be a scan.
    - *Emitting the ``CREATE INDEX`` itself.* That needs a column, and the only
      place a column can be got is PostgreSQL's rendered predicate -- an
      expression that would have to be parsed, in a package that declines a SQL
      parser for reasons written out at
      :func:`~django_query_contract.normalise_sql`, and whose text carries the
      bound value this package retains nowhere.

    So what is here is every fact the decision needs and no decision: the table,
    how PostgreSQL reached it, the predicate it applied with the values taken
    out, how many rows it said it threw away, the lines that asked, and -- from
    :attr:`~django_query_contract.PlanCapture.relation_indexes` -- the indexes
    that already exist, in the server's own words. The reader supplies the part
    that is a judgement. That is the same bargain
    :attr:`~django_query_contract.PlanNode.estimate_error` struck: report the
    two numbers, classify neither.

    **It is a grouping and not a detector**, in the sense
    :func:`~django_query_contract.group_by_call_site` sets out. Nothing here is
    a finding, nothing fails on it, and there is no rule anywhere in it about
    which read is the interesting one -- which is exactly why it is allowed to
    put a relation's reads side by side, where a finding would not be.

    :attr:`records` and :attr:`nodes` are parallel: ``nodes[i]`` is the node in
    ``records[i]``'s plan that read this relation. A record appears twice when
    one plan read the table twice, which is what a self-join is.
    """

    relation: str
    """The table, under the name PostgreSQL printed in the plan."""

    records: tuple[QueryRecord, ...]
    """The executions that read it, in capture order. At least one."""

    nodes: tuple[PlanNode, ...]
    """The node in each of those plans that did the reading."""

    @property
    def count(self) -> int:
        """How many times this relation was read.

        Reads, not statements: one plan reading a table twice counts twice, so
        the reads listed under a relation cannot outnumber the number printed
        beside its name.
        """
        return len(self.nodes)

    @property
    def first_index(self) -> int:
        """Position in the capture of the first statement that read this relation.

        The tie-break on an ordering by :attr:`count` -- and, unlike
        :attr:`~django_query_contract.Attribution.first_index`, **it does not
        make that order total on its own**. An attribution's first statement
        belongs to it alone; one statement reads several relations, so two
        groups here can share one and tie on both keys. Plan order settles
        those, which is deterministic and is the order ``EXPLAIN`` printed them
        in.
        """
        return self.records[0].index

    @property
    def call_sites(self) -> tuple[StackFrame | None, ...]:
        """The distinct lines these reads came from, in the order first seen.

        Picked by the rule the whole package shares -- the innermost frame
        outside Django, see
        :attr:`~django_query_contract.QueryRecord.call_site` -- so a report can
        never name one line here and a different line for the same statement
        three blocks higher up. A ``None`` is a record whose kept frames were
        all Django's own, reported rather than approximated.
        """
        return tuple(dict.fromkeys(record.call_site for record in self.records))

    @property
    def indexes_used(self) -> tuple[str, ...]:
        """Every index PostgreSQL read this relation through, in the order first seen.

        Resolved per node by :attr:`~django_query_contract.PlanNode.indexes_used`,
        which walks down past the nodes PostgreSQL splits a bitmap read across.
        Empty means every read here went to the table itself.
        """
        return tuple(dict.fromkeys(index for node in self.nodes for index in node.indexes_used))

    @property
    def unindexed_reads(self) -> tuple[PlanNode, ...]:
        """The reads that reached this table without an index, in plan order.

        The subset an index decision is about -- and the whole of what this
        package will say on the subject. Whether a read wanting an index is a
        problem depends on how much of the table it read, and that is the number
        this package does not pick.
        """
        return tuple(node for node in self.nodes if not node.indexes_used)

    @property
    def conditions(self) -> tuple[str, ...]:
        """The distinct predicates applied to this relation, in the order first seen.

        Shapes rather than predicates as printed: the value is taken out at
        parse time, for the reasons
        :attr:`~django_query_contract.PlanNode.condition` gives. That is what
        lets twelve executions of one statement with twelve parameters appear
        here as one entry rather than twelve.
        """
        return tuple(
            dict.fromkeys(node.condition for node in self.nodes if node.condition is not None)
        )

    @property
    def most_rows_discarded(self) -> tuple[float, PlanNode] | None:
        """The most rows any one read of this table threw away, and which read.

        **An argmax rather than a cut-off**, which is the same device
        :attr:`~django_query_contract.QueryPlan.worst_estimate` uses and for the
        same reason: every set of reads has one that discarded the most, so
        naming it introduces no number of ours. Whether that many is too many is
        the judgement this class declines.

        ``None`` when no read here filtered at all. PostgreSQL emits
        ``Rows Removed by Filter`` only where it applied one, so zero would be a
        measurement it never made.
        """
        # ``max`` takes the first of a tie, and the tie-break is therefore plan
        # order -- the order the nodes were listed in, which is the order a
        # reader of EXPLAIN output already has in their head.
        scored = [
            (rows, node) for node in self.nodes if (rows := node.rows_removed_by_filter) is not None
        ]
        if not scored:
            return None
        return max(scored, key=lambda candidate: candidate[0])
