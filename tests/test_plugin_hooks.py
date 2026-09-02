"""Each plugin hook, driven directly, with real pytest objects on both sides.

``test_plugin.py`` proves the hooks are wired and that a real run gets a real
section; it does that by running pytest in a subprocess, which is the only place
a report section exists. What a subprocess cannot show is which branch was
taken, so the decisions live here: capture or stand aside, speak or stay quiet.

Nothing here is a stand-in. The configs come from ``Pytester.parseconfig``, the
items from a collected module, the reports from
``TestReport.from_item_and_call``, and the hookwrapper results from
``pluggy.Result`` -- so a change in any of those shapes fails these tests rather
than agreeing with them.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from django.conf import empty, settings
from django.db import connection
from pluggy import Result

from django_query_lens import QueryLogCeilingWarning, plugin

_A_TEST = """
def test_nothing():
    assert True
"""


def _item(pytester: pytest.Pytester, *configargs: str) -> pytest.Item:
    """A real collected test item, whose config carries the given command line.

    For tests that vary the command line and touch no database. Building a
    second pytest ``Config`` constructs a **new** pytest-django database
    blocker -- they live on ``Config.stash``, one per config -- which installs
    its blocking wrapper over the global
    ``BaseDatabaseWrapper.ensure_connection``. The outer blocker cannot hand
    that back: ``unblock`` and ``restore`` pop a different instance's history,
    so the connection stays closed for the rest of the test *and its teardown*.
    On Django 4.2 that surfaces as an error in ``check_constraints`` after the
    test itself has already passed; on 6.1 the teardown happens not to need a
    cursor and the same bug is invisible.

    A test that touches a database uses :func:`_live_item` instead.
    """
    module = pytester.getmodulecol(_A_TEST, configargs=list(configargs))
    (item,) = module.collect()
    return item


def _live_item(request: pytest.FixtureRequest) -> pytest.Item:
    """The item pytest is running right now.

    Realer than a collected one, and free of the blocker problem above: it is a
    genuine ``Function`` carrying the session's own ``Config``, so driving the
    hooks with it needs no second config to exist at all. Every test that has to
    vary the command line is one that touches no database, so the two helpers
    divide cleanly.
    """
    node = request.node
    assert isinstance(node, pytest.Item)
    return node


def _run_call_hook(item: pytest.Item, body: Any = None) -> None:
    """Drive ``pytest_runtest_call`` by hand, running ``body`` where the test would."""
    generator = plugin.pytest_runtest_call(item)
    next(generator)
    if body is not None:
        body()
    with pytest.raises(StopIteration):
        next(generator)


def _make_report(item: pytest.Item, when: str, failing: bool) -> pytest.TestReport:
    """A real ``TestReport`` for the given phase and outcome."""

    def outcome() -> None:
        if failing:
            raise AssertionError("boom")

    call = pytest.CallInfo.from_call(outcome, when)
    return pytest.TestReport.from_item_and_call(item, call)


def _run_makereport(item: pytest.Item, report: pytest.TestReport) -> pytest.TestReport:
    """Drive the report hookwrapper by hand and hand it the report to enrich."""
    generator = plugin.pytest_runtest_makereport(
        item, pytest.CallInfo.from_call(lambda: None, "call")
    )
    next(generator)
    with pytest.raises(StopIteration):
        generator.send(Result(report, None))
    return report


@pytest.mark.django_db
def test_the_call_hook_captures_and_leaves_the_capture_behind(
    request: pytest.FixtureRequest,
) -> None:
    """The stash is the join between the two hooks: one fills it, the other reads it."""
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

    _run_call_hook(item, body)

    capture = item.stash[plugin._CAPTURE_KEY]
    assert len(capture) == 1


def test_the_flag_stands_the_hook_down(pytester: pytest.Pytester) -> None:
    """Nothing is captured and nothing is stashed, so the report hook has nothing to say."""
    item = _item(pytester, "--no-query-lens")

    _run_call_hook(item)

    assert plugin._CAPTURE_KEY not in item.stash


def test_a_project_without_django_settings_is_left_alone(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unconfigured through Django's own mechanism, not through a stand-in.

    ``LazySettings.configured`` is ``self._wrapped is not empty``, so putting
    the sentinel back is exactly the state a project that never called
    ``settings.configure()`` is in.
    """
    item = _item(pytester)
    monkeypatch.setattr(settings, "_wrapped", empty)

    _run_call_hook(item)

    assert plugin._CAPTURE_KEY not in item.stash


@pytest.mark.django_db
def test_a_block_over_the_ceiling_warns(
    request: pytest.FixtureRequest, tiny_query_log: int
) -> None:
    """The warning fires on the way out of the call phase, whatever the outcome was."""
    item = _live_item(request)
    connection.queries_log.extend(
        {"sql": "SELECT 1", "time": "0.000"} for _ in range(tiny_query_log)
    )

    def body() -> None:
        with connection.cursor() as cursor:
            for _ in range(3):
                cursor.execute("SELECT 1")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _run_call_hook(item, body)

    (raised,) = [entry for entry in caught if entry.category is QueryLogCeilingWarning]
    assert "reports 0 for this block" in str(raised.message)


@pytest.mark.django_db
def test_a_failed_call_gains_the_section(request: pytest.FixtureRequest) -> None:
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.execute("SELECT 1")

    _run_call_hook(item, body)
    report = _run_makereport(item, _make_report(item, "call", failing=True))

    (section,) = report.sections
    assert section[0] == "django-query-lens"
    assert "2 statements captured" in section[1]


@pytest.mark.django_db
def test_a_passing_call_gains_nothing(request: pytest.FixtureRequest) -> None:
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

    _run_call_hook(item, body)
    report = _run_makereport(item, _make_report(item, "call", failing=False))

    assert report.sections == []


@pytest.mark.django_db
def test_a_failure_in_setup_gains_nothing(request: pytest.FixtureRequest) -> None:
    """Only the call phase is diagnosed; the capture describes the call phase."""
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

    _run_call_hook(item, body)
    report = _run_makereport(item, _make_report(item, "setup", failing=True))

    assert report.sections == []


def test_a_failure_with_capture_disabled_gains_nothing(pytester: pytest.Pytester) -> None:
    """Nothing in the stash, so the report hook returns before it formats anything."""
    item = _item(pytester, "--no-query-lens")

    _run_call_hook(item)
    report = _run_makereport(item, _make_report(item, "call", failing=True))

    assert report.sections == []


@pytest.mark.django_db
def test_a_failure_with_an_empty_capture_gains_nothing(request: pytest.FixtureRequest) -> None:
    """A failure unrelated to the database does not acquire a paragraph about it."""
    item = _live_item(request)

    _run_call_hook(item)
    report = _run_makereport(item, _make_report(item, "call", failing=True))

    assert report.sections == []


def test_the_stack_depth_ini_has_a_default(pytester: pytest.Pytester) -> None:
    """A project that configures nothing still gets a working depth."""
    config = pytester.parseconfig()

    assert config.getini("query_lens") is True
    assert int(config.getini("query_lens_stack_depth")) == 25
