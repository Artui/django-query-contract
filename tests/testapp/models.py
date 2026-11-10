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
    """The parent side of the shaped world the plan tests measure against."""

    name = models.CharField(max_length=100)


class Order(models.Model):
    """The child side, with the skewed fan-out the planner cannot see across a join."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    reference = models.CharField(max_length=100)
