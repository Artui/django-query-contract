from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

from django.db import transaction

from django_query_contract import QueryCapture
from django_query_contract.types.growth_point import GrowthPoint
from tests.testapp.models import Author, Book


@contextmanager
def author_world(factor: int) -> Iterator[int]:
    """``2 * factor`` authors with a book each, undone on the way out."""
    with transaction.atomic():
        Author.objects.bulk_create([Author(name=f"a{index}") for index in range(2 * factor)])
        Book.objects.bulk_create(
            [Book(author=author, title="b") for author in Author.objects.all()]
        )
        yield Author.objects.count() + Book.objects.count()
        transaction.set_rollback(True)


@contextmanager
def row_by_row_world(factor: int) -> Iterator[int]:
    """``3 * factor`` authors, one ``INSERT`` each: a loader whose own count grows."""
    with transaction.atomic():
        for index in range(3 * factor):
            Author.objects.create(name=f"a{index}")
        yield Author.objects.count()
        transaction.set_rollback(True)


@contextmanager
def sizeless_world(factor: int) -> Iterator[None]:
    """A world that builds rows and does not count them."""
    with transaction.atomic():
        Author.objects.bulk_create([Author(name=f"a{index}") for index in range(factor)])
        yield None
        transaction.set_rollback(True)


@contextmanager
def misreporting_world(factor: int) -> Iterator[object]:
    """A world that yields something which is not a row count at all."""
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
