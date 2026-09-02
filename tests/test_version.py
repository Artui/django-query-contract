"""The version is a string and the package exports it."""

from __future__ import annotations

import django_query_contract


def test_version_is_exported() -> None:
    assert isinstance(django_query_contract.__version__, str)
    assert django_query_contract.__version__.count(".") == 2
