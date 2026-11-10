from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import ExitStack
from typing import Any

from django.db import connections

from django_query_contract.capture.normalise_sql import normalise_sql
from django_query_contract.source_location.capture_stack import capture_stack
from django_query_contract.types.log_ceiling import LogCeiling
from django_query_contract.types.query_plan import QueryPlan
from django_query_contract.types.query_record import QueryRecord
from django_query_contract.utils import DEFAULT_STACK_DEPTH


class QueryCapture:
    """Record every statement executed inside a block, on one or more connections."""

    def __init__(
        self,
        *,
        using: str | Iterable[str] | None = None,
        stack_depth: int = DEFAULT_STACK_DEPTH,
    ) -> None:
        """``using``: a connection alias, several aliases, or ``None`` for every configured one."""
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
        # Reset rather than accumulate, so re-entering one instance measures one block.
        self._records = []
        self._ceilings = ()
        aliases = self._aliases()
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

    def _aliases(self) -> tuple[str, ...]:
        """The connections this capture covers: the ones named, or every configured one."""
        return self._using if self._using is not None else tuple(connections)

    def _plan_for(self, connection: Any, sql: str, params: Any, many: bool) -> QueryPlan | None:
        """The plan for a statement about to run, or ``None`` when nobody asked for one."""
        return None

    def _record(self, execute: Any, sql: Any, params: Any, many: bool, context: Any) -> Any:
        """The ``execute_wrapper`` callable itself."""
        connection = context["connection"]
        stack, truncated = capture_stack(self._stack_depth)
        try:
            param_count = None if params is None else len(params)
        except TypeError:
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
                plan=self._plan_for(connection, sql, params, many),
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
        """Group the records by fingerprint, in the order each was first seen."""
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
        """Build a capture from a ``django.test.utils.CaptureQueriesContext``."""
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
