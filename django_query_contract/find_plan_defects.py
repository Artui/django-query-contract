"""Read a capture's plans back as findings."""

from __future__ import annotations

from collections.abc import Iterable

from django_query_contract.plan_defect import PlanDefect
from django_query_contract.plan_finding import PlanFinding
from django_query_contract.plan_node import PlanNode
from django_query_contract.query_record import QueryRecord

# A record paired with the root of its plan, once, so neither is re-derived and
# neither has to be re-tested for None at every use.
_Measured = list[tuple[QueryRecord, PlanNode]]


def find_plan_defects(records: Iterable[QueryRecord]) -> tuple[PlanFinding, ...]:
    """Name the defects the captured plans state, blindness first.

    The whole of the reader, and it is short for the same reason
    :func:`~django_query_contract.find_n_plus_one` is: both defects are
    definitions rather than heuristics. One is a fact PostgreSQL printed; the
    other is an equality and an inequality over a pair of measurements. See
    :class:`~django_query_contract.PlanDefect` for why the other two candidates
    -- a sequential scan over a row threshold and a nested loop with a large
    inner -- are declined, and for why the estimate-versus-actual ratio is
    reported on every node instead of being classified here.

    **Only measured plans are considered.** Without ``ANALYZE`` a plan carries
    the planner's expectations and nothing to check them against, so neither
    defect is decidable from one. Those statements are skipped rather than
    passed, and :func:`~django_query_contract.format_query_plans` says how many
    were skipped rather than reporting a clean bill of health it did not earn.

    Takes any iterable of records, so it reads a
    :class:`~django_query_contract.PlanCapture` directly, a slice of one, or the
    records of a single connection. A record with no plan -- every record from an
    ordinary :class:`~django_query_contract.QueryCapture` -- contributes nothing,
    so calling this on a capture that took no plans returns nothing rather than
    raising.

    ```python
    from django_query_contract import PlanCapture, find_plan_defects

    with PlanCapture() as capture:
        render_author_list()

    for finding in find_plan_defects(capture):
        print(finding.defect, finding.count, finding.actual_rows)
    ```

    Args:
        records: The executions to read.

    Returns:
        The findings, blindness first and then spills, each kind in capture
        order. The order across the two kinds is presentation and not a ranking:
        a spilled sort and a blind estimate have no common scale, and inventing
        one to sort them by would be the first knob.
    """
    measured = _measured(records)
    return (*_blind(measured), *_spills(measured))


def _measured(records: Iterable[QueryRecord]) -> _Measured:
    """Every record whose plan was taken with ``ANALYZE``, paired with its root node.

    The test is that the root carries an actual row count, rather than that the
    plan's ``analyzed`` flag is set. They agree, and the measurement is the thing
    both defects actually need -- so this asks for what it uses.
    """
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
    """Executions of one statement shape that the planner priced identically.

    The root node rather than any node, because a plan's root is where it states
    how many rows the query produces, which is the number the planner would have
    had to get right for the whole plan to be the right one.

    Grouped on ``(fingerprint, that estimate)`` rather than on the fingerprint
    alone, so three executions of one shape that drew two different estimates
    still produce a finding for whichever of them shared one. Requiring a whole
    group to agree would lose that pair for no gain.
    """
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
    """Every node that ran out of ``work_mem``, one finding per node.

    One finding per node rather than per statement, because a plan can spill in
    two places for two reasons -- a sort, and a hash join under it -- and merging
    them would name one and hide the other. They stay in the order the plan lists
    them, parents before children, which is the order a reader of ``EXPLAIN``
    output already has in their head.
    """
    return [
        PlanFinding(defect=PlanDefect.SPILLED_TO_DISK, records=(record,), nodes=(node,))
        for record, root in measured
        for node in root.walk()
        if node.spilled_to_disk
    ]
