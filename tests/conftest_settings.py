"""Django settings for the test suite.

In-memory SQLite by default, and that is the honest default here rather than a
compromise. Almost everything this package ships is backend-neutral: capture is
``connection.execute_wrapper``, the fingerprint is a string transform, and the
ceiling is arithmetic over ``connection.queries_limit``. So SQLite reaches every
line, which is what lets the coverage gate stay on the portable matrix.

Plan capture is the one exception and it is PostgreSQL-only. The rule that keeps
the gate here is that every refusal branches on the connection's *vendor* and
every plan is parsed from a payload, so both are covered by passing a vendor or
a payload rather than by running the suite on the backend being refused. What
that cannot cover is whether ``EXPLAIN`` actually works against a real server,
which is what ``QUERY_CONTRACT_TEST_DATABASE=postgres`` is for: it points the
default connection at PostgreSQL and lets ``tests/test_plan_capture_postgres.py``
run for real. That job carries no coverage gate; this one does.
"""

from __future__ import annotations

import os

SECRET_KEY = "not-a-secret-this-is-the-test-suite"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tests.testapp",
]

USE_TZ = True

_DEFAULT: dict[str, object] = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",
}

if os.environ.get("QUERY_CONTRACT_TEST_DATABASE") == "postgres":
    _DEFAULT = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PGDATABASE", "django_query_contract"),
        "USER": os.environ.get("PGUSER", ""),
        "PASSWORD": os.environ.get("PGPASSWORD", ""),
        "HOST": os.environ.get("PGHOST", "localhost"),
        "PORT": os.environ.get("PGPORT", "5432"),
    }

DATABASES = {
    "default": _DEFAULT,
    # A second alias, because capture defaults to every configured connection
    # and ``django_assert_num_queries`` takes a ``using=``. With one database
    # the multi-connection path would be written and never executed.
    #
    # It stays SQLite even when the default is PostgreSQL, and that is load
    # bearing in both directions. On the SQLite run it is an ordinary second
    # connection; on the PostgreSQL run it is a connection plan capture must
    # refuse, so the "one of these connections cannot produce a plan" path is
    # driven by a real registry rather than only by a stub.
    "other": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
