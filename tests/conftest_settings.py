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
