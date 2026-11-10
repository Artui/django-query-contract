from __future__ import annotations

import warnings
from typing import Any

import pytest
from _pytest.outcomes import Skipped
from django.conf import empty, settings
from django.db import connection
from pluggy import Result

from django_query_contract import PlanCapture, QueryLogCeilingWarning, plugin

_A_TEST = """
def test_nothing():
    assert True
"""


def _item(pytester: pytest.Pytester, *configargs: str) -> pytest.Item:
    """A real collected test item, whose config carries the given command line."""
    module = pytester.getmodulecol(_A_TEST, configargs=list(configargs))
    (item,) = module.collect()
    return item


def _live_item(request: pytest.FixtureRequest) -> pytest.Item:
    """The item pytest is running right now."""
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


def _run_setup_hook(item: pytest.Item) -> None:
    """Drive ``pytest_runtest_setup`` by hand, standing in for the setup phase."""
    generator = plugin.pytest_runtest_setup(item)
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)


def _make_report(item: pytest.Item, when: str, failing: bool) -> pytest.TestReport:
    """A real ``TestReport`` for the given phase and outcome."""

    def outcome() -> None:
        if failing:
            raise AssertionError("boom")

    call = pytest.CallInfo.from_call(outcome, when)
    return pytest.TestReport.from_item_and_call(item, call)


def _reporter(pytester: pytest.Pytester, *configargs: str) -> Any:
    """pytest's own terminal reporter, over a real ``Config``, writing to captured stdout."""
    return pytester.parseconfigure(*configargs).pluginmanager.getplugin("terminalreporter")


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
    item = _item(pytester, "--no-query-contract")

    _run_call_hook(item)

    assert plugin._CAPTURE_KEY not in item.stash


