"""List every N+1 found across a run, worst first."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from django_query_contract.format_n_plus_one import format_n_plus_one
from django_query_contract.n_plus_one import NPlusOne
from django_query_contract.utils import in_project_tree


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

    # Worst first. The label is the middle key rather than a decoration: two
    # blocks can produce findings of the same size that began at the same index,
    # and without it the order of two such findings would depend on the order
    # the mapping happened to be built in.
    flattened.sort(key=lambda item: (-item[1].count, item[0], item[1].first_index))

    # Sectioned by whose code the call site is in, and *only* the display is
    # sectioned: nothing is merged, dropped or renamed, and every finding is
    # still here. A run-wide listing answers "what should I go and fix", which
    # is not the question a finding answers, and ordering by repetition alone
    # puts every library that legitimately loops above every defect in the
    # project. Measured on a consumer: 158 findings, none of the ones there was
    # room to print in their own code.
    yours = [item for item in flattened if in_project_tree(item[1].call_site)]
    theirs = [item for item in flattened if not in_project_tree(item[1].call_site)]

    lines = [f"{len(flattened)} N+1 finding(s), most repeated first:"]
    if yours and theirs:
        lines.append(f"  {len(yours)} in your own code:")
    lines.extend(_section(yours, max_findings=max_findings, max_sql=max_sql))

    if theirs:
        if yours:
            # Named rather than hidden. A repetition inside a dependency is a
            # real one and worth seeing once -- a batched bulk_create is one
            # shape run a hundred times from one line -- it is just not what the
            # reader can act on, and the budget belongs to the half they can.
            lines.append(
                f"  {len(theirs)} inside installed packages, which you cannot fix from here:"
            )
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
