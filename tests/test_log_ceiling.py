"""The arithmetic of a query count that stops being true.

The table below is not invented. It is what ``CaptureQueriesContext`` actually
reports, measured against the installed Django in
``test_query_capture.py::test_the_ceiling_is_real``; this file asserts that
``LogCeiling`` models it, so the two can be compared and one of them can be
wrong out loud.
"""

from __future__ import annotations

import pytest

from django_query_lens import LogCeiling


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
    assert ceiling.headroom == 9000 - log_length_at_enter


def test_an_unbounded_log_has_no_ceiling() -> None:
    """``queries_limit`` can be raised, and a deque with ``maxlen=None`` never rotates."""
    ceiling = LogCeiling(alias="default", limit=None, log_length_at_enter=10, executions=10**6)
    assert ceiling.headroom is None
    assert ceiling.visible == 10**6
    assert ceiling.exceeded is False


def test_headroom_never_goes_negative() -> None:
    """A log longer than its own limit is not a thing, but the arithmetic must not invent one."""
    ceiling = LogCeiling(alias="default", limit=9000, log_length_at_enter=9500, executions=1)
    assert ceiling.headroom == 0
    assert ceiling.visible == 0
