"""Which frames are the reader's own, as a rule a consumer can call.

The rule existed before this and was private, which meant a consumer writing
its own report had to reimplement it -- and one did, because the nearest public
thing (``call_site``, the innermost frame outside *Django*) lands on
``contextlib`` when the query came from inside ``transaction.atomic`` and on a
library that monkeypatches the ORM in place. Both answers are truthful and
neither is useful in a report.

That left the definition of "our code" in two places that can disagree: what the
run-wide listing prints, and what a consumer's own report prints, for the same
finding from the same capture. ``utils.py`` already carries the rule that a
record, a finding and an attribution must not disagree about where a statement
came from; a consumer is one more reader of the same answer.
"""

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
    # A virtualenv inside the project is the ordinary layout, so the marker is a
    # path component rather than a prefix: site-packages is under the working
    # directory and is still not the reader's code.
    vendored = Path(os.getcwd()) / ".venv" / "lib" / "site-packages" / "zeal" / "patch.py"

    assert not in_project_tree(_frame(str(vendored)))


def test_the_standard_library_is_not_the_projects_either() -> None:
    # The case that sends a savepoint loop into the wrong half of a report:
    # `transaction.atomic` used as a decorator puts contextlib between the
    # caller and the query, and contextlib is neither Django nor a package the
    # reader installed.
    import contextlib

    assert not in_project_tree(_frame(contextlib.__file__))


def test_no_frame_is_not_the_projects() -> None:
    # The safe direction: an unplaceable finding stays out of the half a reader
    # is told to act on.
    assert not in_project_tree(None)


def test_a_path_is_rendered_against_the_working_directory() -> None:
    inside = str(Path(os.getcwd()) / "app" / "views.py")

    assert relative_to_cwd(f"{inside}:31 in index") == "app/views.py:31 in index"


def test_a_path_outside_the_working_directory_is_left_alone() -> None:
    # Nothing is shortened that a reader could not then find: an absolute path
    # elsewhere is the only useful spelling of a frame in a dependency.
    assert relative_to_cwd("/elsewhere/app.py:9 in f") == "/elsewhere/app.py:9 in f"
