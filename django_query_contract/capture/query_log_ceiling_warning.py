from __future__ import annotations


class QueryLogCeilingWarning(UserWarning):
    """A block executed more statements than ``connection.queries_log`` can hold."""
