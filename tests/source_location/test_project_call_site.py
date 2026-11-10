from __future__ import annotations

import pytest
from django.db import transaction

from django_query_contract import (
    QueryCapture,
    find_n_plus_one,
    format_n_plus_one_summary,
)
from tests.testapp.models import Author

pytestmark = pytest.mark.django_db


@transaction.atomic
def _save_one(index: int) -> None:
    Author.objects.create(name=f"a{index}")


@pytest.fixture
def authors() -> list[Author]:
    return [Author.objects.create(name=f"a{index}") for index in range(3)]


def test_the_project_call_site_is_the_call_site_for_an_ordinary_loop() -> None:
    with QueryCapture() as capture:
        for author in Author.objects.bulk_create([Author(name="a"), Author(name="b")]):
            list(author.books.all())

    findings = find_n_plus_one(capture)

    assert findings
    for finding in findings:
        assert finding.project_call_site == finding.call_site


def test_a_savepoint_loop_reports_the_line_that_ran_it() -> None:
    # The case the private rule got wrong.
    with QueryCapture() as capture:
        for index in range(4):
            _save_one(index)

    savepoints = [
        finding for finding in find_n_plus_one(capture) if "SAVEPOINT" in finding.fingerprint
    ]

    assert savepoints, "expected the savepoint churn to be found"
    for finding in savepoints:
        assert finding.call_site is not None
        assert "contextlib" in finding.call_site.filename
        site = finding.project_call_site
        assert site is not None, "the reader's own frame is in the stack and should be reachable"
        assert site.filename == __file__


def test_a_stack_with_no_frame_of_the_readers_reports_none() -> None:
    with QueryCapture(stack_depth=1) as capture:
        list(Author.objects.all())
        list(Author.objects.all())

    for finding in find_n_plus_one(capture):
        assert finding.project_call_site is None


def test_the_listing_does_not_call_the_standard_library_an_installed_package(
    authors: list[Author],
) -> None:
    with QueryCapture() as capture:
        for index in range(4):
            _save_one(index)
        for author in authors:
            list(author.books.all())

    listing = format_n_plus_one_summary({"block": find_n_plus_one(capture)})

    assert "installed packages" not in listing
    assert "outside your working tree" in listing


def test_the_listing_names_the_readers_own_frame_in_the_outside_section(
    authors: list[Author],
) -> None:
    with QueryCapture() as capture:
        for index in range(4):
            _save_one(index)
        for author in authors:
            list(author.books.all())

    listing = format_n_plus_one_summary({"block": find_n_plus_one(capture)})

    assert "reached from" in listing
    assert "test_project_call_site.py" in listing
