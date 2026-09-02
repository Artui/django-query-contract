"""One frame of the call stack that emitted a query."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StackFrame:
    """Where a query came from, at one level of the call stack.

    Deliberately three plain strings and an integer rather than a reference to a
    live frame object: a captured stack outlives the call it describes, and
    holding frames would keep every local variable of every ORM call alive for
    the length of a test. It would also make the record unpickleable, which the
    CI-report face needs it not to be.

    The source line is not read either. ``traceback.extract_stack`` opens and
    caches the file for every frame it formats, and this runs once per query in
    a suite that may execute hundreds of thousands of them.
    """

    filename: str
    lineno: int
    function: str

    def __str__(self) -> str:
        """``path/to/file.py:31 in test_books`` -- one frame, one line."""
        return f"{self.filename}:{self.lineno} in {self.function}"
