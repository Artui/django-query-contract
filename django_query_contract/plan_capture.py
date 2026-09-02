"""Capture with plans: what the planner chose, taken while the parameters exist."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from django.db import connections

from django_query_contract.plans_unsupported import PlansUnsupported
from django_query_contract.query_capture import QueryCapture
from django_query_contract.query_plan import QueryPlan
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


class PlanCapture(QueryCapture):
    """A :class:`~django_query_contract.QueryCapture` that also asks for the plan.

    ```python
    from django_query_contract import PlanCapture, format_query_plans

    with PlanCapture() as capture:
        render_author_list()

    print(format_query_plans(capture))
    ```

    **The plan is taken at execution time, and it has to be.** This package
    retains no parameters -- a ``bulk_create`` arrives as one execution and ten
    thousand values, and holding them would mean keeping customer data in memory
    to answer a question about query counts -- so a plan cannot be taken after
    the fact from a record. The wrapper is the one moment the statement and its
    bindings are both in hand, and that was written into
    :class:`~django_query_contract.QueryRecord` from the first release, before
    this class existed.

    It is taken **before** the statement runs, for the same reason the record is
    written before it runs: a statement that raises is still a statement that was
    executed, and a plan dropped because the query failed would be missing from
    exactly the diagnosis that needed it.

    **``EXPLAIN`` goes out on the driver connection, under the Django cursor
    rather than through it**, and that is what keeps composition intact. Django's
    ``execute_wrapper`` and its ``queries_log`` both sit on the Python cursor, so
    a plan taken through ``connection.cursor()`` would be captured by this very
    wrapper -- endlessly -- and would also be counted by
    ``django_assert_num_queries``, which counts through ``queries_log``. Measured
    both ways against a real server: the raw cursor is seen by neither. The
    package already documented that blind spot as a limitation of the capture;
    here it is the mechanism.

    **What it costs, measured.** Against PostgreSQL 16 on a shaped 400,000-row
    world, a two-statement block took 8.9 ms on its own and 14.8 ms with plan
    capture: about **1.7x**, which is what running each statement twice buys.
    With ``analyze=False`` it was 9.1 ms, or 1.02x, because the server only plans.
    ``ANALYZE`` is the default anyway, because a plan with no measurement in it
    cannot produce a finding, and a plan capture that can produce no finding is
    the vacuous pass this package exists to refuse.
    """

    def __init__(
        self,
        *,
        using: str | Iterable[str] | None = None,
        stack_depth: int = DEFAULT_STACK_DEPTH,
        analyze: bool = True,
    ) -> None:
        """
        Args:
            using: As :class:`~django_query_contract.QueryCapture` takes it. Every
                configured connection by default -- and every one of them is then
                required to be PostgreSQL, because a capture that quietly skipped
                the connection it could not explain would be the silent gap this
                class exists to refuse.
            stack_depth: Frames kept per statement, as ``QueryCapture`` takes it.
            analyze: Whether to run the statement under ``EXPLAIN ANALYZE`` and
                measure it, or only ask the planner what it would do. ``True``
                costs about twice the block's own time and is the only setting
                from which a finding can be made; ``False`` is for reading the
                planner's choice without paying for it, and
                :func:`~django_query_contract.find_plan_defects` will then find
                nothing and the report will say why.
        """
        super().__init__(using=using, stack_depth=stack_depth)
        self._analyze = analyze
        self._relations: dict[str, tuple[Any, set[str]]] = {}
        self._unanalyzed: tuple[str, ...] = ()

    @property
    def analyze(self) -> bool:
        """Whether plans here were measured or only planned."""
        return self._analyze

    def refusal(self) -> str | None:
        """Why plans cannot be captured on these connections, or ``None``.

        Reads ``vendor`` off each connection and decides from the string, without
        opening anything. That is deliberate and it is what keeps this package's
        coverage gate on the portable matrix: a degradation path reachable only
        by running the suite on the backend it refuses is a path the gating job
        cannot see.

        Public because the two callers need the same sentence delivered two ways.
        ``__enter__`` raises it, and the ``query_plans`` fixture skips with it.
        """
        return _vendor_refusal((alias, connections[alias].vendor) for alias in self._aliases())

    def __enter__(self) -> PlanCapture:
        """Start capturing, or refuse before a single statement has run."""
        refusal = self.refusal()
        if refusal is not None:
            raise PlansUnsupported(refusal)
        self._relations = {}
        self._unanalyzed = ()
        super().__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Stop capturing, then ask the catalogue whether these plans meant anything."""
        super().__exit__(exc_type, exc, traceback)
        self._unanalyzed = self._read_statistics()

    @property
    def unanalyzed_relations(self) -> tuple[str, ...]:
        """The tables in these plans that PostgreSQL has never gathered statistics for.

        **The other half of "never pass vacuously", and the half a vendor check
        cannot reach.** Refusing SQLite covers the backend with no planner. This
        covers the backend that has one and was given nothing to reason with:
        rows loaded in a fixture and never analyzed leave the planner guessing
        from a default selectivity, and the plan it prints is confident and
        meaningless. Measured during this package's design: two million rows
        never analyzed produced a bitmap heap scan estimated at 10,000 rows for
        two predicates whose real answers were 30,298 and 1,959,743.

        It says nothing about whether the tables are *big enough*, and cannot:
        "ten rows is too few" is a number, and a number is the knob this package
        refuses. What it can do is print the row count the planner is working
        from beside the plan and let a reader judge.

        Empty before the block has finished, and empty on any capture that took
        no plans.
        """
        return self._unanalyzed

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
        # A savepoint only inside a transaction. PostgreSQL refuses SAVEPOINT
        # outside a transaction block outright -- verified, it raises rather than
        # warning -- and outside one there is nothing to protect: a failed
        # statement in autocommit poisons only itself.
        guarded = connection.in_atomic_block
        cursor = connection.connection.cursor()
        try:
            if guarded:
                cursor.execute(_SAVEPOINT)
            try:
                # The same split Django's own cursor wrapper makes, and for the
                # same reason: under client-side binding, passing an empty
                # parameter sequence makes a literal ``%`` in the statement an
                # interpolation, so "no parameters" and "an empty tuple of
                # parameters" are different requests.
                if params is None:
                    cursor.execute(statement)
                else:
                    cursor.execute(statement, params)
                payload = cursor.fetchall()[0][0]
            except Exception as error:
                if guarded:
                    cursor.execute(_ROLLBACK)
                # The class name and not the message. A driver error text can
                # quote the value that caused it, and this package retains no
                # parameters -- an error path is not where that rule gets an
                # exception. The statement itself is on the record beside this.
                return QueryPlan.refused(
                    f"EXPLAIN raised {type(error).__name__} and the plan was not taken. "
                    "The message is withheld because a driver error can quote a bound "
                    "value, and this package retains none."
                )
            if guarded:
                cursor.execute(_RELEASE)
        finally:
            cursor.close()
        return QueryPlan.from_explain(payload, analyzed=self._analyze)

    def _read_statistics(self) -> tuple[str, ...]:
        """Ask each connection which of the relations it planned over it has never analyzed.

        One statement per connection that produced a plan, at the end of the
        block rather than per statement, and on the driver cursor for the reason
        the ``EXPLAIN`` is: a diagnostic that inflated ``queries_log`` would
        change the count the assertion it is diagnosing reads.
        """
        unanalyzed: set[str] = set()
        for connection, relations in self._relations.values():
            driver = connection.connection
            if driver is None:
                # The block closed the connection it queried. Nothing to ask, and
                # opening a new one to ask would be this package deciding a
                # diagnostic is worth a reconnection.
                continue
            cursor = driver.cursor()
            try:
                cursor.execute(_STATISTICS, [sorted(relations)])
                unanalyzed.update(row[0] for row in cursor.fetchall())
            finally:
                cursor.close()
        return tuple(sorted(unanalyzed))


def _vendor_refusal(vendors: Iterator[tuple[str, str]]) -> str | None:
    """The sentence refusing the first connection that is not PostgreSQL, or ``None``.

    A pure function of alias and vendor strings, so both answers are reachable
    from a suite running entirely on SQLite. That is the rule this repository
    keeps its coverage gate on the portable matrix with, written out rather than
    left as a convention.
    """
    for alias, vendor in vendors:
        if vendor != "postgresql":
            return (
                f"Plan capture needs PostgreSQL; connection '{alias}' is {vendor}. "
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and the plan vocabulary this "
                "package reads are PostgreSQL's, and a plan assertion that passed "
                "because the backend could not check it is worse than no assertion."
            )
    return None
