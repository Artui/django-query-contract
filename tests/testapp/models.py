"""Two models with one edge: the smallest schema that can produce an N+1."""

from __future__ import annotations

from django.db import models


class Author(models.Model):
    """The parent side of the loop."""

    name = models.CharField(max_length=100)


class Book(models.Model):
    """The child side. Iterating authors and touching ``books`` is the defect."""

    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    title = models.CharField(max_length=100)


class Customer(models.Model):
    """The parent side of the shaped world the plan tests measure against.

    Separate models from ``Author`` and ``Book`` on purpose. The plan tests build
    a session-scoped world of a hundred thousand rows and commit it, so pointing
    them at the models the N+1 tests use would leave those tests counting five
    thousand authors where their own fixture made three. A shaped world and a
    hand-built one compose by taking different models, never by taking turns
    over one.
    """

    name = models.CharField(max_length=100)


class Order(models.Model):
    """The child side, with the skewed fan-out the planner cannot see across a join."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    reference = models.CharField(max_length=100)
