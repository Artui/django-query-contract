"""The version is a string and the package exports it."""

from __future__ import annotations

import django_query_lens


def test_version_is_exported() -> None:
    assert isinstance(django_query_lens.__version__, str)
    assert django_query_lens.__version__.count(".") == 2
