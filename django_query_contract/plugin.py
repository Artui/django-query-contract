"""The pytest face of the capture: a diagnosis, and never an assertion.

This module is the one place in the package that is not a single exported
symbol, because pytest finds hooks by name in a module and there is nowhere else
to put them. It stays thin for that reason: every hook here decides *when* to
capture and *when* to speak, and hands the actual work to a module that can be
tested without a test runner in the loop.

The design decision it implements is that this package ships **no count
assertion**. ``django_assert_num_queries`` is the assertion -- it is typed, it
already handles ``connection=`` and ``using=`` and a custom failure note, and it
yields the captured queries. Wrapping it in a fixture of our own would
re-implement all of that to add a paragraph. So the seam is: their assertion,
our diagnosis, joined by a report section rather than by a wrapper.

The N+1 listing follows the same rule from the other side. It is opt-in, it
prints after the run rather than during it, and it changes no outcome -- because
an N+1 that fails a build is how a detector earns the reputation that gets it
uninstalled, and four of them are dead on PyPI already.
"""

from __future__ import annotations

import warnings
from collections.abc import Generator, Iterable
from typing import Any

import pytest
from django.conf import settings
from pluggy import Result

from django_query_contract.find_n_plus_one import find_n_plus_one
from django_query_contract.format_capture_report import format_capture_report
from django_query_contract.format_n_plus_one_summary import format_n_plus_one_summary
from django_query_contract.format_query_plans import format_query_plans
from django_query_contract.n_plus_one import NPlusOne
from django_query_contract.plan_capture import PlanCapture
from django_query_contract.query_capture import QueryCapture
from django_query_contract.query_log_ceiling_warning import QueryLogCeilingWarning
from django_query_contract.utils import DEFAULT_STACK_DEPTH

_CAPTURE_KEY = pytest.StashKey[QueryCapture]()

# The plan capture a test asked for through the ``query_plans`` fixture, so the
# report hook can put its findings under a failure. A second key rather than
# reusing the one above, because the two capture different windows: the hook's
# capture is the call phase, and a fixture's is everything set up after it.
_PLAN_KEY = pytest.StashKey[PlanCapture]()

# Findings gathered across the whole run, keyed by node id, for the end-of-run
# listing. On the config rather than in a module-level variable: the run owns
# them, and a module global would be shared by two sessions in one interpreter
# and survive into the next.
_FINDINGS_KEY = pytest.StashKey[dict[str, tuple[NPlusOne, ...]]]()

# What pytest prints above the failure section, as
# ``---- django-query-contract ----``, and above the end-of-run listing. One
# name for both, so a reader meets the package under the same heading twice.
_SECTION_NAME = "django-query-contract"