def test_a_project_without_django_settings_is_left_alone(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unconfigured through Django's own mechanism, not through a stand-in."""
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
    assert section[0] == "django-query-contract"
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
    item = _item(pytester, "--no-query-contract")

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

    assert config.getini("query_contract") is True
    assert int(config.getini("query_contract_stack_depth")) == 25


@pytest.mark.django_db
def test_the_flag_collects_a_finding_for_the_summary(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The collection half of the listing: findings, not the capture they came from."""
    item = _live_item(request)
    monkeypatch.setattr(item.config.option, "n_plus_one", True)

    def body() -> None:
        with connection.cursor() as cursor:
            for _ in range(2):
                cursor.execute("SELECT 1")

    try:
        _run_call_hook(item, body)

        collected = item.config.stash[plugin._FINDINGS_KEY]
        assert list(collected) == [item.nodeid]
        (finding,) = collected[item.nodeid]
        assert finding.count == 2
    finally:
        del item.config.stash[plugin._FINDINGS_KEY]


@pytest.mark.django_db
def test_a_test_with_no_findings_still_records_that_it_was_asked(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent means "nobody asked"; empty means "asked, and there were none"."""
    item = _live_item(request)
    monkeypatch.setattr(item.config.option, "n_plus_one", True)

    try:
        _run_call_hook(item)

        assert item.config.stash[plugin._FINDINGS_KEY] == {}
    finally:
        del item.config.stash[plugin._FINDINGS_KEY]


def test_the_summary_says_nothing_when_nobody_asked(
    pytester: pytest.Pytester, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not one line, rather than an empty section on every run of every suite."""
    plugin.pytest_terminal_summary(_reporter(pytester))

    assert capsys.readouterr().out == ""


def test_the_summary_reports_an_empty_run_as_empty(
    pytester: pytest.Pytester, capsys: pytest.CaptureFixture[str]
) -> None:
    reporter = _reporter(pytester, "--n-plus-one")
    reporter.config.stash[plugin._FINDINGS_KEY] = {}

    plugin.pytest_terminal_summary(reporter)

    printed = capsys.readouterr().out
    assert "django-query-contract" in printed
    assert "No N+1: no statement shape repeated from a single call path." in printed


@pytest.mark.django_db
def test_the_capture_does_not_outlive_the_report_that_reads_it(
    request: pytest.FixtureRequest,
) -> None:
    """The capture is taken out of the stash, not read from it."""
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

    _run_call_hook(item, body)
    assert plugin._CAPTURE_KEY in item.stash

    _run_makereport(item, _make_report(item, "call", failing=True))

    assert plugin._CAPTURE_KEY not in item.stash


@pytest.mark.django_db
def test_a_passing_call_also_drops_its_capture(request: pytest.FixtureRequest) -> None:
    """The passing case is the one that matters, because it is nearly all of them."""
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

    _run_call_hook(item, body)
    _run_makereport(item, _make_report(item, "call", failing=False))

    assert plugin._CAPTURE_KEY not in item.stash


def test_the_plan_fixture_skips_where_a_plan_could_not_mean_anything(
    request: pytest.FixtureRequest,
) -> None:
    """The honest skip, driven through the fixture's own body."""
    generator = plugin._query_plans(request, plugin._query_plan_connections())

    with pytest.raises(Skipped) as skipped:
        next(generator)

    assert "Plan capture needs PostgreSQL" in str(skipped.value)


def test_the_plan_fixture_captures_and_leaves_the_capture_behind(
    request: pytest.FixtureRequest, pretend_postgres: str
) -> None:
    """The accepting half, and the stash that lets a failure gain a plan section."""
    item = _live_item(request)
    generator = plugin._query_plans(request, pretend_postgres)

    capture = next(generator)

    assert isinstance(capture, PlanCapture)
    assert item.stash[plugin._PLAN_KEY] is capture
    with pytest.raises(StopIteration):
        next(generator)


def test_the_connections_fixture_means_every_one_of_them_by_default() -> None:
    """``None`` is what ``PlanCapture`` reads as "every configured connection"."""
    assert plugin._query_plan_connections() is None


def test_a_failed_test_that_asked_for_plans_gains_a_plan_section(
    request: pytest.FixtureRequest,
) -> None:
    from django_query_contract import PlanCapture, QueryPlan, QueryRecord
    from tests.plan_payloads import SPILLED_SORT

    item = _live_item(request)
    capture = PlanCapture()
    capture._records = [
        QueryRecord(
            index=0,
            sql="SELECT id FROM testapp_book ORDER BY title",
            fingerprint="SELECT id FROM testapp_book ORDER BY title",
            alias="default",
            vendor="postgresql",
            many=False,
            param_count=None,
            plan=QueryPlan.from_explain(SPILLED_SORT, analyzed=True),
        )
    ]
    item.stash[plugin._PLAN_KEY] = capture

    report = _run_makereport(item, _make_report(item, "call", failing=True))

    names = [name for name, _ in report.sections]
    assert "django-query-contract plans" in names
    assert plugin._PLAN_KEY not in item.stash
    body = dict(report.sections)["django-query-contract plans"]
    assert "spilled to disk" in body


def test_a_passing_test_that_asked_for_plans_gains_nothing_and_drops_the_capture(
    request: pytest.FixtureRequest,
) -> None:
    """Same retention rule as the ordinary capture: the report is the only reader."""
    from django_query_contract import PlanCapture

    item = _live_item(request)
    item.stash[plugin._PLAN_KEY] = PlanCapture()

    report = _run_makereport(item, _make_report(item, "call", failing=False))

    assert report.sections == []
    assert plugin._PLAN_KEY not in item.stash


def test_a_failed_test_whose_plan_capture_saw_nothing_gains_no_empty_section(
    request: pytest.FixtureRequest,
) -> None:
    from django_query_contract import PlanCapture

    item = _live_item(request)
    item.stash[plugin._PLAN_KEY] = PlanCapture()

    report = _run_makereport(item, _make_report(item, "call", failing=True))

    assert [name for name, _ in report.sections] == []


@pytest.mark.django_db
def test_the_setup_hook_empties_the_log_so_one_test_cannot_charge_another(
    request: pytest.FixtureRequest, tiny_query_log: int
) -> None:
    """A log an earlier test filled makes this test's ceiling warning name this test."""
    connection.queries_log.extend(
        {"sql": "SELECT 1", "time": "0.000"} for _ in range(tiny_query_log)
    )
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _run_setup_hook(item)
        _run_call_hook(item, body)

    assert not [entry for entry in caught if entry.category is QueryLogCeilingWarning]
    assert item.stash[plugin._CAPTURE_KEY].ceilings[0].log_length_at_enter == 0


@pytest.mark.django_db
def test_a_block_that_outruns_the_log_by_itself_still_warns(
    request: pytest.FixtureRequest, tiny_query_log: int
) -> None:
    """The falsification of the test above: clearing the log hides nothing of its own."""
    item = _live_item(request)

    def body() -> None:
        with connection.cursor() as cursor:
            for _ in range(tiny_query_log + 2):
                cursor.execute("SELECT 1")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _run_setup_hook(item)
        _run_call_hook(item, body)

    (raised,) = [entry for entry in caught if entry.category is QueryLogCeilingWarning]
    assert "already held 0" in str(raised.message)


def test_the_flag_stands_the_setup_hook_down_too(pytester: pytest.Pytester) -> None:
    """A run with capture off is a run this package does not touch at all."""
    item = _item(pytester, "--no-query-contract")
    connection.queries_log.append({"sql": "SELECT 1", "time": "0.000"})

    try:
        _run_setup_hook(item)

        assert len(connection.queries_log) == 1
    finally:
        connection.queries_log.clear()


def test_the_setup_hook_leaves_a_project_without_django_settings_alone(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There are no connections to reset, and asking for them would raise."""
    item = _item(pytester)
    monkeypatch.setattr(settings, "_wrapped", empty)

    _run_setup_hook(item)
