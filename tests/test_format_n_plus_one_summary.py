"""The end-of-run listing: every finding from every block, worst first."""

from __future__ import annotations

import pytest

from django_query_contract import QueryCapture, find_n_plus_one, format_n_plus_one_summary
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db


@pytest.fixture
def authors() -> list[Author]:
    made = [Author.objects.create(name=f"a{index}") for index in range(3)]
    for author in made:
        Book.objects.create(author=author, title="b")
    return made


def test_nothing_found_is_said_out_loud() -> None:
    """The answer somebody ran this to get, so a blank screen will not do."""
    assert format_n_plus_one_summary({}) == (
        "No N+1: no statement shape repeated from a single call path."
    )


def test_every_finding_is_listed_with_the_block_it_came_from(
    authors: list[Author],
) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    summary = format_n_plus_one_summary({"tests/x.py::test_y": find_n_plus_one(capture)})
    assert summary.startswith("1 N+1 finding(s), most repeated first:")
    assert "  2 x  from " in summary
    assert "       in tests/x.py::test_y" in summary


def test_the_worst_finding_leads_whichever_block_it_came_from(
    authors: list[Author],
) -> None:
    with QueryCapture(using="default") as small:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
    with QueryCapture(using="default") as large:
        for _ in range(5):
            list(Book.objects.filter(pk=1))

    summary = format_n_plus_one_summary(
        {"first": find_n_plus_one(small), "second": find_n_plus_one(large)}
    )
    assert summary.index("5 x ") < summary.index("2 x ")


def test_equal_findings_are_ordered_by_block_name(authors: list[Author]) -> None:
    """The middle sort key, and the reason it is not decoration.

    Two blocks can produce findings of the same size that began at the same
    index in their own captures. Without the label between them the order would
    be whatever order the mapping happened to be built in.
    """
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
    findings = find_n_plus_one(capture)

    summary = format_n_plus_one_summary({"zebra": findings, "aardvark": findings})
    assert summary.index("in aardvark") < summary.index("in zebra")


def test_only_the_worst_are_listed(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
        for _ in range(3):
            list(Book.objects.filter(pk=1))
        for _ in range(4):
            list(Author.objects.filter(name="a0"))

    summary = format_n_plus_one_summary(
        {"tests/x.py::test_y": find_n_plus_one(capture)}, max_findings=1
    )
    assert "4 x " in summary
    assert "and 2 more findings." in summary


def test_a_long_statement_is_cut(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.all())

    findings = find_n_plus_one(capture)
    assert "... (truncated)" in format_n_plus_one_summary({"b": findings}, max_sql=20)
    assert "... (truncated)" not in format_n_plus_one_summary({"b": findings}, max_sql=10_000)


def test_one_call_path_seen_in_two_blocks_is_listed_twice(authors: list[Author]) -> None:
    """Not merged, on purpose.

    A finding's identity is its whole call stack, and two blocks are two stacks.
    Merging them would need a second grouping rule -- "these are the same one
    really" -- which is exactly the judgement this package is built without. The
    listing orders instead of merging.
    """
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
    findings = find_n_plus_one(capture)

    summary = format_n_plus_one_summary({"first": findings, "second": findings})
    assert summary.startswith("2 N+1 finding(s)")
    assert "in first" in summary
    assert "in second" in summary
