from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _documents() -> list[Path]:
    return [_ROOT / "README.md", *sorted((_ROOT / "docs").glob("*.md"))]


def test_the_documents_are_where_this_test_thinks_they_are() -> None:
    names = {path.name for path in _documents()}

    assert {"README.md", "index.md", "reference.md"} <= names


@pytest.mark.parametrize("document", _documents(), ids=lambda path: path.name)
def test_every_python_block_parses(document: Path) -> None:
    blocks = _BLOCK.findall(document.read_text())

    for number, block in enumerate(blocks, start=1):
        try:
            ast.parse(block)
        except SyntaxError as error:
            pytest.fail(f"{document.name} python block {number}: {error.msg}\n\n{block}")


def test_the_readme_ceiling_table_matches_the_installed_django() -> None:
    """The README quotes four numbers off a real mechanism, so they get re-measured."""
    from django.db import connection

    readme = (_ROOT / "README.md").read_text()

    assert f"| 0 | {connection.queries_limit - 1} | {connection.queries_limit - 1} |" in readme
    assert f"| 0 | {connection.queries_limit + 1} | {connection.queries_limit} |" in readme
    assert f"| {connection.queries_limit - 10} | 100 | 10 |" in readme
    assert f"| {connection.queries_limit} | 5 | **0** |" in readme


def test_the_plan_documents_quote_the_payloads_they_were_measured_from() -> None:
    """Two documents print a table of plan numbers, and both are checked against the source."""
    from django_query_contract import PlanNode
    from tests.plan_payloads import PARALLEL_SCAN, SERIAL_SCAN

    def scan(payload: list[dict[str, object]]) -> PlanNode:
        (found,) = [
            node
            for node in PlanNode.from_explain(payload[0]["Plan"]).walk()
            if node.node_type == "Seq Scan"
        ]
        return found

    serial, parallel = scan(SERIAL_SCAN), scan(PARALLEL_SCAN)
    plans = (_ROOT / "docs" / "plans.md").read_text()
    readme = (_ROOT / "README.md").read_text()

    assert (
        f"| `Rows Removed by Filter` | {serial.rows_removed_by_filter:,.0f} "
        f"| {parallel.rows_removed_by_filter:,.0f} |"
    ) in plans
    assert (f"| `Actual Rows` | {serial.actual_rows:,.0f} | {parallel.actual_rows:,.0f} |") in plans
    assert f"| `Actual Loops` | {serial.loops:,.0f} | {parallel.loops:,.0f} |" in plans
    assert f"`Rows Removed by Filter: {serial.rows_removed_by_filter:.0f}`" in readme
    assert f"`{parallel.rows_removed_by_filter:.0f}`" in readme
