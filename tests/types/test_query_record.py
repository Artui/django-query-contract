from __future__ import annotations

import contextlib
import os

import django

from django_query_contract import QueryRecord, StackFrame

_DJANGO_ROOT = os.path.dirname(os.path.abspath(django.__file__))


def _django_frame(name: str) -> StackFrame:
    return StackFrame(
        filename=os.path.join(_DJANGO_ROOT, "db", "models", "query.py"), lineno=1, function=name
    )


def _record(*stack: StackFrame, **overrides: object) -> QueryRecord:
    fields: dict[str, object] = {
        "index": 0,
        "sql": "SELECT 1",
        "fingerprint": "SELECT %s",
        "alias": "default",
        "vendor": "sqlite",
        "many": False,
        "param_count": None,
        "stack": stack,
    }
    fields.update(overrides)
    return QueryRecord(**fields)


def test_the_call_site_is_the_innermost_frame_outside_django() -> None:
    """The point of the record: one line a reader can go and look at."""
    caller = StackFrame(filename="/app/views.py", lineno=112, function="render")
    record = _record(
        StackFrame(filename="/app/urls.py", lineno=9, function="dispatch"),
        caller,
        _django_frame("_fetch_all"),
        _django_frame("execute_sql"),
    )
    assert record.call_site == caller


def test_only_django_is_skipped() -> None:
    """A framework, a factory or a service layer did emit the query."""
    library = StackFrame(filename="/venv/rest_framework/generics.py", lineno=4, function="list")
    record = _record(
        StackFrame(filename="/app/views.py", lineno=112, function="render"),
        library,
        _django_frame("_fetch_all"),
    )
    assert record.call_site == library


def test_a_stack_of_only_django_frames_has_no_call_site() -> None:
    """``None`` rather than the innermost frame available."""
    assert _record(_django_frame("_fetch_all"), _django_frame("execute_sql")).call_site is None


def test_an_empty_stack_has_no_call_site() -> None:
    """The shape a record reconstructed from a CaptureQueriesContext arrives in."""
    assert _record().call_site is None


def test_the_stack_defaults_to_empty_and_untruncated() -> None:
    record = QueryRecord(
        index=3,
        sql="BEGIN",
        fingerprint="BEGIN",
        alias="other",
        vendor="sqlite",
        many=False,
        param_count=None,
    )
    assert record.stack == ()
    assert record.stack_truncated is False


def test_a_frame_prints_as_a_location() -> None:
    assert str(StackFrame(filename="/app/views.py", lineno=112, function="render")) == (
        "/app/views.py:112 in render"
    )


def test_a_record_names_the_readers_own_frame_the_way_a_finding_does() -> None:
    """One walk, so a record and the finding holding it cannot disagree."""
    mine = StackFrame(
        filename=os.path.join(os.getcwd(), "shop", "views.py"), lineno=7, function="index"
    )
    record = _record(
        mine,
        StackFrame(filename=contextlib.__file__, lineno=84, function="inner"),
    )

    assert record.call_site is not None
    assert "contextlib" in record.call_site.filename
    assert record.project_call_site == mine


def test_a_record_with_no_frame_of_the_readers_reports_none() -> None:
    record = _record(StackFrame(filename="/elsewhere/lib.py", lineno=1, function="f"))

    assert record.project_call_site is None


def test_the_readers_innermost_frame_wins_not_their_outermost() -> None:
    """The direction of the walk, which no other test here can hold."""
    outer = StackFrame(
        filename=os.path.join(os.getcwd(), "shop", "views.py"), lineno=7, function="index"
    )
    inner = StackFrame(
        filename=os.path.join(os.getcwd(), "shop", "services.py"), lineno=52, function="charge"
    )
    record = _record(outer, _django_frame("execute"), inner, _django_frame("cursor"))

    assert record.project_call_site == inner
