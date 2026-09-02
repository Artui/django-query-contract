"""Django settings for the test suite.

In-memory SQLite, and that is the honest default here rather than a compromise.
Everything this package ships is backend-neutral: capture is
``connection.execute_wrapper``, the fingerprint is a string transform, and the
ceiling is arithmetic over ``connection.queries_limit``. So SQLite reaches every
line, which is what lets the coverage gate stay on the portable matrix.

When plan assertions arrive they will be PostgreSQL-only. The rule that keeps
the gate here is to branch their refusals on the connection's *vendor*, so a
refusal is covered by passing a vendor rather than by running the suite on the
backend being refused.
"""

from __future__ import annotations

SECRET_KEY = "not-a-secret-this-is-the-test-suite"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tests.testapp",
]

USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
    # A second alias, because capture defaults to every configured connection
    # and ``django_assert_num_queries`` takes a ``using=``. With one database
    # the multi-connection path would be written and never executed.
    "other": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
