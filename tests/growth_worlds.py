"""Worlds, blocks and points the growth tests share.

Not a test module. It exists because four test files need the same two things
-- a world of a declared size, and a :class:`GrowthPoint` whose capture really
holds a chosen number of statements -- and a fourth copy of either is a fourth
chance for one of them to describe something the package does not do.

**Every capture built here is a real one over a real connection**, for the
reason ``test_format_capture_report.py`` states at the top of itself: a
formatter or a rule tested against a hand-assembled capture agrees with whatever
the test author believed a capture looks like, and the shape of the thing is
exactly what is worth checking.

The worlds are hand-written ``@contextmanager`` functions rather than anything
from ``django-data-shape``, and that is the point rather than a convenience.
The seam a growth assertion depends on is a *shape* -- ``world(factor)``
returning a context manager -- and the whole reason it is a shape is that a
project on a backend that package refuses, or one that has never installed it,
must be able to supply its own five lines and have the assertion work unchanged.
These are those five lines.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

from django.db import transaction

from django_query_contract import QueryCapture
from django_query_contract.growth_point import GrowthPoint
from tests.testapp.models import Author, Book


@contextmanager
def author_world(factor: int) -> Iterator[int]:
    """``2 * factor`` authors with a book each, undone on the way out.

    Built with two ``bulk_create`` calls, so the *loader's* own statement count
    barely moves between factors. That is deliberate: a test about the block's
    curve should not be able to pass or fail because of the world's, and the one
    test that is about the world's curve uses ``row_by_row_world`` instead.

    The teardown is a rollback to a savepoint rather than a delete, which is
    what ``django_data_shape.scaled_world`` does and for the same reason: inside
    a pytest-django test the whole test is already in a transaction, so this
    costs nothing and leaves the enclosing transaction usable.
    """
    with transaction.atomic():
        Author.objects.bulk_create([Author(name=f"a{index}") for index in range(2 * factor)])
        Book.objects.bulk_create(
            [Book(author=author, title="b") for author in Author.objects.all()]
        )
        yield Author.objects.count() + Book.objects.count()
        transaction.set_rollback(True)


@contextmanager
def row_by_row_world(factor: int) -> Iterator[int]:
    """``3 * factor`` authors, one ``INSERT`` each: a loader whose own count grows.

    The portable loading path, and the hazard the growth harness exists to make
    unavailable. ``django-data-shape`` uses ``COPY`` where the backend has it --
    invisible to ``execute_wrapper`` -- and ordinary inserts where it does not,
    which is most Django suites. A capture opened around a call to this sees a
    statement count that rises with the factor, and a harness reading that curve
    would report the loader's growth as the block's.
    """
    with transaction.atomic():
        for index in range(3 * factor):
            Author.objects.create(name=f"a{index}")
        yield Author.objects.count()
        transaction.set_rollback(True)


@contextmanager
def sizeless_world(factor: int) -> Iterator[None]:
    """A world that builds rows and does not count them.

    The shape of the seam that a five-line implementation actually has: nothing
    obliges a project's own ``@contextmanager`` to have counted its rows, and a
    plain ``yield`` is what it will write. The harness has to take it.
    """
    with transaction.atomic():
        Author.objects.bulk_create([Author(name=f"a{index}") for index in range(factor)])
        yield None
        transaction.set_rollback(True)


@contextmanager
def misreporting_world(factor: int) -> Iterator[object]:
    """A world that yields something which is not a row count at all.

    The realistic shape of the mistake is yielding the build's own result object
    instead of its ``rows`` attribute. The size is a diagnostic printed beside a
    count, so the harness reports it as unknown rather than putting a repr in
    the table or refusing to measure over a cosmetic detail.
    """
    with transaction.atomic():
        Author.objects.bulk_create([Author(name=f"a{index}") for index in range(factor)])
        yield SimpleNamespace(rows=factor)
        transaction.set_rollback(True)


def count_authors() -> None:
    """One statement, whatever the world holds. The ``O(1)`` block."""
    Author.objects.count()


def books_per_author() -> None:
    """One statement per author, plus the one that listed them. The ``O(N)`` block."""
    for author in Author.objects.all():
        list(author.books.all())


def books_for_every_pair() -> None:
    """One statement per pair of authors: the shape a linear claim has to refuse."""
    authors = list(Author.objects.all())
    for _ in authors:
        for inner in authors:
            inner.books.count()


def capture_of(count: int) -> QueryCapture:
    """A closed capture holding exactly ``count`` real statements."""
    with QueryCapture(using="default") as capture:
        for _ in range(count):
            Author.objects.exists()
    return capture


def point(factor: int, count: int, *, rows: int | None = None) -> GrowthPoint:
    """A measurement at ``factor`` whose capture really ran ``count`` statements."""
    return GrowthPoint(factor=factor, rows=rows, capture=capture_of(count))
