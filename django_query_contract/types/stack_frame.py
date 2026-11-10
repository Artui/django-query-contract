from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StackFrame:
    """Where a query came from, at one level of the call stack."""

    filename: str
    lineno: int
    function: str

    def __str__(self) -> str:
        """``path/to/file.py:31 in test_books`` -- one frame, one line."""
        return f"{self.filename}:{self.lineno} in {self.function}"
