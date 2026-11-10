from __future__ import annotations

import os
from pathlib import Path

import django
import pytest

from django_query_contract import (
    NPlusOne,
    QueryCapture,
    QueryRecord,
    StackFrame,
    find_n_plus_one,
    format_n_plus_one_summary,
)
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
    """The middle sort key, and the reason it is not decoration."""
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
    """Not merged, on purpose."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
    findings = find_n_plus_one(capture)

    summary = format_n_plus_one_summary({"first": findings, "second": findings})
    assert summary.startswith("2 N+1 finding(s)")
    assert "in first" in summary
    assert "in second" in summary


def _finding(*, filename: str, count: int, label: str) -> tuple[str, NPlusOne]:
    """One finding with its call site placed in a named file."""
    stack = (StackFrame(filename=filename, lineno=1, function="loop"),)
    records = tuple(
        QueryRecord(
            index=index,
            sql="SELECT 1",
            fingerprint="SELECT %s",
            alias="default",
            vendor="postgresql",
            many=False,
            param_count=0,
            stack=stack,
            stack_truncated=False,
            plan=None,
        )
        for index in range(count)
    )
    return label, NPlusOne(fingerprint="SELECT %s", stack=stack, records=records)


def test_findings_in_your_own_code_come_first_however_small(tmp_path: Path) -> None:
    """The finding the whole section exists for."""
    mine = os.path.join(os.getcwd(), "shop", "views.py")
    theirs = os.path.join(os.getcwd(), ".venv", "lib", "site-packages", "lib", "relay.py")

    summary = format_n_plus_one_summary(
        {
            "t::a": [_finding(filename=theirs, count=40, label="t::a")[1]],
            "t::b": [_finding(filename=mine, count=2, label="t::b")[1]],
        }
    )

    assert "2 N+1 finding(s), most repeated first:" in summary
    assert "1 in your own code:" in summary
    assert "1 outside your working tree:" in summary
    assert "40 x  from " in summary
    assert summary.index("shop/views.py") < summary.index("relay.py")


def test_a_run_with_only_dependency_findings_is_not_given_a_heading() -> None:
    """Two sections are worth naming; one is just a list."""
    theirs = os.path.join(os.getcwd(), ".venv", "lib", "site-packages", "lib", "relay.py")

    summary = format_n_plus_one_summary(
        {"t::a": [_finding(filename=theirs, count=3, label="t::a")[1]]}
    )

    assert "in your own code" not in summary
    assert "outside your working tree" not in summary
    assert "3 x  from " in summary


def test_a_findings_own_ordering_is_unchanged_inside_a_section() -> None:
    """Worst first still holds; only the partition is new."""
    mine = os.path.join(os.getcwd(), "shop", "views.py")
    other = os.path.join(os.getcwd(), "shop", "reports.py")

    summary = format_n_plus_one_summary(
        {
            "t::a": [_finding(filename=mine, count=3, label="t::a")[1]],
            "t::b": [_finding(filename=other, count=9, label="t::b")[1]],
        }
    )

    assert summary.index("shop/reports.py") < summary.index("shop/views.py")


def test_a_finding_with_no_placeable_call_site_is_not_called_yours() -> None:
    """A stack that is entirely Django's has no call site at all."""
    django_only = os.path.join(os.path.dirname(django.__file__), "db", "models", "query.py")
    mine = os.path.join(os.getcwd(), "shop", "views.py")

    summary = format_n_plus_one_summary(
        {
            "t::a": [_finding(filename=django_only, count=40, label="t::a")[1]],
            "t::b": [_finding(filename=mine, count=1, label="t::b")[1]],
        }
    )

    assert "1 in your own code:" in summary
    assert "1 outside your working tree:" in summary
    assert summary.index("shop/views.py") < summary.index("outside your working tree")
