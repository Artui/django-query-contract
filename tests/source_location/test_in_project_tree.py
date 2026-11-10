from __future__ import annotations

import os
from pathlib import Path

from django_query_contract import StackFrame, in_project_tree, relative_to_cwd


def _frame(filename: str) -> StackFrame:
    return StackFrame(filename=filename, lineno=1, function="f")


def test_a_frame_under_the_working_directory_is_the_projects() -> None:
    assert in_project_tree(_frame(str(Path(os.getcwd()) / "app" / "views.py")))


def test_a_frame_outside_the_working_directory_is_not() -> None:
    assert not in_project_tree(_frame("/somewhere/else/app/views.py"))


def test_an_installed_package_is_not_the_projects_even_inside_the_tree() -> None:
    vendored = Path(os.getcwd()) / ".venv" / "lib" / "site-packages" / "zeal" / "patch.py"

    assert not in_project_tree(_frame(str(vendored)))


def test_the_standard_library_is_not_the_projects_either() -> None:
    import contextlib

    assert not in_project_tree(_frame(contextlib.__file__))


def test_no_frame_is_not_the_projects() -> None:
    # The safe direction: an unplaceable finding stays out of the half a reader is told to act on.
    assert not in_project_tree(None)


def test_a_path_is_rendered_against_the_working_directory() -> None:
    inside = str(Path(os.getcwd()) / "app" / "views.py")

    assert relative_to_cwd(f"{inside}:31 in index") == "app/views.py:31 in index"


def test_a_path_outside_the_working_directory_is_left_alone() -> None:
    assert relative_to_cwd("/elsewhere/app.py:9 in f") == "/elsewhere/app.py:9 in f"
