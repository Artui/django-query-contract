"""The arithmetic of a query count that stops being true.

The table below is not invented. It is what ``CaptureQueriesContext`` actually
reports, measured against the installed Django in
``test_query_capture.py::test_the_ceiling_is_real``; this file asserts that
``LogCeiling`` models it, so the two can be compared and one of them can be
wrong out loud.
"""

from __future__ import annotations

import pytest

from django_query_contract import LogCeiling


@pytest.mark.parametrize(
    ("log_length_at_enter", "executions", "visible", "exceeded"),
    [
        (0, 50, 50, False),
        (0, 8999, 8999, False),
        # Exactly full: the last entry the log can hold, and still correct.
        (0, 9000, 9000, False),
        (0, 9001, 9000, True),
        (0, 20000, 9000, True),
        (8990, 100, 10, True),
        # The row that matters. Five real queries, a reported count of zero, and
        # django_assert_max_num_queries(1) passing.
        (9000, 5, 0, True),
    ],
)
def test_the_ceiling_table(
    log_length_at_enter: int, executions: int, visible: int, exceeded: bool
) -> None:
    ceiling = LogCeiling(
        alias="default",
        limit=9000,
        log_length_at_enter=log_length_at_enter,
        executions=executions,
    )
    assert ceiling.visible == visible
    assert ceiling.exceeded is exceeded
    assert ceiling.headroom_at_enter == 9000 - log_length_at_enter


def test_an_unbounded_log_has_no_ceiling() -> None:
    """``queries_limit`` can be raised, and a deque with ``maxlen=None`` never rotates."""
    ceiling = LogCeiling(alias="default", limit=None, log_length_at_enter=10, executions=10**6)
    assert ceiling.headroom_at_enter is None
    assert ceiling.visible == 10**6
    assert ceiling.exceeded is False


def test_the_headroom_never_goes_negative() -> None:
    """A log longer than its own limit is not a thing, but the arithmetic must not invent one."""
    ceiling = LogCeiling(alias="default", limit=9000, log_length_at_enter=9500, executions=1)
    assert ceiling.headroom_at_enter == 0
    assert ceiling.visible == 0


def test_the_headroom_is_named_for_the_moment_it_describes() -> None:
    """It is measured on the way in, and the old name did not say so.

    A capture reads ``len(connection.queries_log)`` when it opens and never
    again, so this number is fixed for the life of the block: four thousand
    statements later it still reports the room there was at the start. That is
    the right number -- it is the one the arithmetic below it needs, and the log
    length at exit is not recoverable, because Django only logs a statement when
    the debug cursor is on and a capture cannot tell how many of its executions
    were written down. What was wrong was calling it ``headroom``, beside a field
    already spelled ``log_length_at_enter``.
    """
    ceiling = LogCeiling(alias="default", limit=9000, log_length_at_enter=10, executions=4615)

    assert ceiling.headroom_at_enter == 8990
    assert not hasattr(ceiling, "headroom")
