"""Helpers used by more than one module in this package.

A one-file helper stays in the file that needs it, prefixed with an underscore.
This module is for the ones that are genuinely shared, and it holds no exported
symbol of its own -- nothing here is re-exported from ``__init__``.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TypeAlias

import django

from django_query_contract.stack_frame import StackFrame

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


def relative_to_cwd(text: str) -> str:
    """Shorten a rendered call site to a path relative to the working directory.

    Only when it is under it: ``os.path.relpath`` will happily walk out of the
    tree with a row of ``..`` segments, which is longer than the absolute path
    and harder to read.

    Here for the same reason as the frame choice above. Two renderings name a
    call site now -- a finding's block and an attribution's -- and a reader
    shown one path abbreviated and the other absolute would reasonably wonder
    whether they were the same file.
    """
    root = os.getcwd() + os.sep
    if text.startswith(root):
        return text[len(root) :]
    return text


def row_count(value: float | None) -> str:
    """A row count as a reader wants it, or the fact that it was never measured.

    Shared by both plan renderings for the reason ``shorten`` is: a number that
    PostgreSQL did not measure has to read the same way in every block, or a
    reader meets "not measured" in one paragraph and a bare dash in the next and
    has to work out whether they mean the same thing.
    """
    return "not measured" if value is None else f"{value:,.0f}"


def loops_note(loops: float | None, *, parallel_aware: bool) -> str | None:
    """Name how many times a node ran and why, or ``None`` when it ran once.

    Here rather than in either formatter because both of them print a per-loop
    number beside a total, and a reader shown "3 loops (parallel workers)" in one
    block and "run three times" in another would reasonably wonder whether the
    two blocks were describing the same node.

    **The parenthesis is the part that carries information.** A loop count above
    one has two unrelated causes and the plan states which: a parallel-aware node
    ran once in each participating process, so the work was *divided*; any other
    node with loops ran once per row of the outer side of a join, so the work was
    *repeated*. Both totalise the same way, and only one of them also puts the
    estimate on a different scale from the measurement -- see
    :attr:`~django_query_contract.PlanNode.estimate_error`.

    Args:
        loops: ``Actual Loops``. ``None`` on a plan taken without ``ANALYZE``,
            where there is no count and therefore nothing to say.
        parallel_aware: Whether PostgreSQL marked the node ``Parallel Aware``.

    Returns:
        A phrase like ``3 loops (parallel workers)``, or ``None`` when the node
        ran once or was never measured -- which is the case a caller wants to
        print nothing at all for, rather than "1 loop".
    """
    if loops is None or loops <= 1.0:
        return None
    cause = "parallel workers" if parallel_aware else "once per row of the outer side"
    return f"{loops:,.0f} loops ({cause})"


def shorten(text: str, limit: int) -> str:
    """Cut a statement to ``limit`` characters, saying that it was cut.

    Shared by both renderings of a statement, so ``max_sql`` means one thing
    across a report rather than one thing per block in it.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + " ... (truncated)"
