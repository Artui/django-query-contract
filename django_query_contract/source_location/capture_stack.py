from __future__ import annotations

import inspect
import os

from django_query_contract.types.stack_frame import StackFrame

# The directory this package occupies. Frames inside it are dropped, so a caller
# never sees the capture machinery between itself and the query -- including the
# frame of this function. Computed once at import: it cannot change, and doing it
# per query would cost a path resolution on every execution.
#
# **Two dirnames, because this module sits one level down.** The value wanted is
# the package root, not this subpackage: the frames to drop are in
# ``capture/``, ``analysis/`` and ``reporting/`` as much as in this directory,
# and a root computed from ``__file__`` alone would name only
# ``source_location/`` and let every other one through. Nothing would raise --
# the caller would simply start seeing the machinery it asked not to see, which
# is why ``test_capture_stack.py`` pins the root against the package's own
# ``__file__`` rather than recomputing it the same way twice.
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep


def capture_stack(depth: int) -> tuple[tuple[StackFrame, ...], bool]:
    """Return the innermost ``depth`` frames outside this package, and whether more existed."""
    frame = inspect.currentframe()
    if frame is None:
        return (), False

    collected: list[StackFrame] = []
    truncated = False
    current = frame.f_back
    try:
        while current is not None:
            code = current.f_code
            filename = code.co_filename
            if not filename.startswith(_PACKAGE_ROOT):
                if len(collected) == depth:
                    truncated = True
                    break
                collected.append(
                    StackFrame(
                        filename=filename,
                        lineno=current.f_lineno,
                        function=code.co_name,
                    )
                )
            current = current.f_back
    finally:
        del frame, current

    collected.reverse()
    return tuple(collected), truncated
