from __future__ import annotations

import os

from django_query_contract.types.stack_frame import StackFrame

# Where installed dependencies live. A path component rather than a prefix,
# because a virtualenv inside the project is the ordinary layout and the
# directory is then *under* the working directory rather than outside it.
_INSTALLED_MARKERS = (os.sep + "site-packages" + os.sep, os.sep + "dist-packages" + os.sep)


def in_project_tree(frame: StackFrame | None) -> bool:
    """Whether this frame is code the reader can edit, rather than a dependency."""
    if frame is None:
        return False
    path = os.path.abspath(frame.filename)
    if any(marker in path for marker in _INSTALLED_MARKERS):
        return False
    return path.startswith(os.getcwd() + os.sep)


__all__ = ["in_project_tree"]
