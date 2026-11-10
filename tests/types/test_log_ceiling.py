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
    """It is measured on the way in, and the old name did not say so."""
    ceiling = LogCeiling(alias="default", limit=9000, log_length_at_enter=10, executions=4615)

    assert ceiling.headroom_at_enter == 8990
    assert not hasattr(ceiling, "headroom")
