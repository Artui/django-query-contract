"""How one finding reads, from real captures.

The block a reader acts on. Both reports in the package render a finding through
this one function, so what is pinned here is what both of them print.
"""

from __future__ import annotations

import os

import pytest

from django_query_contract import QueryCapture, find_n_plus_one, format_n_plus_one
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def authors() -> list[Author]:
    made = [Author.objects.create(name=f"a{index}") for index in range(3)]
    for author in made:
        Book.objects.create(author=author, title="b")
    return made


def _one(capture: QueryCapture) -> str:
    (finding,) = find_n_plus_one(capture)
    return format_n_plus_one(finding)


def test_the_call_site_comes_before_the_sql(authors: list[Author]) -> None:
    """A count with no address is the output people turn off.

    The line somebody edits goes on the first line of the block, above the
    statement, because it is the only part of a finding anybody acts on.
    """
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())

    block = _one(capture)
    lines = block.splitlines()
    assert lines[0].startswith("  3 x  from ")
    assert __file__ in lines[0] or "tests/test_format_n_plus_one.py" in lines[0]
    assert '"testapp_book"."author_id" = %s' in lines[1]
    assert lines[2] == "       queries #1, #2, #3"


def test_a_label_is_named_under_the_call_site(authors: list[Author]) -> None:
    """Only present when the caller has more than one block to distinguish."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    (finding,) = find_n_plus_one(capture)
    assert "       in tests/x.py::test_y" in format_n_plus_one(finding, label="tests/x.py::test_y")
    assert "       in " not in format_n_plus_one(finding)


def test_more_than_eight_executions_are_elided(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(9):
            list(Author.objects.filter(pk=1))

    assert "queries #0, #1, #2, #3, #4, #5, #6, #7, ..." in _one(capture)


def test_a_long_statement_is_cut_and_says_so(authors: list[Author]) -> None:
    """The records keep the whole statement; the block keeps the reader's attention."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.all())

    (finding,) = find_n_plus_one(capture)
    assert "... (truncated)" in format_n_plus_one(finding, max_sql=20)
    assert "... (truncated)" not in format_n_plus_one(finding, max_sql=10_000)


def test_a_call_site_under_the_working_directory_is_shortened(
    authors: list[Author], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_REPO_ROOT)
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert "from tests/test_format_n_plus_one.py:" in _one(capture)


def test_a_call_site_outside_it_keeps_its_absolute_path(
    authors: list[Author], monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``os.path.relpath`` would walk out with a row of dot-dots, which is worse."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    monkeypatch.chdir(tmp_path)
    assert f"from {os.path.abspath(__file__)}:" in _one(capture)


def test_a_path_that_never_left_django_says_so_and_says_why(authors: list[Author]) -> None:
    """Depth one keeps the innermost frame, which is Django's own.

    The refusal names its cause. Without the second half a reader would be told
    a query arrived from nowhere, when what happened is that the window they
    configured did not reach far enough.
    """
    with QueryCapture(using="default", stack_depth=1) as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert "from no frame outside Django (the capture's stack depth did not reach one)" in _one(
        capture
    )


def test_an_ordinary_finding_carries_no_caveat_about_its_window(
    authors: list[Author],
) -> None:
    """``stack_truncated`` is true of every capture under a test runner.

    A query from a test function is 38 frames deep and 30 of them are pytest's
    and pluggy's own preamble, identical for every test in the session, so at
    any workable depth the flag is set and discriminates nothing. Printing it
    per finding would put a caveat on every line of every report -- which is how
    a caveat stops being read.
    """
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    (finding,) = find_n_plus_one(capture)
    assert finding.stack_truncated is True
    assert "truncated" not in format_n_plus_one(finding)


@pytest.mark.django_db(databases=["default", "other"])
def test_a_finding_spanning_two_connections_names_both() -> None:
    """The identity does not split on the alias, so the block has to report it."""
    with QueryCapture() as capture:
        for alias in ("default", "other"):
            list(Author.objects.using(alias).filter(pk=1))

    assert "       across connections 'default', 'other'" in _one(capture)


def test_a_finding_on_one_connection_does_not_mention_it(authors: list[Author]) -> None:
    """The common case stays short; the capture report already counts per alias."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert "across connections" not in _one(capture)
