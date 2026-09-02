"""The capture engine: every execution, with its fingerprint and its call site."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import ExitStack
from typing import Any

from django.db import connections

from django_query_contract.capture_stack import capture_stack
from django_query_contract.log_ceiling import LogCeiling
from django_query_contract.normalise_sql import normalise_sql
from django_query_contract.query_record import QueryRecord

# Measured rather than guessed: six frames separate ``cursor.execute`` from the
# line that iterated a queryset, so twenty-five leaves nineteen for whatever
# application code sits above it -- a view, a service, a serializer -- and still
# reaches the call site. The frames beyond that, under pytest, are the runner's
# own and identical for every query in the suite. Depth is the one part of
# capture whose cost scales, at roughly half a microsecond per frame, so the
# default is the smallest number that keeps what a reader can act on.
_DEFAULT_STACK_DEPTH = 25


class QueryCapture:
    """Record every statement executed inside a block, on one or more connections.

    Capture rides on ``connection.execute_wrapper()``, which is Django's
    documented hook and is what makes this compose rather than compete.
    ``django_assert_num_queries`` counts through ``CaptureQueriesContext``, which
    works by flipping ``force_debug_cursor`` and reading ``queries_log``; a
    wrapper is a separate list on the connection and touches neither. So this
    nests inside or around that assertion without changing what it sees --
    a fact about the two mechanisms rather than a hope about them.

    It also counts every execution, where ``queries_log`` is a bounded deque.
    See ``LogCeiling`` for what that costs the other path and how this reports it.

    ```python
    with QueryCapture() as capture:
        list(Author.objects.all())

    for fingerprint, records in capture.by_fingerprint().items():
        print(len(records), fingerprint, records[0].call_site)
    ```
    """

    def __init__(
        self,
        *,
        using: str | Iterable[str] | None = None,
        stack_depth: int = _DEFAULT_STACK_DEPTH,
    ) -> None:
        """
        Args:
            using: A connection alias, several aliases, or ``None`` for every
                configured one. Every alias by default because the assertion
                this diagnoses takes a ``using=`` of its own, and a diagnosis
                that covered only ``default`` would go quiet on exactly the
                multi-database test that most needs it.
            stack_depth: How many frames to keep per query. Lower it if a suite
                feels the cost; the walk is the only part of capture that is not
                a handful of string operations.
        """
        if using is None:
            self._using: tuple[str, ...] | None = None
        elif isinstance(using, str):
            self._using = (using,)
        else:
            self._using = tuple(using)
        self._stack_depth = stack_depth
        self._records: list[QueryRecord] = []
        self._ceilings: tuple[LogCeiling, ...] = ()
        self._entered: tuple[tuple[str, int, int | None], ...] = ()
        self._wrappers = ExitStack()

    def __enter__(self) -> QueryCapture:
        # Reset rather than accumulate, so re-entering one instance measures one
        # block. A capture that silently summed two blocks would be the same
        # class of quiet wrongness this package exists to expose.
        self._records = []
        self._ceilings = ()
        aliases = self._using if self._using is not None else tuple(connections)
        entered: list[tuple[str, int, int | None]] = []
        self._wrappers = ExitStack()
        for alias in aliases:
            connection = connections[alias]
            entered.append((alias, len(connection.queries_log), connection.queries_limit))
            self._wrappers.enter_context(connection.execute_wrapper(self._record))
        self._entered = tuple(entered)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._wrappers.close()
        self._ceilings = tuple(
            LogCeiling(
                alias=alias,
                limit=limit,
                log_length_at_enter=log_length,
                executions=sum(1 for record in self._records if record.alias == alias),
            )
            for alias, log_length, limit in self._entered
        )

    def _record(self, execute: Any, sql: Any, params: Any, many: bool, context: Any) -> Any:
        """The ``execute_wrapper`` callable itself.

        Recording happens before the statement runs and the result is returned
        untouched, so a query that raises is still counted. A failing statement
        is a statement that was executed, and a diagnosis that dropped it would
        under-report the block that most needs explaining.
        """
        connection = context["connection"]
        stack, truncated = capture_stack(self._stack_depth)
        try:
            param_count = None if params is None else len(params)
        except TypeError:
            # Django accepts an iterator of parameters and handles the same
            # TypeError in its own debug logging. Sizing it here would consume
            # it and the query would run with nothing bound.
            param_count = None
        self._records.append(
            QueryRecord(
                index=len(self._records),
                sql=sql,
                fingerprint=normalise_sql(sql),
                alias=connection.alias,
                vendor=connection.vendor,
                many=many,
                param_count=param_count,
                stack=stack,
                stack_truncated=truncated,
            )
        )
        return execute(sql, params, many, context)

    @property
    def records(self) -> tuple[QueryRecord, ...]:
        """Every execution, in order. A snapshot, so it is safe to read mid-block."""
        return tuple(self._records)

    @property
    def ceilings(self) -> tuple[LogCeiling, ...]:
        """One per captured connection, populated on exit."""
        return self._ceilings

    @property
    def exceeded_ceilings(self) -> tuple[LogCeiling, ...]:
        """The connections whose block ran past what Django's query log can hold."""
        return tuple(ceiling for ceiling in self._ceilings if ceiling.exceeded)

    def by_fingerprint(self) -> dict[str, tuple[QueryRecord, ...]]:
        """Group the records by fingerprint, in the order each was first seen.

        The grouping every face of this capture starts from. A group of more
        than one is a repeated statement; whether it is an N+1 also depends on
        the call stack, which the records carry.
        """
        grouped: dict[str, list[QueryRecord]] = {}
        for record in self._records:
            grouped.setdefault(record.fingerprint, []).append(record)
        return {fingerprint: tuple(records) for fingerprint, records in grouped.items()}

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[QueryRecord]:
        return iter(tuple(self._records))

    def __getitem__(self, index: int) -> QueryRecord:
        return self._records[index]

    @classmethod
    def from_capture_context(cls, context: Any) -> QueryCapture:
        """Build a capture from a ``django.test.utils.CaptureQueriesContext``.

        This is the object ``django_assert_num_queries`` yields, so a caller
        already holding one can be served without rewriting the test. What comes
        back is honestly degraded, and the gaps are the argument for capturing
        separately rather than a limitation to work around:

        - **No call stacks.** That context records ``{"sql", "time"}`` per query
          and nothing else, so there is no frame to recover. ``call_site`` is
          ``None`` on every record.
        - **No ceiling.** ``ceilings`` is empty, because a count taken from a
          rotated deque cannot report how much it lost -- the dropped entries
          are gone, and their number with them. This is the one thing that
          cannot be reconstructed after the fact at any price.
        - **No parameter counts**, and ``many`` is ``False`` throughout: the SQL
          of an ``executemany`` arrives there already rewritten to
          ``"N times: ..."``.

        Args:
            context: Anything with ``captured_queries`` and ``connection``.
        """
        capture = cls()
        connection = context.connection
        capture._records = [
            QueryRecord(
                index=index,
                sql=query["sql"],
                fingerprint=normalise_sql(query["sql"]),
                alias=connection.alias,
                vendor=connection.vendor,
                many=False,
                param_count=None,
            )
            for index, query in enumerate(context.captured_queries)
        ]
        return capture
