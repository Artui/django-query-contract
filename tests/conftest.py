"""Suite-wide fixtures."""

from __future__ import annotations

from collections import deque

import pytest
from django.db import connection

# The plugin hooks are only observable from the outside -- a report section and a
# warning attached to somebody else's test run -- so they are tested by running
# pytest inside pytest. There is no way to assert on a report section from the
# run that produced it.
pytest_plugins = ["pytester"]


@pytest.fixture
def clean_query_log():
    """Give a test sole ownership of ``connection.queries_log``.

    The log is shared for the life of the connection and every earlier test
    contributes to it, so a test about the ceiling has to start from a state it
    chose. Restored afterwards for the same reason.
    """
    saved_log = connection.queries_log.copy()
    saved_debug = connection.force_debug_cursor
    connection.queries_log.clear()
    try:
        yield connection.queries_log
    finally:
        connection.force_debug_cursor = saved_debug
        connection.queries_log.clear()
        connection.queries_log.extend(saved_log)


@pytest.fixture
def tiny_query_log(clean_query_log):
    """Shrink Django's query log so its ceiling is reachable in a few statements.

    The same mechanism as the real 9000-entry bound, at a size a test can drive
    in microseconds. ``test_query_capture.py::test_the_ceiling_is_real`` runs it
    at the real limit; everything else uses this, so the suite pays that cost
    once rather than in every test that needs a full log.
    """
    saved_limit = connection.queries_limit
    saved_log = connection.queries_log
    connection.queries_limit = 5
    connection.queries_log = deque(maxlen=5)
    connection.force_debug_cursor = True
    try:
        yield 5
    finally:
        connection.queries_limit = saved_limit
        connection.queries_log = saved_log
