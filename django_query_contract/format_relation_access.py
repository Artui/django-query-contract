"""Print the evidence an index decision needs, and refuse to make the decision."""

from __future__ import annotations

from django_query_contract.group_by_relation import group_by_relation
from django_query_contract.plan_capture import PlanCapture
from django_query_contract.plan_node import PlanNode
from django_query_contract.relation_access import RelationAccess
from django_query_contract.utils import loops_note, relative_to_cwd, row_count, shorten

# Printed above the relations rather than left to the documentation, and this is
# the most important string in the module. Everything below it is a table name, a
# count of discarded rows and a line number -- which is precisely the material a
# reader turns into "so add an index" on their own. Saying nothing would let the
# report imply a recommendation it has decided it cannot make; the reasoning is
# at ``RelationAccess``.
_DECLINED = (
    "  No index is recommended below, and that is a decision rather than an omission.",
    "  Whether one is worth adding is a judgement about size -- how many rows is too many "
    "to read -- and this package states what the server measured instead.",
)


def format_relation_access(
    capture: PlanCapture,
    *,
    max_relations: int = 5,
    max_sql: int = 160,
) -> str:
    """Describe which tables these plans read, how, and what already indexes them.

    The fourth reading of one capture, after the N+1 findings, the call sites and
    the plans themselves. What it adds is the join between a plan and an address:
    "``testapp_order`` was read end to end eleven times, filtering
    ``((status)::text = %s::text)``, discarding 199,000 rows, from
    ``views.py:112``" -- every clause of which is either PostgreSQL's own output
    or this package's own call-site rule, and none of which is a recommendation.

    Args:
        capture: A closed :class:`~django_query_contract.PlanCapture`.
        max_relations: How many tables to describe before counting the rest.
        max_sql: Where to cut a long predicate or index definition. The records
            keep the whole thing.

    Returns:
        The report, without a trailing newline. Empty when no statement in the
        capture carried a plan that read a table -- which is every ordinary
        :class:`~django_query_contract.QueryCapture`.
    """
    accesses = group_by_relation(capture.records)
    if not accesses:
        return ""

    lines = ["Relations these plans read, and how PostgreSQL reached them:", *_DECLINED]
    for access in accesses[:max_relations]:
        lines.extend(_relation(access, capture, max_sql=max_sql))
    if len(accesses) > max_relations:
        lines.append(f"  and {len(accesses) - max_relations} more relations.")
    return "\n".join(lines)


def _relation(access: RelationAccess, capture: PlanCapture, *, max_sql: int) -> list[str]:
    """One table as an indented block, the counts first and the catalogue last."""
    unindexed = len(access.unindexed_reads)
    lines = [
        f"  {access.relation}  {access.count} read{'' if access.count == 1 else 's'}, "
        f"{unindexed if unindexed else 'none'} without an index"
    ]
    if access.conditions:
        rendered = ", ".join(shorten(condition, max_sql) for condition in access.conditions)
        lines.append(f"       filtering {rendered}")
    lines.extend(_discarded(access))
    if access.indexes_used:
        lines.append(f"       read through {', '.join(access.indexes_used)}")
    lines.append(f"       from {_sites(access)}")
    lines.extend(_catalogue(access, capture, max_sql=max_sql))
    return lines


def _discarded(access: RelationAccess) -> list[str]:
    """The read that threw away most, named by an argmax and judged by nobody.

    **Both numbers are the whole read**, not one loop of it, because a read
    PostgreSQL split across three processes is still one read of this table and
    it discarded everything the three of them discarded. The per-loop figures the
    plan actually prints are named on the line below rather than dropped, so a
    reader comparing this report against ``EXPLAIN`` output can see where the
    total came from.

    Nothing is printed when no read here filtered: PostgreSQL emits
    ``Rows Removed by Filter`` only where it applied one, and a zero would be a
    measurement it never made rather than a table nothing was discarded from.
    """
    worst = access.most_rows_discarded
    if worst is None:
        return []
    rows, node = worst
    kept = row_count(node.total_actual_rows)
    return [
        f"       most one read discarded: {rows:,.0f} rows, keeping {kept}",
        *_arithmetic(node),
    ]


def _arithmetic(node: PlanNode) -> list[str]:
    """Show the multiplication when the total above was one, and nothing when it was not.

    Silent for a node that ran once, which is every node of every plan over a
    database small enough not to be scanned in parallel -- so the ordinary report
    is unchanged and this line appears exactly where the old number would have
    started meaning something different.
    """
    note = loops_note(node.loops, parallel_aware=node.parallel_aware)
    if note is None:
        return []
    per_loop = row_count(node.rows_removed_by_filter)
    return [f"       across {note}; PostgreSQL states {per_loop} discarded per loop"]


def _catalogue(access: RelationAccess, capture: PlanCapture, *, max_sql: int) -> list[str]:
    """The indexes this table already has, in the statements PostgreSQL would write.

    **The only ``CREATE INDEX`` statements this package prints, and they are the
    ones that exist.** The milestone imagined emitting the ones that should; what
    can be stated instead is what is already there, beside the filter above it,
    so a reader can see for themselves which predicate nothing covers.

    Nothing is printed when the catalogue said nothing about this relation --
    a capture that never asked, or a table that was gone by the time it did. An
    empty list would read as "this table has no indexes", which is a claim, and
    a false one for any table with a primary key.
    """
    definitions = capture.relation_indexes.get(access.relation, ())
    if not definitions:
        return []
    count = len(definitions)
    lines = [
        f"       PostgreSQL has {count} index{'' if count == 1 else 'es'} on {access.relation}:"
    ]
    lines.extend(f"         {shorten(definition, max_sql)}" for definition in definitions)
    return lines


def _sites(access: RelationAccess) -> str:
    """Every line that reached this table, shortened and deduplicated."""
    return ", ".join(
        "no frame outside Django (the capture's stack depth did not reach one)"
        if site is None
        else relative_to_cwd(str(site))
        for site in access.call_sites
    )
