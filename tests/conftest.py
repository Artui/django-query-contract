"""Suite-wide fixtures."""

from __future__ import annotations

from collections import deque

import pytest
from django.db import connection
from django.test import override_settings

from django_query_contract import plugin

# The plugin hooks are only observable from the outside -- a report section and a
# warning attached to somebody else's test run -- so they are tested by running
# pytest inside pytest. There is no way to assert on a report section from the
# run that produced it.
pytest_plugins = ["pytester"]


def pytest_addoption(parser: pytest.Parser, pluginmanager: pytest.PytestPluginManager) -> None:
    """Register the plugin's options without registering its hooks.

    ``addopts`` carries ``-p no:django_query_contract``, for the reason written
    there: an entry-point plugin is imported before pytest-cov starts measuring,
    so leaving it on makes the coverage gate report 0% for lines that ran. The
    cost is that the session's own config then knows nothing about
    ``--no-query-contract`` or ``query_contract``, and a hook driven against the live
    item raises ``ValueError: no option named '--no-query-contract'`` -- a failure
    that says nothing about the option and everything about which plugins are
    loaded.

    Declaring the options here separates the two halves of what a plugin is.
    pluggy finds hooks by name in a module's namespace, and the only hook name
    in this one is the one below, so the package's options exist for this
    session while its ``pytest_runtest_call`` and ``pytest_runtest_makereport``
    stay out of it -- which is exactly the arrangement ``addopts`` is asking for,
    stated where a contributor will read it.

    The guard is for the contributor who runs ``pytest`` without ``addopts``, or
    who enables the plugin explicitly: registering the same option twice raises
    at startup, which is a worse first experience than the one this file exists
    to prevent. It tests for the plugin **module** rather than for a plugin
    name, because the name depends on how it was loaded -- ``django_query_contract``
    from the entry point, ``django_query_contract.plugin`` from ``-p`` -- and the
    module object is the same either way.
    """
    if any(loaded is plugin for loaded in pluginmanager.get_plugins()):
        return
    plugin.pytest_addoption(parser)


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


@pytest.fixture
def pretend_postgres():
    """A connection whose ``vendor`` is ``postgresql``, with no server behind it.

    Plan capture refuses on the connection's vendor, so on a SQLite run the
    *accepting* half of that decision has nothing to accept and the code that
    runs once a capture is allowed to start is unreachable. A backend's
    ``vendor`` is a class attribute, though, and Django reads
    ``settings.DATABASES`` lazily -- so declaring an alias with the PostgreSQL
    engine gives a real connection object that answers ``postgresql`` and never
    opens a socket.

    It is added here rather than in the settings module because pytest-django
    creates a test database for every configured alias, and this one has none to
    create. Anything that would actually connect through it fails, which is the
    correct outcome: this exists to be *asked its vendor*.
    """
    from django.conf import settings
    from django.db import connections

    databases = {
        **settings.DATABASES,
        "pretend_postgres": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "django-query-contract-has-no-server-here",
        },
    }
    # ``ConnectionHandler.settings`` is a cached_property over a dict it also
    # keeps on ``_settings``, and nothing in ``override_settings`` invalidates
    # either -- so both have to be dropped for the new alias to be visible.
    # Dropped again afterwards, along with the connection object itself, so no
    # later test finds an alias its settings do not declare.
    with override_settings(DATABASES=databases):
        _reset_connection_settings()
        try:
            yield "pretend_postgres"
        finally:
            if hasattr(connections._connections, "pretend_postgres"):
                delattr(connections._connections, "pretend_postgres")
            _reset_connection_settings()


def _reset_connection_settings() -> None:
    """Make ``django.db.connections`` re-read ``settings.DATABASES``."""
    from django.db import connections

    connections._settings = None
    connections.__dict__.pop("settings", None)
