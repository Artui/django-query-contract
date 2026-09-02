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
"""

from __future__ import annotations

import warnings
from collections.abc import Generator
from typing import Any

import pytest
from django.conf import settings
from pluggy import Result

from django_query_lens.format_capture_report import format_capture_report
from django_query_lens.query_capture import QueryCapture
from django_query_lens.query_log_ceiling_warning import QueryLogCeilingWarning

_CAPTURE_KEY = pytest.StashKey[QueryCapture]()

# What pytest prints above the block, as ``---- django-query-lens ----``.
_SECTION_NAME = "django-query-lens"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the on/off switch and the stack-depth knob."""
    parser.addini(
        "query_lens",
        "Capture queries around every test, so a failed query-count assertion "
        "can be diagnosed and a block above Django's query-log ceiling can be reported.",
        type="bool",
        default=True,
    )
    # A string rather than pytest's ``int`` type, which only exists from 8.4.
    parser.addini(
        "query_lens_stack_depth",
        "How many call-stack frames to keep per captured query.",
        default="25",
    )
    parser.getgroup("django-query-lens").addoption(
        "--no-query-lens",
        action="store_true",
        default=False,
        help="Turn capture off for this run without editing the ini file.",
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
    if report.when != "call" or not report.failed:
        return
    capture = item.stash.get(_CAPTURE_KEY, None)
    if capture is None:
        return
    text = format_capture_report(capture)
    if text:
        report.sections.append((_SECTION_NAME, text))


def _enabled(config: pytest.Config) -> bool:
    """Whether to capture at all: the ini says normally, the flag says today."""
    if config.getoption("--no-query-lens"):
        return False
    return bool(config.getini("query_lens"))


def _stack_depth(config: pytest.Config) -> int:
    """The configured frame budget per query."""
    return int(config.getini("query_lens_stack_depth"))
