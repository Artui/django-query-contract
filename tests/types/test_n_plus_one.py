from __future__ import annotations

import os

import django

from django_query_contract import NPlusOne, QueryRecord, StackFrame

_DJANGO_ROOT = os.path.dirname(os.path.abspath(django.__file__))

_CALLER = StackFrame(filename="/app/views.py", lineno=112, function="render")
_INSIDE_DJANGO = StackFrame(
    filename=os.path.join(_DJANGO_ROOT, "db", "models", "query.py"), lineno=1, function="_fetch_all"
)


def _record(index: int, **overrides: object) -> QueryRecord:
    fields: dict[str, object] = {
        "index": index,
        "sql": "SELECT 1",
        "fingerprint": "SELECT %s",
        "alias": "default",
        "vendor": "sqlite",
        "many": False,
        "param_count": None,
        "stack": (_CALLER, _INSIDE_DJANGO),
    }
    fields.update(overrides)
    return QueryRecord(**fields)


def _finding(*records: QueryRecord, stack: tuple[StackFrame, ...] | None = None) -> NPlusOne:
    return NPlusOne(
        fingerprint="SELECT %s",
        stack=(_CALLER, _INSIDE_DJANGO) if stack is None else stack,
        records=records,
    )


def test_the_count_is_how_often_the_statement_ran() -> None:
    assert _finding(_record(0), _record(1), _record(2)).count == 3


def test_the_call_site_is_the_line_to_go_and_look_at() -> None:
    """The headline of a finding, and the reason the whole package exists."""
    assert _finding(_record(0), _record(1)).call_site == _CALLER


def test_a_path_that_never_leaves_django_has_no_call_site() -> None:
    """Reachable in practice: a stack depth low enough to keep only ORM frames."""
    finding = _finding(_record(0), _record(1), stack=(_INSIDE_DJANGO,))
    assert finding.call_site is None


def test_the_first_index_is_where_the_path_started() -> None:
    """The tie-break that makes ordering by count a total order."""
    assert _finding(_record(4), _record(9)).first_index == 4


def test_the_aliases_are_named_in_the_order_they_appeared() -> None:
    """The identity says nothing about the connection, so the span is reported."""
    finding = _finding(
        _record(0, alias="other"),
        _record(1, alias="default"),
        _record(2, alias="other"),
    )
    assert finding.aliases == ("other", "default")


def test_truncation_anywhere_marks_the_whole_finding() -> None:
    """``any``, not "all of them agreed"."""
    finding = _finding(_record(0), _record(1, stack_truncated=True))
    assert finding.stack_truncated is True
    assert _finding(_record(0), _record(1)).stack_truncated is False
