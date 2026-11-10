from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.types.plan_defect import PlanDefect
from django_query_contract.types.plan_finding import PlanFinding
from django_query_contract.types.plan_node import PlanNode
from django_query_contract.types.query_record import QueryRecord

# A record paired with the root of its plan, once, so neither is re-derived and
# neither has to be re-tested for None at every use.
_Measured = list[tuple[QueryRecord, PlanNode]]


def find_plan_defects(records: Iterable[QueryRecord]) -> tuple[PlanFinding, ...]:
    """Name the defects the captured plans state, blindness first."""
    measured = _measured(records)
    return (*_blind(measured), *_spills(measured))


def _measured(records: Iterable[QueryRecord]) -> _Measured:
    """Every record whose plan was taken with ``ANALYZE``, paired with its root node."""
    measured: _Measured = []
    for record in records:
        plan = record.plan
        if plan is None or plan.root is None:
            continue
        if plan.root.actual_rows is None:
            continue
        measured.append((record, plan.root))
    return measured


def _blind(measured: _Measured) -> list[PlanFinding]:
    """Executions of one statement shape that the planner priced identically."""
    groups: dict[tuple[str, float], _Measured] = {}
    for record, root in measured:
        groups.setdefault((record.fingerprint, root.estimated_rows), []).append((record, root))

    findings = [
        PlanFinding(
            defect=PlanDefect.PLANNER_BLIND,
            records=tuple(record for record, _ in group),
            nodes=tuple(root for _, root in group),
        )
        for group in groups.values()
        if len(group) > 1 and len({root.actual_rows for _, root in group}) > 1
    ]
    findings.sort(key=lambda finding: finding.first_index)
    return findings


def _spills(measured: _Measured) -> list[PlanFinding]:
    """Every node that ran out of ``work_mem``, one finding per node."""
    return [
        PlanFinding(defect=PlanDefect.SPILLED_TO_DISK, records=(record,), nodes=(node,))
        for record, root in measured
        for node in root.walk()
        if node.spilled_to_disk
    ]
