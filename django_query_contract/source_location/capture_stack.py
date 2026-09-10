"""Walk the live call stack into plain frame records."""

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
    """Return the innermost ``depth`` frames outside this package, and whether more existed.

    Ordered outermost-first, the way a traceback reads. The *innermost* frames
    are the ones kept when the stack is deeper than ``depth``, because those are
    where the information is: between a cursor execution and the test function
    sit twenty-odd Django frames, and the call site this package exists to name
    is just outside them. Truncating from the other end would drop it.

    The boolean is the second half of that bargain. A truncated stack can hide
    the call site entirely, and this package's whole argument is that a
    measurement which quietly stops being true is worse than one that refuses --
    so truncation is reported rather than absorbed.

    Returns:
        The frames and a flag that is ``True`` when at least one more frame was
        available beyond ``depth``.
    """
    frame = inspect.currentframe()
    if frame is None:
        # Python implementations are not required to support frame
        # introspection, and an interpreter that declines returns None here
        # rather than raising. Every other face of this capture still works with
        # an empty stack, so this degrades to "no call site" instead of failing
        # a suite that was only asking for a query count.
        return (), False

    collected: list[StackFrame] = []
    truncated = False
    current = frame.f_back
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

    collected.reverse()
    return tuple(collected), truncated
