from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LogCeiling:
    """The arithmetic behind a query count that stops being true."""

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
        """How many more entries the log could hold when the capture opened."""
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
