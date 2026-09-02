"""The capture engine against a real connection."""

from __future__ import annotations

import contextlib
import os

import pytest
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext

import django_query_contract
from django_query_contract import QueryCapture
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db

_PACKAGE_ROOT = os.path.dirname(os.path.abspath(django_query_contract.__file__)) + os.sep


@pytest.fixture
def authors() -> list[Author]:
    """Three authors, two books each: enough for a loop to be visibly a loop."""
    made = [Author.objects.create(name=f"a{index}") for index in range(3)]
    for author in made:
        for index in range(2):
            Book.objects.create(author=author, title=f"b{index}")
    return made


def test_a_loop_is_one_shape_from_one_place(authors: list[Author]) -> None:
    """The defect this package exists to describe, and how it reads in the capture.

    Three iterations, three statements, one fingerprint and one call site. That
    pairing is what makes an N+1 identifiable by construction rather than by a
    rule about lazy loads -- which is what the detectors that died were tuning.
    """
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())

    groups = capture.by_fingerprint()
    repeated = [records for records in groups.values() if len(records) > 1]
    assert len(repeated) == 1
    (child_queries,) = repeated
    assert len(child_queries) == 3
    sites = {str(record.call_site) for record in child_queries}
    assert len(sites) == 1
    assert sites.pop().startswith(f"{os.path.abspath(__file__)}:")


def test_widths_of_one_in_list_share_a_fingerprint(authors: list[Author]) -> None:
    """Three different parameter counts, one shape. The width is data, not structure."""
    with QueryCapture(using="default") as capture:
        list(Author.objects.filter(pk__in=[authors[0].pk]))
        list(Author.objects.filter(pk__in=[a.pk for a in authors[:2]]))
        list(Author.objects.filter(pk__in=[a.pk for a in authors]))

    assert len(capture) == 3
    assert len(capture.by_fingerprint()) == 1
    assert [record.param_count for record in capture] == [1, 2, 3]


def test_a_record_carries_what_the_four_faces_need(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        list(Author.objects.all())

    record = capture[0]
    assert record.index == 0
    assert record.alias == "default"
    assert record.vendor == "sqlite"
    assert record.many is False
    assert record.sql.startswith("SELECT")
    assert record.fingerprint == record.sql
    assert record.stack
    assert record.call_site is not None
    # The capture machinery must not appear between the caller and the query.
    # Called directly, ``capture_stack`` has no frames of its own to drop; only
    # through the wrapper is there anything for the filter to do, so this is
    # where its absence would show.
    assert not any(frame.filename.startswith(_PACKAGE_ROOT) for frame in record.stack)


def test_executemany_is_recorded_as_such() -> None:
    """``many`` distinguishes one statement over many rows from many statements."""
    with QueryCapture(using="default") as capture, connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO testapp_author (name) VALUES (%s)",
            [("one",), ("two",), ("three",)],
        )

    (record,) = [item for item in capture if item.many]
    assert record.param_count == 3


def test_unsized_parameters_do_not_break_capture() -> None:
    """Django accepts an iterator of parameters; sizing it here would consume it.

    The query itself is free to fail -- that is the backend's business -- but it
    must still be recorded, because a statement that raised is a statement that
    ran.
    """
    with (
        QueryCapture(using="default") as capture,
        connection.cursor() as cursor,
        contextlib.suppress(Exception),
    ):
        cursor.execute("SELECT %s", iter([1]))

    assert len(capture) == 1
    assert capture[0].param_count is None


def test_a_failing_statement_is_still_recorded() -> None:
    """A block that raised is the block most in need of explaining."""
    with (
        QueryCapture(using="default") as capture,
        connection.cursor() as cursor,
        contextlib.suppress(Exception),
    ):
        cursor.execute("SELECT * FROM a_table_that_does_not_exist")

    assert len(capture) == 1
    assert "a_table_that_does_not_exist" in capture[0].sql


def test_a_statement_that_bypasses_the_cursor_wrapper_is_not_captured() -> None:
    """The boundary of the mechanism, pinned so it is read here and not discovered.

    ``execute_wrapper`` wraps Django's cursor wrapper, which means it sees
    ``execute`` and ``executemany`` and nothing else. A statement issued on the
    raw driver connection is invisible, and so is anything using a driver API
    that is not one of those two -- psycopg 3's ``cursor.copy()``, which is how
    ``django-data-shape`` loads rows, was measured emitting no captured
    statement at all.

    Django's own ``queries_log`` has the same blind spot, so the two agree; the
    point of the test is that the agreement is a fact rather than an assumption,
    and that a package about honest counts states where its count stops.
    """
    with connection.cursor():
        pass  # Open the connection without counting the statement that does it.

    with QueryCapture(using="default") as capture:
        connection.connection.execute("SELECT 1")

    assert len(capture) == 0


def test_transaction_control_is_captured_with_no_parameters() -> None:
    """BEGIN and SAVEPOINT pass ``None``, and every savepoint has a unique name."""
    with QueryCapture(using="default") as capture, connection.cursor() as cursor:
        cursor.execute('SAVEPOINT "s1_x1"')
        cursor.execute('RELEASE SAVEPOINT "s1_x1"')

    assert [record.param_count for record in capture] == [None, None]
    assert capture[0].fingerprint == "SAVEPOINT <savepoint>"


def test_using_selects_which_connections_to_watch(authors: list[Author]) -> None:
    with QueryCapture(using=["default", "other"]) as several:
        list(Author.objects.all())
    assert {ceiling.alias for ceiling in several.ceilings} == {"default", "other"}

    with QueryCapture(using="default") as one:
        list(Author.objects.all())
    assert {ceiling.alias for ceiling in one.ceilings} == {"default"}


