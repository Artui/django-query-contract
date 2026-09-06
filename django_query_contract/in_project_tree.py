"""Whether a captured frame is code the reader can edit."""

from __future__ import annotations

import os

from django_query_contract.stack_frame import StackFrame

# Where installed dependencies live. A path component rather than a prefix,
# because a virtualenv inside the project is the ordinary layout and the
# directory is then *under* the working directory rather than outside it.
_INSTALLED_MARKERS = (os.sep + "site-packages" + os.sep, os.sep + "dist-packages" + os.sep)


def in_project_tree(frame: StackFrame | None) -> bool:
    """Whether this frame is code the reader can edit, rather than a dependency.

    **A display rule, and it must stay one.** Which frames matter is exactly the
    judgement that becomes a knob, and a knob in a detector's identity is how
    the four dead N+1 detectors came to cry wolf -- so no finding is created,
    merged, dropped or renamed by this. It decides the order two findings are
    printed in and nothing else.

    The question it exists for is not the one a finding answers. A finding says
    *this statement repeated from this path*, and every statement is in scope for
    that. A run-wide listing says *what should I go and fix*, and inherits an
    ordering -- raw repetition count -- under which any library that loops
    outranks every defect in the project. Measured on a consumer's suite: 158
    findings, and none of the ones it had room to print were in the application.

    The rule is the working directory minus installed packages, and it is
    deliberately that crude: no project root setting, no package name, nothing
    to configure and so nothing to be wrong about. A frame with no filename we
    can place is treated as **not** the project's, which is the safe direction
    -- it keeps an unplaceable finding out of the section a reader is told to
    act on.
    """
    if frame is None:
        return False
    path = os.path.abspath(frame.filename)
    if any(marker in path for marker in _INSTALLED_MARKERS):
        return False
    return path.startswith(os.getcwd() + os.sep)


__all__ = ["in_project_tree"]