# The plan block is its own section rather than more lines in the one above,
# because the two describe different windows and a reader has to be able to tell
# which capture a statement came from.
_PLAN_SECTION_NAME = "django-query-contract plans"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the on/off switch and the stack-depth knob."""
    parser.addini(
        "query_contract",
        "Capture queries around every test, so a failed query-count assertion "
        "can be diagnosed and a block above Django's query-log ceiling can be reported.",
        type="bool",
        default=True,
    )
    # A string rather than pytest's ``int`` type, which only exists from 8.4.
    parser.addini(
        "query_contract_stack_depth",
        "How many call-stack frames to keep per captured query.",
        # Stringified from the one constant rather than written out again: an
        # ini default that drifted from the capture's own would make the plugin
        # quietly measure something different from a hand-written
        # ``QueryCapture``, which is the class of divergence this package exists
        # to complain about.
        default=str(DEFAULT_STACK_DEPTH),
    )
    group = parser.getgroup("django-query-contract")
    group.addoption(
        "--no-query-contract",
        action="store_true",
        default=False,
        help="Turn capture off for this run without editing the ini file.",
    )
    # Opt-in, and it stays opt-in. An N+1 printed under every passing test is
    # the crying wolf that killed four earlier detectors; a listing somebody
    # asked for cannot cry anything. It also fails nothing -- the exit status is
    # the same with the flag as without it.
    group.addoption(
        "--n-plus-one",
        action="store_true",
        default=False,
        help="List every N+1 found, worst first, at the end of the run. Changes no "
        "outcome. Needs capture, so it reports nothing under --no-query-contract.",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Result[Any], None]:
    """Capture around the test body, and say so when the block outran the log.

    Around the *call* phase only. The assertion this diagnoses is written inside
    the test, and widening capture to setup would fold every fixture's queries
    into the diagnosis of a block that did not run them.

    The ceiling is reported as a warning rather than a report section because
    the case that matters is a test that **passed**: past the ceiling
    ``django_assert_max_num_queries`` can be handed a zero for a block that ran
    five queries, and a section on a passing test is only printed when somebody
    already suspected something.
    """
    if not _enabled(item.config) or not settings.configured:
        # Installed in a suite with no Django settings, or switched off. Both
        # are ordinary, and neither is this plugin's business to complain about.
        yield
        return

    capture = QueryCapture(stack_depth=_stack_depth(item.config))
    item.stash[_CAPTURE_KEY] = capture
    with capture:
        yield
    if item.config.getoption("--n-plus-one"):
        # Gathered here rather than at the end of the run, because the capture
        # is the thing that gets read and a finding is the small part of it
        # worth keeping. ``setdefault`` runs even when this test found nothing,
        # so the listing can distinguish "asked, and there were none" from
        # "never asked" and say the first out loud.
        collected = item.config.stash.setdefault(_FINDINGS_KEY, {})
        findings = find_n_plus_one(capture)
        if findings:
            collected[item.nodeid] = findings
    for ceiling in capture.exceeded_ceilings:
        warnings.warn(
            f"{item.nodeid}: {ceiling.executions} statements ran on connection "
            f"'{ceiling.alias}', but connection.queries_log holds at most {ceiling.limit} "
            f"and already held {ceiling.log_length_at_enter}. A query count taken from it "
            f"-- which is what assertNumQueries and django_assert_num_queries both do -- "
            f"reports {ceiling.visible} for this block.",
            QueryLogCeilingWarning,
            stacklevel=1,
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Result[Any], None]:
    """Attach the diagnosis under a failed test.

    ``_assert_num_queries`` builds its message inline and calls ``pytest.fail()``,
    so there is no hook inside it to enrich. A report section reaches the same
    place -- underneath the stock failure -- without owning the failure, which
    means the user's assertion keeps working unchanged whether this package is
    installed or not.
    """
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return
    # Taken out of the stash, not read from it. pytest holds every collected
    # item in ``session.items`` until the run ends, so a capture left here is
    # retained for the whole session -- every statement's SQL and up to
    # ``stack_depth`` frames per statement, for every test that ran. Measured on
    # a synthetic suite at twenty queries a test: about 50 KiB per test, so 64
    # MiB across twelve hundred tests and growing linearly. This package asks to
    # be left on session-wide, which it can only honestly do if it does not
    # accumulate.
    #
    # Dropping it here rather than in teardown because this is the only reader:
    # the report section below is the last thing that wants it, and the
    # ``--n-plus-one`` listing already extracted its findings during the call
    # phase, keeping the small part worth keeping.
    capture = item.stash.get(_CAPTURE_KEY, None)
    if capture is not None:
        del item.stash[_CAPTURE_KEY]
    plans = item.stash.get(_PLAN_KEY, None)
    if plans is not None:
        del item.stash[_PLAN_KEY]
    if not report.failed:
        return
    if capture is not None:
        text = format_capture_report(capture)
        if text:
            report.sections.append((_SECTION_NAME, text))
    if plans is not None:
        planned = format_query_plans(plans)
        if planned:
            report.sections.append((_PLAN_SECTION_NAME, planned))


# ``Any`` rather than ``pytest.TerminalReporter``, which this package cannot
# name: that alias reached pytest's public namespace well after the 8.0 floor
# the plugin claims to work against, and the floor job proved the difference is
# not theoretical. The hook needs three things from it -- ``config``,
# ``write_sep`` and ``write_line`` -- all of which pytest 8.0 already had.
def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Print the run's N+1 findings, when somebody asked for them.

    Nothing here changes an outcome, and that is the design rather than a
    limitation. This package ships no assertion: ``django_assert_num_queries``
    is the assertion, and an N+1 that fails a build is how a detector earns the
    reputation that gets it uninstalled. A finding is a diagnosis attached to a
    failure somebody else's assertion produced, or -- here -- a list somebody
    asked to see.
    """
    collected = terminalreporter.config.stash.get(_FINDINGS_KEY, None)
    if collected is None:
        # Not asked for, or capture never ran. Either way, say nothing at all
        # rather than printing an empty section for every run of every suite.
        return
    terminalreporter.write_sep("=", _SECTION_NAME)
    terminalreporter.write_line(format_n_plus_one_summary(collected))


