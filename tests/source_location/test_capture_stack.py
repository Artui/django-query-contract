from __future__ import annotations

import gc
import inspect
import os
import weakref

import pytest

import django_query_contract
from django_query_contract import QueryCapture, StackFrame, capture_stack
from tests.testapp.models import Author

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
    """Nothing from this package appears between a caller and its query."""
    frames, _ = capture_stack(50)
    assert not any(frame.filename.startswith(_PACKAGE_ROOT) for frame in frames)


def _one() -> tuple[tuple[StackFrame, ...], bool]:
    return _two()


def _two() -> tuple[tuple[StackFrame, ...], bool]:
    return _three()


def _three() -> tuple[tuple[StackFrame, ...], bool]:
    return capture_stack(2)


def test_truncation_keeps_the_innermost_frames_and_says_so() -> None:
    """Depth cuts from the outside, because the information is on the inside."""
    frames, truncated = _one()
    assert truncated
    assert [frame.function for frame in frames] == ["_two", "_three"]


def test_an_interpreter_without_frames_degrades_to_no_stack(monkeypatch) -> None:
    """Frame introspection is optional in Python, and its absence is not an error here."""
    monkeypatch.setattr(inspect, "currentframe", lambda: None)
    assert capture_stack(10) == ((), False)


class _Witness:
    """A local whose lifetime a weak reference can watch; ``object()`` takes none."""


def _query_with_a_witness_in_a_local(depth: int) -> tuple[weakref.ref[_Witness], bool]:
    witness = _Witness()
    with QueryCapture(stack_depth=depth) as capture:
        Author.objects.count()
    (record,) = capture.records
    return weakref.ref(witness), record.stack_truncated


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("depth", "truncated"),
    [
        pytest.param(10_000, False, id="walk-runs-off-the-top"),
        pytest.param(1, True, id="walk-breaks-at-depth"),
    ],
)
def test_a_capture_frees_its_callers_locals_without_the_cycle_collector(
    depth: int, truncated: bool
) -> None:
    """A caller's locals die when the caller returns, not when the cyclic GC next runs."""
    gc.collect()
    gc.disable()
    try:
        witness, was_truncated = _query_with_a_witness_in_a_local(depth)
        assert was_truncated is truncated
        assert witness() is None
    finally:
        gc.enable()
