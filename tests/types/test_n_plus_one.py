"""The finding, and the four questions it answers about itself.

Records are built by hand here rather than captured, because these are the
properties of a value: what the finding says when it holds particular records is
exactly what is worth pinning, and a real capture cannot be steered into every
shape one can hold. ``test_find_n_plus_one.py`` does the opposite -- every
capture there is real -- and between them the identity and the value are both
covered against something that can disagree with them.
"""

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
    """The headline of a finding, and the reason the whole package exists.

    Derived from the finding's stack through the same helper a record uses, so
    a finding and the records inside it cannot name different call sites.
    """
    assert _finding(_record(0), _record(1)).call_site == _CALLER


def test_a_path_that_never_leaves_django_has_no_call_site() -> None:
    """Reachable in practice: a stack depth low enough to keep only ORM frames.

    ``None`` rather than the innermost frame available, for the same reason a
    record refuses -- naming ``django/db/models/query.py`` is true of every
    query ever run.
    """
    finding = _finding(_record(0), _record(1), stack=(_INSIDE_DJANGO,))
    assert finding.call_site is None


def test_the_first_index_is_where_the_path_started() -> None:
    """The tie-break that makes ordering by count a total order."""
    assert _finding(_record(4), _record(9)).first_index == 4


def test_the_aliases_are_named_in_the_order_they_appeared() -> None:
    """The identity says nothing about the connection, so the span is reported.

    One line querying two databases is one loop with one fix, so it stays one
    finding. Deduplicated and ordered, so the report is stable rather than
    however a set happened to iterate.
    """
    finding = _finding(
        _record(0, alias="other"),
        _record(1, alias="default"),
        _record(2, alias="other"),
    )
    assert finding.aliases == ("other", "default")


def test_truncation_anywhere_marks_the_whole_finding() -> None:
    """``any``, not "all of them agreed".

    Two executions can keep matching frames while the frames above differ -- a
    recursive walk reaching the same line from two depths -- so one truncated
    record is enough to make the path a partial one, and a reader is told.
    """
    finding = _finding(_record(0), _record(1, stack_truncated=True))
    assert finding.stack_truncated is True
    assert _finding(_record(0), _record(1)).stack_truncated is False