def _query_plan_connections() -> str | Iterable[str] | None:
    """Which connections ``query_plans`` captures. Override to name one.

    ``None`` means every configured connection, which is what
    :class:`~django_query_contract.PlanCapture` takes it to mean -- and every one
    of them then has to be PostgreSQL, because a capture that quietly skipped the
    connection it could not explain would be the silent gap that class exists to
    refuse.

    That is the right default and the wrong one for a project whose second
    database is a SQLite cache: there, every test asking for plans would skip
    with a true sentence about a connection nobody meant. Overriding this
    fixture in a ``conftest.py`` is the answer, and it is a fixture rather than
    an ini setting because the projects that need it are the ones that already
    override ``django_db_setup`` next to it.

    ```python
    # conftest.py
    import pytest


    @pytest.fixture
    def query_plan_connections():
        return "default"
    ```
    """
    return None


query_plan_connections = pytest.fixture(name="query_plan_connections")(_query_plan_connections)


def _query_plans(
    request: Any, query_plan_connections: str | Iterable[str] | None
) -> Generator[PlanCapture, None, None]:
    """Capture query plans around this test, or skip it with the reason there are none.

    ```python
    def test_the_dashboard_plan(db, orders, query_plans):
        dashboard()

        assert not query_plans.unanalyzed_relations
    ```

    Which connections it covers comes from the ``query_plan_connections``
    fixture, so a project whose second database is not PostgreSQL can name the
    one it means instead of skipping every plan test.

    Yields a :class:`~django_query_contract.PlanCapture` entered around
    everything set up after this fixture and around the test body, so the
    statements a later fixture runs are captured too.

    **The skip is the point of the fixture, and it is the only way this package
    offers to get one.** Plan capture is PostgreSQL-only, and on any other
    backend :class:`~django_query_contract.PlanCapture` raises rather than
    yielding an empty capture -- an empty plan capture is indistinguishable from
    a healthy one, so an assertion over it would pass because the backend could
    not check it. A raise in a fixture is an *error*, though, and a suite that
    errors on SQLite is a suite nobody runs. So the refusal arrives here as a
    skip carrying the same sentence: a test that never ran is honest.

    The capture is also left on the item, so a failing test gains a plan section
    underneath the failure without the test having to print anything.

    A plain generator function rather than the fixture itself, so this whole body
    is reachable from a test that drives it directly. pytest 9 wraps a fixture in
    an object that cannot be called, and a wrapper of one line here would be one
    line no coverage gate could reach.
    """
    capture = PlanCapture(using=query_plan_connections, stack_depth=_stack_depth(request.config))
    refusal = capture.refusal()
    if refusal is not None:
        pytest.skip(refusal)
    request.node.stash[_PLAN_KEY] = capture
    with capture:
        yield capture


query_plans = pytest.fixture(name="query_plans")(_query_plans)


def _enabled(config: pytest.Config) -> bool:
    """Whether to capture at all: the ini says normally, the flag says today."""
    if config.getoption("--no-query-contract"):
        return False
    return bool(config.getini("query_contract"))


def _stack_depth(config: pytest.Config) -> int:
    """The configured frame budget per query."""
    return int(config.getini("query_contract_stack_depth"))
