"""The documentation's code blocks are checked, not trusted.

A docs example is the first code anybody runs, so it gets the same treatment as
the package: a guard rather than a convention. A sibling repo shipped two
snippets that were syntax errors, in its README and on a reference page, and
both would have failed the moment a reader pasted them.

Only the syntax is checked. Executing them would need a consumer project, and
the failure this exists to catch -- a snippet that cannot parse -- does not.
"""

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
    # Without this the parametrised test below passes by finding nothing, which
    # is the failure mode of every test that discovers its own inputs.
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
    """The README quotes four numbers off a real mechanism, so they get re-measured.

    ``test_query_capture.py::test_the_ceiling_is_real`` runs the mechanism; this
    checks the document still says what the mechanism does. A table of measured
    numbers rots exactly like a version pin, and silently.
    """
    from django.db import connection

    readme = (_ROOT / "README.md").read_text()

    assert f"| 0 | {connection.queries_limit - 1} | {connection.queries_limit - 1} |" in readme
    assert f"| 0 | {connection.queries_limit + 1} | {connection.queries_limit} |" in readme
    assert f"| {connection.queries_limit - 10} | 100 | 10 |" in readme
    assert f"| {connection.queries_limit} | 5 | **0** |" in readme


def test_the_plan_documents_quote_the_payloads_they_were_measured_from() -> None:
    """Two documents print a table of plan numbers, and both are checked against the source.

    The per-loop section exists because those numbers move: the same statement
    reports one set serially and another in parallel, and the whole argument is
    that a reader cannot tell from the plan alone. A table of them in prose is
    exactly the kind of measured claim that rots silently, so it is compared
    against the payloads it was read off -- which are themselves a real server's
    output, checked in verbatim.
    """
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
