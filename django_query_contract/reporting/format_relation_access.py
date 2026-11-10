from __future__ import annotations

from django_query_contract.analysis.group_by_relation import group_by_relation
from django_query_contract.capture.plan_capture import PlanCapture
from django_query_contract.source_location.relative_to_cwd import relative_to_cwd
from django_query_contract.types.plan_node import PlanNode
from django_query_contract.types.relation_access import RelationAccess
from django_query_contract.utils import loops_note, row_count, shorten

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
    """Describe which tables these plans read, how, and what already indexes them."""
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
    """The read that threw away most, named by an argmax and judged by nobody."""
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
    """Show the multiplication when the total above was one, and nothing when it was not."""
    note = loops_note(node.loops, parallel_aware=node.parallel_aware)
    if note is None:
        return []
    per_loop = row_count(node.rows_removed_by_filter)
    return [f"       across {note}; PostgreSQL states {per_loop} discarded per loop"]


def _catalogue(access: RelationAccess, capture: PlanCapture, *, max_sql: int) -> list[str]:
    """The indexes this table already has, in the statements PostgreSQL would write."""
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
