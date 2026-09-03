"""How much of a block Django's own query log could still see."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LogCeiling:
    """The arithmetic behind a query count that stops being true.

    ``django.test.utils.CaptureQueriesContext`` -- which is what
    ``assertNumQueries`` and pytest-django's ``django_assert_num_queries`` both
    count with -- records ``len(connection.queries_log)`` on entry and on exit
    and returns the slice between them. But ``queries_log`` is a
    ``deque(maxlen=connection.queries_limit)``, 9000 by default, and once it
    rotates those two absolute indices no longer point at what they did.

    Measured against Django 6.1, with the count that context manager reports:

    | Already in the log | Queries in the block | Reported |
    | --- | --- | --- |
    | 0 | 8999 | 8999 |
    | 0 | 9001 | 9000 |
    | 8990 | 100 | 10 |
    | 9000 | 5 | 0 |

    The last row is the one that matters: five real queries, a reported count of
    zero, and ``django_assert_max_num_queries(1)`` passing. Django does emit a
    ``UserWarning`` when the log is full, so it is not perfectly silent -- but a
    warning in the summary beside a green test is not what a reader takes from a
    passing assertion, and the regime this happens in, thousands of queries in
    one block, is precisely the N+1-at-scale case worth catching.

    The capture in this package counts executions through
    ``connection.execute_wrapper``, which has no bound at all. This class is how
    it says so instead of quietly being right where the other is wrong.
    """

    alias: str
    """The Django connection alias these numbers describe."""

    limit: int | None
    """``connection.queries_limit``. ``None`` means the log is unbounded and there is no ceiling."""

    log_length_at_enter: int
    """``len(connection.queries_log)`` when the capture opened, itself capped at ``limit``."""

    executions: int
    """Statements this capture counted. Unbounded, and therefore the true number."""

    @property
    def headroom_at_enter(self) -> int | None:
        """How many more entries the log could hold when the capture opened.

        **Named for the moment it describes, because it never moves.** A capture
        reads ``len(connection.queries_log)`` on the way in and never again, so
        this number is fixed for the length of the block: four thousand
        statements later it still reports the room there was at the start.

        That is the right number rather than a stale one -- it is what
        :attr:`visible` needs, and it is the only one obtainable. Django writes a
        statement to the log only when the debug cursor is on, and a capture
        counts every execution through ``execute_wrapper`` whether it is or not,
        so how much of the log this block consumed cannot be derived from either
        end. What was wrong was the name, sitting beside a field already spelled
        ``log_length_at_enter``.

        ``None`` when the log is unbounded.
        """
        if self.limit is None:
            return None
        return max(self.limit - self.log_length_at_enter, 0)

    @property
    def visible(self) -> int:
        """What a ``CaptureQueriesContext`` opened at the same moment would report."""
        headroom = self.headroom_at_enter
        if headroom is None:
            return self.executions
        return min(self.executions, headroom)

    @property
    def exceeded(self) -> bool:
        """``True`` when a count taken from Django's query log would be too low."""
        return self.visible != self.executions
