"""Attribution, against real captures over a real connection.

Every capture here is produced by running the code that produces it, for the
reason ``test_find_n_plus_one.py`` gives: a grouping tested against a
hand-assembled record list agrees with whatever its author believed a stack
looks like, and the shape of a real stack is part of the claim being made.

The load-bearing test in this file is the one that runs the same capture through
both readings at once. Attribution merges call paths a finding keeps apart, on
purpose, and nothing but a test can hold the two apart as the code moves.
"""

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
    """The gap this milestone closes, stated as a test.

    A finding needs a repetition, so before attribution existed a capture named
    a call site only where something had repeated. One query from one line is
    not a defect and never will be a finding -- and "where did this come from"
    still has an answer.
    """
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
    """The whole display-versus-identity split, in one capture.

    Both loops emit their query from the same line inside ``_books``. As
    *findings* that is two defects with two fixes, and the identity is the whole
    stack precisely so a report never points at the helper's line, which is the
    one line that is fine. As *attribution* the honest answer is that line: it
    is where the statements were emitted, and both call paths really did emit
    them there.

    So the merge this makes is deliberate, and it is only safe because an
    attribution claims nothing about defects. If this ever starts returning two
    groups, attribution has quietly grown a rule about which frames matter -- and
    if ``find_n_plus_one`` ever starts returning one, the identity has quietly
    become the call site.
    """
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
    """The partition is total, which is what lets a report's counts add up.

    A grouping that dropped what it could not place would be the silently
    incomplete measurement this package exists to complain about -- and it would
    be silent here in particular, because the dropped statements are the ones a
    reader has no other way to see.
    """
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
    """A capture rebuilt from a ``CaptureQueriesContext`` records no frames.

    The detector skips these, because bucketing them would manufacture a finding
    out of a gap in the input. Attribution keeps them, because grouping them
    under "no call site" manufactures nothing -- it says exactly what is known,
    which is that nothing is.
    """
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
    """Both kinds in one input, because a reader can hold both at once.

    Any iterable of records is accepted, so a caller comparing a capture with
    one rebuilt from the fixture's ``CaptureQueriesContext`` can attribute the
    two together -- and the half that has stacks keeps its call sites rather
    than being dragged down to the half that has none.
    """
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
    """No two groups share a first statement, so the order is total.

    Without this the two below would be ordered by however the buckets happened
    to be built, and a report would reshuffle between two runs over one capture.
    """
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Book.objects.filter(pk=1))
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert [attribution.first_index for attribution in group_by_call_site(capture)] == [0, 2]


def test_the_order_does_not_depend_on_the_order_records_arrive(
    authors: list[Author],
) -> None:
    """The tie-break has to be the tie-break, not a coincidence of bucket order.

    The test above cannot tell the two apart. Buckets are built in first-seen
    order and ``list.sort`` is stable, so with records arriving in capture order
    a sort on the count alone lands equal-sized groups in ``first_index`` order
    anyway -- and would keep doing so if the tie-break were deleted. Any
    iterable of records is accepted, so handing them over out of order separates
    what the code promises from what the dict happened to do.
    """
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
