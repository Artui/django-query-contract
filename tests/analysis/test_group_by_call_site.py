from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from django_query_contract import QueryCapture, find_n_plus_one, group_by_call_site
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db


@pytest.fixture
def authors() -> list[Author]:
    """Three authors, two books each: enough for a loop to be visibly a loop."""
    made = [Author.objects.create(name=f"a{index}") for index in range(3)]
    for author in made:
        for index in range(2):
            Book.objects.create(author=author, title=f"b{index}")
    return made


def _books(author: Author) -> list[Book]:
    """A helper two different loops below both call. The query is emitted in here."""
    return list(author.books.all())


def test_one_line_is_one_attribution(authors: list[Author]) -> None:
    """The ordinary case: a loop's statements are attributed to the line in it."""
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())

    attributions = group_by_call_site(capture)
    assert [attribution.count for attribution in attributions] == [3, 1]
    assert attributions[0].call_site is not None
    assert attributions[0].call_site.filename == __file__


def test_a_statement_that_ran_once_is_attributed_too(authors: list[Author]) -> None:
    """The gap this milestone closes, stated as a test."""
    with QueryCapture(using="default") as capture:
        list(Author.objects.all())

    (attribution,) = group_by_call_site(capture)
    assert attribution.count == 1
    assert find_n_plus_one(capture) == ()
    assert attribution.call_site is not None
    assert attribution.call_site.filename == __file__


def test_two_callers_of_one_helper_merge_here_and_split_as_findings(
    authors: list[Author],
) -> None:
    """The whole display-versus-identity split, in one capture."""
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            _books(author)
        for author in Author.objects.all():
            _books(author)

    findings = find_n_plus_one(capture)
    assert [finding.count for finding in findings] == [3, 3]
    assert len({finding.stack for finding in findings}) == 2

    inside_helper = [
        attribution
        for attribution in group_by_call_site(capture)
        if attribution.call_site is not None and attribution.call_site.function == "_books"
    ]
    assert len(inside_helper) == 1
    assert inside_helper[0].count == 6


def test_every_statement_lands_in_exactly_one_group(authors: list[Author]) -> None:
    """The partition is total, which is what lets a report's counts add up."""
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())
        list(Book.objects.all())

    attributions = group_by_call_site(capture)
    grouped = [record for attribution in attributions for record in attribution.records]
    assert sorted(record.index for record in grouped) == [
        record.index for record in capture.records
    ]
    assert sum(attribution.count for attribution in attributions) == len(capture)


def test_one_line_that_ran_two_shapes_keeps_both(authors: list[Author]) -> None:
    """What a finding cannot hold: a finding is one shape by definition."""
    with QueryCapture(using="default") as capture:
        for model in (Author, Book):
            list(model.objects.filter(pk=1))

    (attribution,) = group_by_call_site(capture)
    assert attribution.count == 2
    assert len(attribution.fingerprints) == 2


def test_records_with_no_stack_are_grouped_under_no_call_site() -> None:
    """A capture rebuilt from a ``CaptureQueriesContext`` records no frames."""
    with CaptureQueriesContext(connection) as context:
        for _ in range(3):
            list(Author.objects.filter(pk=1))

    capture = QueryCapture.from_capture_context(context)
    (attribution,) = group_by_call_site(capture)
    assert attribution.call_site is None
    assert attribution.count == 3


def test_a_window_that_never_left_django_has_no_call_site(authors: list[Author]) -> None:
    """The second way a group can be unaddressed: depth one keeps an ORM frame."""
    with QueryCapture(using="default", stack_depth=1) as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    (attribution,) = group_by_call_site(capture)
    assert attribution.call_site is None
    assert attribution.count == 2


def test_addressed_and_unaddressed_statements_are_separate_groups(
    authors: list[Author],
) -> None:
    """Both kinds in one input, because a reader can hold both at once."""
    with CaptureQueriesContext(connection) as context:
        list(Author.objects.filter(pk=1))
    stackless = QueryCapture.from_capture_context(context)

    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    attributions = group_by_call_site([*capture.records, *stackless.records])
    assert [attribution.count for attribution in attributions] == [2, 1]
    assert attributions[0].call_site is not None
    assert attributions[1].call_site is None


def test_attributions_are_ordered_busiest_first(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
        for _ in range(4):
            list(Book.objects.filter(pk=1))
        for _ in range(3):
            list(Author.objects.filter(name="a0"))

    assert [attribution.count for attribution in group_by_call_site(capture)] == [4, 3, 2]


def test_lines_of_equal_size_are_ordered_by_where_they_started(
    authors: list[Author],
) -> None:
    """No two groups share a first statement, so the order is total."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Book.objects.filter(pk=1))
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert [attribution.first_index for attribution in group_by_call_site(capture)] == [0, 2]


def test_the_order_does_not_depend_on_the_order_records_arrive(
    authors: list[Author],
) -> None:
    """The tie-break has to be the tie-break, not a coincidence of bucket order."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Book.objects.filter(pk=1))
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    shuffled = [*capture.records[2:], *capture.records[:2]]
    assert [attribution.first_index for attribution in group_by_call_site(shuffled)] == [0, 2]


def test_a_capture_and_its_records_read_the_same(authors: list[Author]) -> None:
    """Any iterable of records, so a caller can narrow to one connection first."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert group_by_call_site(capture) == group_by_call_site(capture.records)


@pytest.mark.django_db(databases=["default", "other"])
def test_one_line_querying_two_databases_is_one_attribution() -> None:
    """The key is the line, and a line is one line whichever database it hit."""
    with QueryCapture() as capture:
        for alias in ("default", "other"):
            list(Author.objects.using(alias).filter(pk=1))

    (attribution,) = group_by_call_site(capture)
    assert attribution.count == 2
    assert attribution.aliases == ("default", "other")
