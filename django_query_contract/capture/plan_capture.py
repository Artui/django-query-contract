from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from django.db import connections

from django_query_contract.capture.plans_unsupported import PlansUnsupported
from django_query_contract.capture.query_capture import QueryCapture
from django_query_contract.types.query_plan import QueryPlan
from django_query_contract.utils import DEFAULT_STACK_DEPTH

# With ANALYZE the statement is executed and the plan carries measurements;
# without it the plan carries the planner's expectations and nothing to check
# them against. ``TIMING OFF`` is not a cost optimisation that happens to suit
# this package -- it is this package's thesis. A per-node duration would be a
# field inviting an assertion about milliseconds, and the argument here is that
# such an assertion is a flaky test with extra steps. Turning the instrumentation
# off is the same sentence said to PostgreSQL.
#
# ``BUFFERS`` is only asked for alongside ANALYZE. It was an error without it
# before PostgreSQL 16, and this package states no floor on the server version.
_MEASURED_FLAGS = "ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON"
_PLANNED_FLAGS = "FORMAT JSON"

# Only a statement that begins with SELECT is explained, and the reason is not
# fastidiousness: ``EXPLAIN ANALYZE`` *executes* what it is given. Explaining an
# INSERT would perform the insert, and then the statement would run again for
# real. A leading SELECT is the one thing readable without a SQL parser that
# rules that out -- a data-modifying CTE has to be written ``WITH ... INSERT``,
# which does not begin with SELECT.
#
# The one hole, stated rather than glossed: a SELECT calling a volatile function
# that writes will have that function called twice. There is no reading of the
# statement text that could know, and this package does not parse SQL.
_READ_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

# The two spellings of a cancelled statement, matched by name because this
# package imports neither driver -- it issues EXPLAIN through whichever one the
# connection already has. psycopg 3 raises QueryCanceled and psycopg 2 raises
# QueryCanceledError, and a consumer meeting either wants the same sentence.
_CANCELLED = frozenset({"QueryCanceled", "QueryCanceledError"})

# A savepoint around the EXPLAIN, so a statement PostgreSQL declines to explain
# costs a plan rather than the whole transaction. Verified rather than assumed:
# without it, a failing EXPLAIN inside an atomic block leaves the connection in
# "current transaction is aborted, commands ignored until end of transaction
# block" and every later statement in the test fails. A diagnostic tool that can
# break the test it is diagnosing is not a diagnostic tool.
_SAVEPOINT = "SAVEPOINT django_query_contract_plan"
_ROLLBACK = "ROLLBACK TO SAVEPOINT django_query_contract_plan"
_RELEASE = "RELEASE SAVEPOINT django_query_contract_plan"

# Relations the planner has no statistics for. ``last_analyze`` covers an
# explicit ANALYZE and ``last_autoanalyze`` the one autovacuum ran; either makes
# the plan informed, and neither makes it *right* -- see ``unanalyzed_relations``.
_STATISTICS = (
    "SELECT relname FROM pg_stat_all_tables "
    "WHERE relname = ANY(%s) AND last_analyze IS NULL AND last_autoanalyze IS NULL"
)

# The indexes each relation already has, as the statements PostgreSQL would
# write to create them. ``pg_get_indexdef`` rather than a join onto the columns
# because the server renders an expression index, a partial index and a
# non-default operator class correctly and this package would have to learn all
# three -- and because the only CREATE INDEX statements it is willing to print
# are the ones that already exist, so they may as well be in the server's own
# words. See ``format_relation_access``.
_INDEXES = (
    "SELECT c.relname, pg_get_indexdef(x.indexrelid) "
    "FROM pg_index x JOIN pg_class c ON c.oid = x.indrelid "
    "WHERE c.relname = ANY(%s) ORDER BY 1, 2"
)


