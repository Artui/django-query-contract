"""Helpers used by more than one module in this package.

A one-file helper stays in the file that needs it, prefixed with an underscore.
This module is for the ones that are genuinely shared, and it holds no exported
symbol of its own -- nothing here is re-exported from ``__init__``.
"""

from __future__ import annotations

import os

import django

from django_query_contract.stack_frame import StackFrame

# Where Django itself lives. The walk below steps outwards until it leaves this
# directory, which is what turns twenty frames of queryset machinery into the one
# line a reader can act on. Resolved once at import rather than per query.
_DJANGO_ROOT = os.path.dirname(os.path.abspath(django.__file__)) + os.sep


def innermost_frame_outside_django(stack: tuple[StackFrame, ...]) -> StackFrame | None:
    """The deepest frame in ``stack`` that is not inside Django: the line that asked.

    Two things read this and they must agree, which is why it is here rather
    than duplicated: a :class:`~django_query_contract.QueryRecord` names the call
    site of one statement, and an :class:`~django_query_contract.NPlusOne` names
    the call site of the path it was found on. The second is the headline of a
    finding, and a finding whose call site disagreed with its own records' would
    be worse than one with no call site at all.

    Django is the only package skipped. Anything else in the stack -- a REST
    framework, a factory library, a service layer -- did emit the query, and
    deciding that some libraries are more interesting than others is the kind of
    tuning this package exists without.

    Returns:
        The frame, or ``None`` when every frame in the stack is Django's own or
        the stack is empty. ``None`` is reported rather than approximated with
        the innermost frame available, because "the query came from
        ``django/db/models/query.py``" is true of every query and tells a reader
        nothing.
    """
    for frame in reversed(stack):
        if not frame.filename.startswith(_DJANGO_ROOT):
            return frame
    return None
