from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.stack_frame import StackFrame
from django_query_contract.utils import (
    innermost_frame_in_project,
    innermost_frame_outside_django,
)


@dataclass(frozen=True, slots=True)
class NPlusOne:
    """A repeated statement, and the one place it was repeated from."""

    fingerprint: str
    """The normalised SQL shared by every record here. See ``normalise_sql``."""

    stack: tuple[StackFrame, ...]
    """The call stack shared by every record here, outermost first."""

    records: tuple[QueryRecord, ...]
    """Every execution on this path, in capture order. Always at least two."""

    @property
    def count(self) -> int:
        """How many times the statement ran. The N in N+1, near enough."""
        return len(self.records)

    @property
    def call_site(self) -> StackFrame | None:
        """The innermost frame outside Django: the line to go and look at."""
        return innermost_frame_outside_django(self.stack)

    @property
    def project_call_site(self) -> StackFrame | None:
        """The innermost frame that is the reader's own: the line to go and edit."""
        return innermost_frame_in_project(self.stack)

    @property
    def aliases(self) -> tuple[str, ...]:
        """The connections this ran on, in the order they were first seen."""
        return tuple(dict.fromkeys(record.alias for record in self.records))

    @property
    def stack_truncated(self) -> bool:
        """``True`` when any execution here had frames dropped above the ones kept."""
        return any(record.stack_truncated for record in self.records)

    @property
    def first_index(self) -> int:
        """Position in the capture of the first execution on this path."""
        return self.records[0].index
