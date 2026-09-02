"""The stack walk: what it keeps, what it drops, and what it admits to dropping."""

from __future__ import annotations

import inspect
import os

import django_query_contract
from django_query_contract import StackFrame, capture_stack

_PACKAGE_ROOT = os.path.dirname(os.path.abspath(django_query_contract.__file__)) + os.sep


def test_the_innermost_frame_is_the_caller() -> None:
    """Ordered outermost first, the way a traceback reads."""
    frames, truncated = capture_stack(50)
    assert not truncated
    innermost = frames[-1]
    assert innermost.function == "test_the_innermost_frame_is_the_caller"
    assert innermost.filename == os.path.abspath(__file__)
    assert isinstance(innermost, StackFrame)


def test_the_capture_machinery_is_not_in_its_own_output() -> None:
    """Nothing from this package appears between a caller and its query.

    Without this the innermost frames of every record would be the wrapper and
    the walk itself, and ``call_site`` would name this library on every query.
    """
    frames, _ = capture_stack(50)
    assert not any(frame.filename.startswith(_PACKAGE_ROOT) for frame in frames)


def _one() -> tuple[tuple[StackFrame, ...], bool]:
    return _two()


def _two() -> tuple[tuple[StackFrame, ...], bool]:
    return _three()


def _three() -> tuple[tuple[StackFrame, ...], bool]:
    return capture_stack(2)


def test_truncation_keeps_the_innermost_frames_and_says_so() -> None:
    """Depth cuts from the outside, because the information is on the inside.

    Between a cursor execution and the line that asked for it sit Django's own
    frames and then the caller. Trimming from the other end would drop exactly
    the frame worth reporting.
    """
    frames, truncated = _one()
    assert truncated
    assert [frame.function for frame in frames] == ["_two", "_three"]


def test_an_interpreter_without_frames_degrades_to_no_stack(monkeypatch) -> None:
    """Frame introspection is optional in Python, and its absence is not an error here.

    Every other face of the capture still works with an empty stack; a suite
    that only wanted a query count should not fail because the interpreter
    declines to hand out frames.
    """
    monkeypatch.setattr(inspect, "currentframe", lambda: None)
    assert capture_stack(10) == ((), False)
