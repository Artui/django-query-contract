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
from collections.abc import Generator
from typing import Any

import pytest
from django.conf import settings
from pluggy import Result

from django_query_contract.find_n_plus_one import find_n_plus_one
from django_query_contract.format_capture_report import format_capture_report
from django_query_contract.format_n_plus_one_summary import format_n_plus_one_summary
from django_query_contract.n_plus_one import NPlusOne
from django_query_contract.query_capture import QueryCapture
from django_query_contract.query_log_ceiling_warning import QueryLogCeilingWarning

_CAPTURE_KEY = pytest.StashKey[QueryCapture]()

# Findings gathered across the whole run, keyed by node id, for the end-of-run
# listing. On the config rather than in a module-level variable: the run owns
# them, and a module global would be shared by two sessions in one interpreter
# and survive into the next.
_FINDINGS_KEY = pytest.StashKey[dict[str, tuple[NPlusOne, ...]]]()

# What pytest prints above the failure section, as
# ``---- django-query-contract ----``, and above the end-of-run listing. One
# name for both, so a reader meets the package under the same heading twice.
_SECTION_NAME = "django-query-contract"


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
        default="25",
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
    if capture is None or not report.failed:
        return
    text = format_capture_report(capture)
    if text:
        report.sections.append((_SECTION_NAME, text))


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


def _enabled(config: pytest.Config) -> bool:
    """Whether to capture at all: the ini says normally, the flag says today."""
    if config.getoption("--no-query-contract"):
        return False
    return bool(config.getini("query_contract"))


def _stack_depth(config: pytest.Config) -> int:
    """The configured frame budget per query."""
    return int(config.getini("query_contract_stack_depth"))
