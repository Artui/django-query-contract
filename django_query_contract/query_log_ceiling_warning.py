"""The warning raised when a block outruns Django's query log."""

from __future__ import annotations


class QueryLogCeilingWarning(UserWarning):
    """A block executed more statements than ``connection.queries_log`` can hold.

    A warning rather than a failure, because this package asserts nothing: the
    assertion belongs to ``django_assert_num_queries`` and this only says when
    its arithmetic stopped being reliable. It is a warning rather than a report
    section because the dangerous case is a test that **passed** -- five real
    queries counted as zero -- and a section on a passing test is printed only
    when someone asks for it.

    Django emits a ``UserWarning`` of its own when the log is full, but it says
    only that the log truncated; it does not say what the count should have been
    or that an assertion just read a wrong number off it.
    """
