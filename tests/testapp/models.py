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
