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
    """Describe findings gathered from several blocks, most repeated first."""
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
