from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TypeAlias

import django

from django_query_contract.source_location.in_project_tree import in_project_tree
from django_query_contract.types.stack_frame import StackFrame

# Measured rather than guessed: six frames separate ``cursor.execute`` from the
# line that iterated a queryset, so twenty-five leaves nineteen for whatever
# application code sits above it -- a view, a service, a serializer -- and still
# reaches the call site. The frames beyond that, under pytest, are the runner's
# own and identical for every query in the suite. Depth is the one part of
# capture whose cost scales, at roughly half a microsecond per frame, so the
# default is the smallest number that keeps what a reader can act on.
#
# Here rather than in ``query_capture`` because three places need the same
# number now: the capture itself, the growth harness that opens one per scale
# factor, and the pytest plugin's ini default. Three literals would be three
# chances for one of them to drift.
DEFAULT_STACK_DEPTH = 25

# What a growth assertion asks a world for: make the world be at this factor,
# then let the caller run its block, then undo it. The yielded number is how
# many rows the world actually holds, a diagnostic rather than the curve's
# x-axis.
#
# **A structural type rather than a dependency, deliberately.** This is exactly
# ``django_data_shape.scale_protocol.ScaleProtocol``, and it is spelled out here
# instead of imported because the growth assertion depends on the *shape* of
# that call and not on the package that named it. django-data-shape builds a
# world with ``COPY`` and column statistics where the backend has them, which is
# the right implementation for a project that has adopted it -- and most Django
# suites run SQLite and have not. Anything callable as ``world(factor)``
# returning a context manager satisfies this, including a five-line
# ``@contextmanager`` in a project's own conftest, so the assertion works
# unchanged either way.
#
# The factor is positional because ``Callable`` has no parameter names at all:
# an implementation may spell its argument whatever reads best, which is the
# same property ``ScaleProtocol`` buys with a ``/``.
ScaleWorld: TypeAlias = Callable[[int], AbstractContextManager[int]]

# One small world and one ten times bigger: the default sizes a growth
# assertion measures at. Two points, because the rules a growth claim is made
# of are exact comparisons over a pair and a third point tells them nothing a
# second one did not, and a tenfold spread because it is the smallest one no
# batching can hide -- a per-row statement over ten times the rows lands nine
# times the base count away from constant, while doubling can fall inside a
# single ``bulk_create`` batch and produce the same count twice. Both worlds
# stay in the hundreds-of-rows regime a growth assertion is for, where a build
# is milliseconds.
#
# Shared for the same reason as the stack depth above: the measurement and the
# assertion over it both need a default, and two defaults for one thing is how
# they come to disagree -- silently, because both would be valid factor lists.
DEFAULT_FACTORS = (1, 10)

# Where Django itself lives. The walk below steps outwards until it leaves this
# directory, which is what turns twenty frames of queryset machinery into the one
# line a reader can act on. Resolved once at import rather than per query.
_DJANGO_ROOT = os.path.dirname(os.path.abspath(django.__file__)) + os.sep


def innermost_frame_outside_django(stack: tuple[StackFrame, ...]) -> StackFrame | None:
    """The deepest frame in ``stack`` that is not inside Django: the line that asked."""
    for frame in reversed(stack):
        if not frame.filename.startswith(_DJANGO_ROOT):
            return frame
    return None


def innermost_frame_in_project(stack: tuple[StackFrame, ...]) -> StackFrame | None:
    """The deepest frame in ``stack`` that is the reader's own: the line to edit."""
    for frame in reversed(stack):
        if in_project_tree(frame):
            return frame
    return None


def row_count(value: float | None) -> str:
    """A row count as a reader wants it, or the fact that it was never measured."""
    return "not measured" if value is None else f"{value:,.0f}"


def loops_note(loops: float | None, *, parallel_aware: bool) -> str | None:
    """Name how many times a node ran and why, or ``None`` when it ran once."""
    if loops is None or loops <= 1.0:
        return None
    cause = "parallel workers" if parallel_aware else "once per row of the outer side"
    return f"{loops:,.0f} loops ({cause})"


def shorten(text: str, limit: int) -> str:
    """Cut a statement to ``limit`` characters, saying that it was cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + " ... (truncated)"