class PlanCapture(QueryCapture):
    """A :class:`~django_query_contract.QueryCapture` that also asks for the plan."""

    def __init__(
        self,
        *,
        using: str | Iterable[str] | None = None,
        stack_depth: int = DEFAULT_STACK_DEPTH,
        analyze: bool = True,
    ) -> None:
        """``using``: as :class:`~django_query_contract.QueryCapture` takes it."""
        super().__init__(using=using, stack_depth=stack_depth)
        self._analyze = analyze
        self._relations: dict[str, tuple[Any, set[str]]] = {}
        self._unanalyzed: tuple[str, ...] = ()
        self._indexes: dict[str, tuple[str, ...]] = {}

    @property
    def analyze(self) -> bool:
        """Whether plans here were measured or only planned."""
        return self._analyze

    def refusal(self) -> str | None:
        """Why plans cannot be captured on these connections, or ``None``."""
        return _vendor_refusal((alias, connections[alias].vendor) for alias in self._aliases())

    def __enter__(self) -> PlanCapture:
        """Start capturing, or refuse before a single statement has run."""
        refusal = self.refusal()
        if refusal is not None:
            raise PlansUnsupported(refusal)
        self._relations = {}
        self._unanalyzed = ()
        self._indexes = {}
        super().__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Stop capturing, then ask the catalogue whether these plans meant anything."""
        super().__exit__(exc_type, exc, traceback)
        self._unanalyzed = self._read_statistics()
        self._indexes = self._read_indexes()

    @property
    def unanalyzed_relations(self) -> tuple[str, ...]:
        """The tables in these plans that PostgreSQL has never gathered statistics for."""
        return self._unanalyzed

    @property
    def relation_indexes(self) -> dict[str, tuple[str, ...]]:
        """The indexes each relation in these plans already has, in PostgreSQL's own words."""
        return dict(self._indexes)

    def _plan_for(self, connection: Any, sql: str, params: Any, many: bool) -> QueryPlan:
        """The hook :class:`~django_query_contract.QueryCapture` calls per statement."""
        if many:
            return QueryPlan.refused(
                "executemany was not explained: it is one statement shape and many "
                "parameter sets, so there is no single plan to take."
            )
        if _READ_ONLY.match(sql) is None:
            return QueryPlan.refused(
                "a statement that does not begin with SELECT was not explained: "
                "EXPLAIN ANALYZE executes what it is given, so explaining a write "
                "would perform it, and then the statement would run again for real."
            )
        plan = self._explain(connection, sql, params)
        if plan.root is not None:
            named = self._relations.setdefault(connection.alias, (connection, set()))[1]
            named.update(node.relation for node in plan.nodes if node.relation is not None)
        return plan

    def _explain(self, connection: Any, sql: str, params: Any) -> QueryPlan:
        """Run ``EXPLAIN`` on the driver connection, under a savepoint where there is one."""
        flags = _MEASURED_FLAGS if self._analyze else _PLANNED_FLAGS
        statement = f"EXPLAIN ({flags}) {sql}"
        guarded = connection.in_atomic_block or not connection.get_autocommit()
        cursor = connection.connection.cursor()
        try:
            if guarded:
                cursor.execute(_SAVEPOINT)
            try:
                if params is None:
                    cursor.execute(statement)
                else:
                    cursor.execute(statement, params)
                payload = cursor.fetchall()[0][0]
            except Exception as error:
                if guarded:
                    cursor.execute(_ROLLBACK)
                name = type(error).__name__
                remedy = (
                    " A cancellation here is almost always statement_timeout, and EXPLAIN "
                    "(ANALYZE) runs the statement a second time -- so a query comfortably "
                    "inside the timeout can have its plan capture fall outside it. Raise "
                    "statement_timeout for the tests that capture plans, or capture with "
                    "analyze=False, which only plans."
                    if name in _CANCELLED
                    else ""
                )
                return QueryPlan.refused(
                    f"EXPLAIN raised {name} and the plan was not taken. "
                    "The message is withheld because a driver error can quote a bound "
                    f"value, and this package retains none.{remedy}"
                )
            if guarded:
                cursor.execute(_RELEASE)
        finally:
            cursor.close()
        return QueryPlan.from_explain(payload, analyzed=self._analyze)

    def _read_statistics(self) -> tuple[str, ...]:
        """Ask each connection which of the relations it planned over it has never analyzed."""
        return tuple(sorted({row[0] for row in self._ask_catalogue(_STATISTICS)}))

    def _read_indexes(self) -> dict[str, tuple[str, ...]]:
        """Ask each connection what already indexes the relations it planned over."""
        found: dict[str, list[str]] = {}
        for relation, definition in self._ask_catalogue(_INDEXES):
            found.setdefault(relation, []).append(definition)
        return {relation: tuple(definitions) for relation, definitions in found.items()}

    def _ask_catalogue(self, statement: str) -> Iterator[tuple[Any, ...]]:
        """Put one catalogue question to every connection that produced a plan."""
        for connection, relations in self._relations.values():
            driver = connection.connection
            if driver is None:
                continue
            cursor = driver.cursor()
            try:
                cursor.execute(statement, [sorted(relations)])
                yield from cursor.fetchall()
            finally:
                cursor.close()


def _vendor_refusal(vendors: Iterator[tuple[str, str]]) -> str | None:
    """The sentence refusing the first connection that is not PostgreSQL, or ``None``."""
    for alias, vendor in vendors:
        if vendor != "postgresql":
            return (
                f"Plan capture needs PostgreSQL; connection '{alias}' is {vendor}. "
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and the plan vocabulary this "
                "package reads are PostgreSQL's, and a plan assertion that passed "
                "because the backend could not check it is worse than no assertion."
            )
    return None
