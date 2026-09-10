"""The innermost frame that is the reader's own, and where a report says it.

``call_site`` is the innermost frame outside *Django*, which is the right answer
to "what asked for this query" and the wrong one to "where do I go and look".
A query issued from inside ``transaction.atomic`` used as a decorator reaches
the database through ``contextlib``, and a library that monkeypatches the ORM
puts itself there instead. Both are true and neither is a line anybody edits.

Walking the stack for the nearest frame the reader owns is what a consumer ended
up writing by hand, and it is easy to write backwards: ``capture_stack`` keeps
the innermost frames but orders them **outermost-first**, so a walk from the
wrong end lands on the consumer's own ``execute_wrapper`` on every finding and
looks like a library bug rather than a consumer one.
"""

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
    # When the innermost non-Django frame is already the reader's, the two
    # answers agree, and a report that printed both would say one thing twice.
    with QueryCapture() as capture:
        for author in Author.objects.bulk_create([Author(name="a"), Author(name="b")]):
            list(author.books.all())

    findings = find_n_plus_one(capture)

    assert findings
    for finding in findings:
        assert finding.project_call_site == finding.call_site


def test_a_savepoint_loop_reports_the_line_that_ran_it() -> None:
    # The case the private rule got wrong. `call_site` is contextlib, and the
    # loop that opened a transaction per iteration is the reader's own.
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
    # Reported rather than approximated, for the reason `call_site` gives: a
    # frame that is not the reader's is not an address they can act on.
    with QueryCapture(stack_depth=1) as capture:
        list(Author.objects.all())
        list(Author.objects.all())

    for finding in find_n_plus_one(capture):
        assert finding.project_call_site is None


def test_the_listing_does_not_call_the_standard_library_an_installed_package(
    authors: list[Author],
) -> None:
    # `contextlib` is neither Django nor something the reader installed, and the
    # section it lands in used to claim both -- and to tell the reader they
    # could not fix it, about a loop of their own.
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
    # Sectioning still keys on the call site, because "any frame of yours in the
    # stack" is every finding a test runner ever produces. What changes is that
    # a finding filed outside says where the reader's own code enters it, so a
    # savepoint loop is findable instead of being filed under "not yours".
    with QueryCapture() as capture:
        for index in range(4):
            _save_one(index)
        for author in authors:
            list(author.books.all())

    listing = format_n_plus_one_summary({"block": find_n_plus_one(capture)})

    assert "reached from" in listing
    assert "test_project_call_site.py" in listing
