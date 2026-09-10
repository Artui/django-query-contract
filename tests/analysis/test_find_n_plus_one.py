"""The detector, against real captures over a real connection.

Every capture here is produced by running the code that produces it. A detector
tested against a hand-assembled record list agrees with whatever its author
believed a stack looks like, and the shape of a real stack -- how many frames
Django puts between a loop and a cursor, and whether two iterations of one loop
really do arrive with identical frames -- is the entire claim being made.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from django_query_contract import QueryCapture, find_n_plus_one
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
    """A helper two different loops below both call. The N+1 is not in here."""
    return list(author.books.all())


def test_one_loop_is_one_finding(authors: list[Author]) -> None:
    """The defect the package exists for, and the constraint that it stay one thing.

    Three iterations, three statements, one finding. Every iteration of a loop
    enters the query through the same frames at the same lines, which is what
    makes the whole stack safe to use as an identity.
    """
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())

    (finding,) = find_n_plus_one(capture)
    assert finding.count == 3
    assert finding.call_site is not None
    assert finding.call_site.filename == __file__
    assert finding.aliases == ("default",)


def test_the_same_statement_from_two_lines_is_two_findings(authors: list[Author]) -> None:
    """What the fingerprint alone cannot do.

    Identical SQL, identical fingerprint, two loops. Grouping on the fingerprint
    would report one finding of five and attach it to whichever line was seen
    first, which is a report pointing at a line that is only half the problem.
    """
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
        for _ in range(3):
            list(Author.objects.filter(pk=1))

    findings = find_n_plus_one(capture)
    assert [finding.count for finding in findings] == [3, 2]
    assert len({finding.fingerprint for finding in findings}) == 1
    assert len({str(finding.call_site) for finding in findings}) == 2


def test_two_callers_of_one_helper_are_two_findings(authors: list[Author]) -> None:
    """What the call site alone cannot do, and the reason the identity is the stack.

    Both findings name the same line -- the one inside ``_books`` -- because
    that is where the query is emitted. But the fix is not there: it is in each
    of the two loops, and there are two of them. Grouping on the call site would
    report one finding of six pointing at the one line that is fine.
    """
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            _books(author)
        for author in Author.objects.all():
            _books(author)

    findings = find_n_plus_one(capture)
    assert [finding.count for finding in findings] == [3, 3]
    assert len({str(finding.call_site) for finding in findings}) == 1
    assert len({finding.stack for finding in findings}) == 2


def test_two_statements_from_one_line_are_two_findings(authors: list[Author]) -> None:
    """What the stack alone cannot do.

    One line, two models, two statement shapes. Grouping on the stack would
    merge them into a single finding whose fingerprint described half of it.
    """
    with QueryCapture(using="default") as capture:
        for model in (Author, Book):
            for _ in range(2):
                list(model.objects.filter(pk=1))

    findings = find_n_plus_one(capture)
    assert len(findings) == 2
    assert len({str(finding.call_site) for finding in findings}) == 1
    assert len({finding.fingerprint for finding in findings}) == 2


def test_running_once_is_not_a_finding(authors: list[Author]) -> None:
    """The threshold is the meaning of the word, so there is nothing to configure.

    Once from a path is a query. Twice is an N+1. A knob here would be the first
    thing a maintainer turned up to silence a report, and the first thing that
    made the detector wrong.
    """
    with QueryCapture(using="default") as capture:
        list(Author.objects.filter(pk=1))
    assert find_n_plus_one(capture) == ()

    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
    assert [finding.count for finding in find_n_plus_one(capture)] == [2]


def test_a_batched_write_is_a_finding_like_any_other(authors: list[Author]) -> None:
    """Legitimate repetition is reported, because there is nothing to tell it apart.

    A batched ``bulk_create`` is one statement shape run from one line many
    times, which is the same structure as the defect; only the intention
    differs, and the intention is not in the capture. So it is reported, and
    nothing fails because of it. An exemption list would be the first tunable.
    """
    with QueryCapture(using="default") as capture:
        Book.objects.bulk_create(
            [Book(author=authors[0], title=f"t{index}") for index in range(6)],
            batch_size=2,
        )

    (finding,) = find_n_plus_one(capture)
    assert finding.count == 3


def test_records_with_no_stack_are_not_grouped(authors: list[Author]) -> None:
    """The false positive this refuses to manufacture out of a gap in the input.

    A capture rebuilt from a ``CaptureQueriesContext`` carries no frames at all.
    Bucketing those together would say "these ran from one place" on the
    strength of knowing nothing about where any of them ran -- and it would say
    it about the very repetition a reader is most likely to be looking at.
    """
    with CaptureQueriesContext(connection) as context:
        for _ in range(3):
            list(Author.objects.filter(pk=1))

    capture = QueryCapture.from_capture_context(context)
    assert len(capture) == 3
    assert find_n_plus_one(capture) == ()


def test_findings_are_ordered_worst_first(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
        for _ in range(4):
            list(Book.objects.filter(pk=1))
        for _ in range(3):
            list(Author.objects.filter(name="a0"))

    assert [finding.count for finding in find_n_plus_one(capture)] == [4, 3, 2]


def test_findings_of_equal_size_are_ordered_by_where_they_started(
    authors: list[Author],
) -> None:
    """No two findings share a first execution, so the order is total.

    Without this the two below would be ordered by however the buckets happened
    to be built, and a report would reshuffle between two runs over one capture.

    This is the ordinary case and it is kept for that, but it cannot tell the
    tie-break from a coincidence -- see the test below, which is the one that
    pins it.
    """
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Book.objects.filter(pk=1))
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert [finding.first_index for finding in find_n_plus_one(capture)] == [0, 2]


def test_the_order_does_not_depend_on_the_order_records_arrive(
    authors: list[Author],
) -> None:
    """The tie-break has to be the tie-break, not a coincidence of bucket order.

    The test above cannot tell the two apart, and for a while nothing could:
    deleting the ``first_index`` tie-break left the whole of this module green.
    Buckets are built in first-seen order and ``list.sort`` is stable, so with
    records arriving in capture order a sort on the count alone already lands
    equal-sized findings in ``first_index`` order -- and would keep doing so with
    the tie-break gone.

    ``find_n_plus_one`` accepts any iterable of records, so handing them over out
    of capture order separates what the code promises from what the dict happened
    to do. The same trap, and the same fix, as
    ``test_group_by_call_site.py::test_the_order_does_not_depend_on_the_order_records_arrive``.
    """
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Book.objects.filter(pk=1))
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    shuffled = [*capture.records[2:], *capture.records[:2]]
    assert [finding.first_index for finding in find_n_plus_one(shuffled)] == [0, 2]


def test_a_recursive_walk_splits_by_depth(authors: list[Author]) -> None:
    """The one shape the whole-stack identity does split, pinned rather than hidden.

    The same line reached at two depths is two stacks, so it is two findings.
    Both are true and both name the line to edit; the cost is a longer report,
    and it is the price of never pointing a reader at a line that is fine.
    """

    def walk(depth: int) -> None:
        for _ in range(2):
            list(Author.objects.filter(pk=1))
        if depth:
            walk(depth - 1)

    with QueryCapture(using="default") as capture:
        walk(1)

    findings = find_n_plus_one(capture)
    assert [finding.count for finding in findings] == [2, 2]
    assert len({str(finding.call_site) for finding in findings}) == 1


def test_a_truncated_stack_makes_the_finding_say_so(authors: list[Author]) -> None:
    """Depth one keeps the innermost frame only, which is inside Django."""
    with QueryCapture(using="default", stack_depth=1) as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    (finding,) = find_n_plus_one(capture)
    assert finding.stack_truncated is True
    assert finding.call_site is None


def test_a_capture_and_its_records_read_the_same(authors: list[Author]) -> None:
    """Any iterable of records, so a caller can narrow to one connection first."""
    with QueryCapture(using="default") as capture:
        for _ in range(2):
            list(Author.objects.filter(pk=1))

    assert find_n_plus_one(capture) == find_n_plus_one(capture.records)


@pytest.mark.django_db(databases=["default", "other"])
def test_one_line_querying_two_databases_stays_one_finding() -> None:
    """The identity is (fingerprint, stack) and says nothing about the connection.

    A loop that hits two databases from one line is one loop with one fix, and
    splitting it by alias would be the "one loop, many findings" failure. The
    span is reported on the finding instead of encoded in its identity.
    """
    with QueryCapture() as capture:
        for alias in ("default", "other"):
            list(Author.objects.using(alias).filter(pk=1))

    (finding,) = find_n_plus_one(capture)
    assert finding.count == 2
    assert finding.aliases == ("default", "other")


def _through_a_deep_helper(depth: int) -> None:
    """Recurse, then query twice from one line. The recursion frames are identical."""
    if depth:
        _through_a_deep_helper(depth - 1)
        return
    for _ in range(2):
        list(Author.objects.filter(pk=1))


def _one_caller(authors: list[Author]) -> None:
    _through_a_deep_helper(12)


def _another_caller(authors: list[Author]) -> None:
    _through_a_deep_helper(12)


def test_widening_the_window_is_what_tells_you_two_paths_were_merged(
    authors: list[Author],
) -> None:
    """The advice the documentation gives, run rather than asserted in prose.

    An application stack deeper than the kept window puts two call paths in one
    bucket, and the error that makes is a merge: one finding whose count spans
    both. Nothing on the finding can say so -- ``stack_truncated`` is true of
    every capture under a test runner, at any depth a suite would use, because
    the frames beyond the window are the runner's own. What distinguishes a merge
    is that it *stops being one* when the window widens, so the check is a second
    measurement rather than a flag.

    Below, twelve identical frames of recursion sit between two different callers
    and the query. At a depth that reaches only the recursion, the two are one
    finding of four; at a depth that reaches past it, they are two findings of
    two.
    """
    with QueryCapture(using="default", stack_depth=10) as narrow:
        _one_caller(authors)
        _another_caller(authors)
    with QueryCapture(using="default", stack_depth=40) as wide:
        _one_caller(authors)
        _another_caller(authors)

    merged = find_n_plus_one(narrow)
    split = find_n_plus_one(wide)

    assert [finding.count for finding in merged] == [4]
    assert [finding.count for finding in split] == [2, 2]
    # And the flag says the same thing about both, which is why it cannot be the
    # thing a reader consults.
    assert merged[0].stack_truncated is True
    assert all(finding.stack_truncated for finding in split)
