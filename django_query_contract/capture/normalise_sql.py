from __future__ import annotations

import re
from functools import lru_cache

# Every rule below is here because a real Django execution needs it. They were
# read off the wire -- an ``execute_wrapper`` over an ORM session on SQLite --
# rather than imagined, and each one is named by the statement that produced it.

# ``SAVEPOINT "s8384995712_x1"`` / ``RELEASE SAVEPOINT ...`` / ``ROLLBACK TO
# SAVEPOINT ...``. The identifier carries the thread id and a per-connection
# counter, so it is different for every savepoint and different again on the
# next run. It is not a bound parameter -- there are no parameters on these
# statements at all -- so a normaliser that only strips placeholders leaves
# every nested ``atomic()`` block looking like a unique query shape.
_SAVEPOINT = re.compile(r"(?i)(\bSAVEPOINT\s+)(\"[^\"]*\"|`[^`]*`|\[[^\]]*\]|[^\s;]+)")

# Single-quoted literals, with SQL's doubled-quote escape. Django's own SQL is
# fully parameterised, so these come from the escape hatches: ``.raw()``,
# ``RawSQL``, ``.extra()``, a hand-written ``cursor.execute``, and migrations.
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")

# Numeric literals in value position. The lookarounds are what keep this from
# mangling identifiers: a digit preceded or followed by a word character or a
# quote belongs to a name (``app_address2``, ``"s123_x1"``, ``col1``), while a
# free-standing number is a value. Django inlines ``LIMIT`` and ``OFFSET``
# rather than binding them, which is how a paginating loop -- as real an N+1 as
# any other -- would otherwise present as a different shape on every page.
_NUMERIC_LITERAL = re.compile(r"(?<![\w\"'`\].])\d+(?:\.\d+)?(?![\w\"'`\[.])")

# A parenthesised run of placeholders collapses to one. ``IN (%s, %s, %s)`` is
# what ``prefetch_related`` and ``pk__in`` emit, and its width is the size of the
# data, not the shape of the query. The same rule handles a multi-row
# ``INSERT ... VALUES (%s, %s), (%s, %s)`` from ``bulk_create``, which would
# otherwise fingerprint differently for every batch size.
_PLACEHOLDER_RUN = re.compile(r"\(\s*%s(?:\s*,\s*%s)+\s*\)")
_PLACEHOLDER_GROUPS = re.compile(r"\(%s\)(?:\s*,\s*\(%s\))+")

_WHITESPACE = re.compile(r"\s+")

_PLACEHOLDER = "%s"


@lru_cache(maxsize=2048)
def normalise_sql(sql: str) -> str:
    """Return the fingerprint of ``sql``: the part that repeats across executions.

    Two executions with the same fingerprint ran the same statement with
    different data. Paired with the call stack, that is the definition of an
    N+1 -- which is why this is a small list of named, reversible-in-the-head
    rules rather than a hash. Every one of them can be pointed at, argued with
    and tested, and the record keeps the original SQL beside the fingerprint so
    a report never has to be believed on the strength of the normaliser alone.

    A real SQL parser was considered and does not fit, for three independent
    reasons. The SQL that reaches ``execute_wrapper`` carries Django's ``%s``
    placeholders -- the backend's own paramstyle is applied below the wrapper --
    and ``%s`` is a syntax error to a PostgreSQL grammar, so a parser cannot
    read the input at all without the parameters being substituted back in,
    which is the opposite of what a fingerprint is for. It would also be
    PostgreSQL-only in a package whose count and growth assertions are meant to
    work on any backend. And it costs roughly fifteen times a regex pass, per
    query, in a suite that may run hundreds of thousands.

    Args:
        sql: The statement as handed to ``cursor.execute``.

    Returns:
        The normalised statement, with whitespace collapsed.
    """
    normalised = _STRING_LITERAL.sub(_PLACEHOLDER, sql)
    normalised = _SAVEPOINT.sub(r"\1<savepoint>", normalised)
    normalised = _NUMERIC_LITERAL.sub(_PLACEHOLDER, normalised)
    normalised = _PLACEHOLDER_RUN.sub("(%s)", normalised)
    normalised = _PLACEHOLDER_GROUPS.sub("(%s)", normalised)
    return _WHITESPACE.sub(" ", normalised).strip()