def test_every_configured_connection_is_watched_by_default(authors: list[Author]) -> None:
    """The assertion this diagnoses takes a ``using=`` of its own.

    A diagnosis covering only ``default`` would go quiet on exactly the
    multi-database test that most needs it.
    """
    with QueryCapture() as capture:
        list(Author.objects.all())
    assert {ceiling.alias for ceiling in capture.ceilings} == set(connections)


def test_re_entering_measures_one_block(authors: list[Author]) -> None:
    """A capture that silently summed two blocks would be its own quiet wrongness."""
    capture = QueryCapture(using="default")
    with capture:
        list(Author.objects.all())
    first = len(capture)
    with capture:
        list(Author.objects.all())
    assert first == len(capture) == 1


def test_the_capture_reads_like_a_sequence(authors: list[Author]) -> None:
    """Mirrors ``CaptureQueriesContext`` so it can be read in the same places."""
    with QueryCapture(using="default") as capture:
        list(Author.objects.all())
        list(Book.objects.all())

    assert len(capture) == 2
    assert list(capture) == list(capture.records)
    assert capture[1] is capture.records[1]


def test_capture_does_not_disturb_what_pytest_django_counts(
    authors: list[Author], django_assert_num_queries
) -> None:
    """The composition claim, falsified in both nestings.

    ``CaptureQueriesContext`` works by flipping ``force_debug_cursor`` and
    reading ``queries_log``; a wrapper is a separate list on the connection.
    They cannot see each other, and if this capture executed so much as one
    statement of its own the counts below would move.
    """
    with QueryCapture(using="default") as outside, django_assert_num_queries(2) as context:
        list(Author.objects.all())
        list(Book.objects.all())
    assert len(context) == 2
    assert len(outside) == 2

    with django_assert_num_queries(2) as context, QueryCapture(using="default") as inside:
        list(Author.objects.all())
        list(Book.objects.all())
    assert len(context) == 2
    assert len(inside) == 2


def test_from_capture_context_serves_a_caller_who_already_has_one(
    authors: list[Author], django_assert_num_queries
) -> None:
    """The fixture yields a ``CaptureQueriesContext``; this reads one without a rewrite.

    Honestly degraded, and the degradation is the argument for capturing
    separately: there are no stacks to recover, and no ceiling, because a count
    taken from a rotated deque cannot report what it dropped.
    """
    with django_assert_num_queries(1) as context:
        list(Author.objects.all())

    capture = QueryCapture.from_capture_context(context)
    assert len(capture) == 1
    record = capture[0]
    assert record.sql.startswith("SELECT")
    assert record.alias == "default"
    assert record.vendor == "sqlite"
    assert record.stack == ()
    assert record.call_site is None
    assert record.param_count is None
    assert capture.ceilings == ()


def test_the_ceiling_is_real(clean_query_log) -> None:
    """Reproduce the under-report against the installed Django, at the real limit.

    This is the falsification the whole ceiling story rests on, and it is run
    rather than argued: ``CaptureQueriesContext`` is asked for a count over a
    block whose size is known, and the answer is compared with the number of
    statements that actually executed.
    """
    limit = connection.queries_limit

    def run(count: int) -> None:
        with connection.cursor() as cursor:
            for _ in range(count):
                cursor.execute("SELECT 1")

    def measure(pre_filled: int, inside: int) -> tuple[int, int, bool]:
        connection.queries_log.clear()
        # force_debug_cursor is what makes the log grow at all, and it is what
        # CaptureQueriesContext itself turns on. Pre-filling under it is how a
        # suite arrives at a full log: an earlier assertion in the same test.
        connection.force_debug_cursor = True
        run(pre_filled)
        with QueryCapture(using="default") as capture, CaptureQueriesContext(connection) as context:
            run(inside)
        connection.force_debug_cursor = False
        (ceiling,) = capture.ceilings
        return len(context), len(capture), ceiling.exceeded

    reported, executed, exceeded = measure(0, 50)
    assert (reported, executed, exceeded) == (50, 50, False)

    reported, executed, exceeded = measure(0, limit + 1)
    assert (reported, executed, exceeded) == (limit, limit + 1, True)

    reported, executed, exceeded = measure(limit - 10, 100)
    assert (reported, executed, exceeded) == (10, 100, True)

    # The silent false pass: five statements, a reported count of zero.
    reported, executed, exceeded = measure(limit, 5)
    assert (reported, executed, exceeded) == (0, 5, True)


def test_a_max_num_queries_assertion_passes_over_the_ceiling(
    clean_query_log, django_assert_max_num_queries
) -> None:
    """Not a hypothetical: pytest-django's own assertion, green, over five real queries.

    This is the reason the ceiling is reported rather than absorbed. The
    assertion below is the one a reader would write to prove a block is cheap,
    and here it proves nothing at all.
    """
    connection.force_debug_cursor = True
    with connection.cursor() as cursor:
        for _ in range(connection.queries_limit):
            cursor.execute("SELECT 1")

    with (
        QueryCapture(using="default") as capture,
        django_assert_max_num_queries(1),
        connection.cursor() as cursor,
    ):
        for _ in range(5):
            cursor.execute("SELECT 1")

    assert len(capture) == 5
    (ceiling,) = capture.exceeded_ceilings
    assert ceiling.visible == 0
    assert ceiling.executions == 5
