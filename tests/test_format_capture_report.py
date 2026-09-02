"""The paragraph a reader gets underneath a failed query-count assertion.

Every capture here is a real one over a real connection, rather than a record
list assembled by hand. A formatter tested against a hand-built capture agrees
with whatever the test author believed the capture looked like, and the shape of
the thing it formats is exactly what is worth checking.
"""

from __future__ import annotations

import os

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from django_query_lens import QueryCapture, format_capture_report
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def authors() -> list[Author]:
    made = [Author.objects.create(name=f"a{index}") for index in range(3)]
    for author in made:
        Book.objects.create(author=author, title="b")
    return made


def test_a_capture_with_nothing_in_it_says_nothing() -> None:
    """No statements and no ceiling crossed means no section at all.

    A failure unrelated to the database should not acquire a paragraph about
    the database.
    """
    with QueryCapture(using="default") as capture:
        pass
    assert format_capture_report(capture) == ""


def test_a_repeated_shape_is_named_with_its_call_site(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())

    report = format_capture_report(capture)
    assert "4 statements captured: 4 on 'default'." in report
    assert "Repeated statement shapes:" in report
    assert "3 x  #1, #2, #3" in report
    assert '"testapp_book"."author_id" = %s' in report
    assert "1 shape(s) ran once." in report


def test_shapes_are_ordered_by_how_often_they_repeated(authors: list[Author]) -> None:
    """Most repeated first, then by first appearance so two runs agree."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
        for _ in range(5):
            list(Book.objects.filter(pk=1))

    report = format_capture_report(capture)
    assert report.index("5 x ") < report.index("2 x ")


def test_only_the_worst_shapes_are_listed(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
        for _ in range(3):
            list(Book.objects.filter(pk=1))
        for _ in range(4):
            list(Author.objects.filter(name="a0"))

    report = format_capture_report(capture, max_shapes=1)
    assert "4 x " in report
    assert "and 2 more repeated shapes." in report


def test_a_long_statement_is_cut_and_says_so(authors: list[Author]) -> None:
    """The record keeps the whole statement; the report keeps the reader's attention."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.all())

    report = format_capture_report(capture, max_sql=20)
    assert "... (truncated)" in report

    untruncated = format_capture_report(capture, max_sql=10_000)
    assert "... (truncated)" not in untruncated


def test_more_than_eight_repeats_are_elided(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(9):
            list(Author.objects.filter(pk=1))

    report = format_capture_report(capture)
    assert "9 x  #0, #1, #2, #3, #4, #5, #6, #7, ..." in report


def test_a_capture_without_stacks_says_where_it_could_not_look() -> None:
    """Reconstructed from a ``CaptureQueriesContext``, which records no frames.

    The report says so rather than leaving a blank where a call site should be:
    the missing half is the argument for capturing separately, not something to
    hide.
    """
    with CaptureQueriesContext(connection) as context:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    report = format_capture_report(QueryCapture.from_capture_context(context))
    assert "from no frame outside Django (stack empty or truncated)" in report


def test_the_ceiling_is_reported_before_anything_else(tiny_query_log: int) -> None:
    """The honest half leads, because it says whether the other half can be trusted."""
    with QueryCapture(using="default") as capture, connection.cursor() as cursor:
        for _ in range(tiny_query_log + 3):
            cursor.execute("SELECT 1")

    report = format_capture_report(capture)
    assert report.startswith("Query log ceiling exceeded on 'default': 8 statements executed")
    assert f"holds at most {tiny_query_log}" in report
    assert "they report zero for a block that ran queries" in report
    assert report.index("Query log ceiling") < report.index("statements captured")


def test_a_ceiling_with_no_statements_is_still_reported() -> None:
    """Impossible in practice, and the formatter must not depend on that."""

    class _Ceiling:
        alias = "default"
        limit = 5
        log_length_at_enter = 5
        executions = 3
        visible = 0
        exceeded = True

    capture = QueryCapture(using="default")
    with capture:
        pass
    # Reaching past the public surface once, to hold the two halves of the
    # report independent: the ceiling block must not require records, because a
    # future reader of this capture may build one that has none.
    capture._ceilings = (_Ceiling(),)
    report = format_capture_report(capture)
    assert report.startswith("Query log ceiling exceeded")
    assert "statements captured" not in report


def test_a_call_site_under_the_working_directory_is_shortened(
    authors: list[Author], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_REPO_ROOT)
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    report = format_capture_report(capture)
    assert "from tests/test_format_capture_report.py:" in report


def test_a_call_site_outside_it_keeps_its_absolute_path(
    authors: list[Author], monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``os.path.relpath`` would walk out with a row of dot-dots, which is worse."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    monkeypatch.chdir(tmp_path)
    report = format_capture_report(capture)
    assert f"from {os.path.abspath(__file__)}:" in report


def test_statements_are_counted_per_connection(authors: list[Author]) -> None:
    with QueryCapture() as capture:
        list(Author.objects.all())
    assert "1 statements captured: 1 on 'default'." in format_capture_report(capture)
