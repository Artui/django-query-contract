from __future__ import annotations

from collections.abc import Mapping, Sequence

from django_query_contract.reporting.format_n_plus_one import format_n_plus_one
from django_query_contract.source_location.in_project_tree import in_project_tree
from django_query_contract.types.n_plus_one import NPlusOne


def format_n_plus_one_summary(
    findings: Mapping[str, Sequence[NPlusOne]],
    *,
    max_findings: int = 20,
    max_sql: int = 160,
) -> str:
    """Describe findings gathered from several blocks, most repeated first.

    The listing behind the pytest plugin's ``--n-plus-one``, written as a plain
    function so the CI-report face can use it with no test runner in the loop.
    The keys are whatever names the blocks -- node ids, for that plugin.

    **Findings are not merged across blocks, and that is deliberate.** The same
    call site reached from two tests is two findings here, because the identity
    of a finding is the whole call stack and two tests are two stacks. Merging
    them would need a second grouping rule -- "these are the same really" --
    which is the sort of judgement this package is built without. The listing is
    ordered instead, so the worst one is the first thing on the screen whether it
    came from one block or twenty.

    Args:
        findings: Each block's findings, keyed by a name for the block.
        max_findings: How many to print before summarising the rest.
        max_sql: Where to cut a long statement.

    Returns:
        The listing, without a trailing newline. Never empty: with nothing to
        report it says so, because no N+1 anywhere is the answer somebody
        asked this question to get, and a blank screen does not give it to them.
    """
    flattened = [(label, finding) for label, group in findings.items() for finding in group]
    if not flattened:
        return "No N+1: no statement shape repeated from a single call path."

    flattened.sort(key=lambda item: (-item[1].count, item[0], item[1].first_index))

    yours = [item for item in flattened if in_project_tree(item[1].call_site)]
    theirs = [item for item in flattened if not in_project_tree(item[1].call_site)]

    lines = [f"{len(flattened)} N+1 finding(s), most repeated first:"]
    if yours and theirs:
        lines.append(f"  {len(yours)} in your own code:")
    lines.extend(_section(yours, max_findings=max_findings, max_sql=max_sql))

    if theirs:
        if yours:
            lines.append(f"  {len(theirs)} outside your working tree:")
        lines.extend(
            _section(theirs, max_findings=max(max_findings - len(yours), 1), max_sql=max_sql)
        )
    return "\n".join(lines)


def _section(items: list[tuple[str, NPlusOne]], *, max_findings: int, max_sql: int) -> list[str]:
    """One section's findings, with its own overflow line."""
    lines = [
        format_n_plus_one(finding, max_sql=max_sql, label=label)
        for label, finding in items[:max_findings]
    ]
    if len(items) > max_findings:
        lines.append(f"  and {len(items) - max_findings} more findings.")
    return lines
