from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.stack_frame import StackFrame


@dataclass(frozen=True, slots=True)
class Attribution:
    """Every statement one line of code emitted, and that line."""

    call_site: StackFrame | None
    """The line that emitted every statement here. ``None`` when there was none to name."""

    records: tuple[QueryRecord, ...]
    """Every statement from that line, in capture order. Always at least one."""

    @property
    def count(self) -> int:
        """How many statements this line emitted."""
        return len(self.records)

    @property
    def fingerprints(self) -> tuple[str, ...]:
        """The distinct statement shapes emitted here, in the order first seen."""
        return tuple(dict.fromkeys(record.fingerprint for record in self.records))

    @property
    def aliases(self) -> tuple[str, ...]:
        """The connections these ran on, in the order they were first seen."""
        return tuple(dict.fromkeys(record.alias for record in self.records))

    @property
    def first_index(self) -> int:
        """Position in the capture of the first statement from this line."""
        return self.records[0].index
