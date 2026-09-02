"""Plan capture: what it refuses, what it explains, and what it leaves alone.

Two kinds of test here and the split is the point. The **refusal** is decided
from a connection's ``vendor`` string, so both answers are reachable from a suite
running on SQLite -- which is what keeps this repository's coverage gate on the
portable matrix rather than on a backend most Django projects do not run.

The **explaining** is driven through a stub connection whose cursor records the
statements it was handed and hands back a real server's own JSON. That proves
what this package sends and what it does with the answer. It cannot prove that
PostgreSQL accepts it, and does not try to: ``test_plan_capture_postgres.py``
runs the same entry points against a server.
"""

from __future__ import annotations

from typing import Any

import pytest

from django_query_contract import PlanCapture, PlansUnsupported, QueryCapture
from tests.plan_payloads import WHALE_JOIN

_SELECT = "SELECT id FROM testapp_book WHERE author_id = %s"


class _Cursor:
    """A driver cursor that remembers what it was asked and answers with real JSON."""

    def __init__(
        self, *, rows: list[list[tuple[Any, ...]]] | None = None, fails: Exception | None = None
    ):
        self.statements: list[tuple[str, Any]] = []
        self.closed = False
        # Rows exactly as a driver hands them back: one list per statement. An
        # EXPLAIN answers with a single row holding the whole JSON document.
        self._rows = rows if rows is not None else [[(WHALE_JOIN,)]]
        self._fails = fails

    def execute(self, sql: str, params: Any = None) -> None:
        self.statements.append((sql, params))
        if self._fails is not None and sql.startswith("EXPLAIN"):
            raise self._fails

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows.pop(0)

    def close(self) -> None:
        self.closed = True


class _Driver:
    def __init__(self, cursor: _Cursor):
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


class _Connection:
    """Enough of a Django connection for the plan machinery, and no more."""

    vendor = "postgresql"

    def __init__(
        self,
        cursor: _Cursor | None = None,
        *,
        alias: str = "default",
        in_atomic_block: bool = True,
    ):
        self.alias = alias
        self.in_atomic_block = in_atomic_block
        self.cursor_object = cursor if cursor is not None else _Cursor()
        self.connection: _Driver | None = _Driver(self.cursor_object)


def _statements(cursor: _Cursor) -> list[str]:
    return [sql for sql, _ in cursor.statements]


def test_a_connection_that_is_not_postgres_is_refused_by_name() -> None:
    """The whole refusal, decided from a vendor string and nothing else."""
    capture = PlanCapture()

    refusal = capture.refusal()

    assert refusal is not None
    # Which alias it names depends on which connection is not PostgreSQL, and
    # that differs between this suite's SQLite run and its PostgreSQL one. What
    # has to hold either way is that it names one, and says what it is.
    assert "is sqlite" in refusal
    assert "worse than no assertion" in refusal


def test_entering_a_capture_that_cannot_produce_a_plan_raises_before_anything_runs() -> None:
    """It raises rather than degrading, and that is the whole class.

    An empty plan capture is indistinguishable from a healthy one, so a caller
    asserting over it would pass because the backend could not check.
    """
    with pytest.raises(PlansUnsupported) as raised, PlanCapture():
        pass

    assert "Plan capture needs PostgreSQL" in str(raised.value)


def test_a_postgres_connection_is_not_refused_and_the_capture_starts(pretend_postgres) -> None:
    """The accepting half, reachable on SQLite because the decision is a string."""
    capture = PlanCapture(using=pretend_postgres)

    assert capture.refusal() is None
    with capture as entered:
        assert entered is capture
    assert len(capture) == 0
    assert capture.unanalyzed_relations == ()
    assert capture.analyze is True


def test_a_capture_can_ask_for_the_plan_without_paying_to_run_the_statement() -> None:
    capture = PlanCapture(analyze=False)
    connection = _Connection()

    plan = capture._plan_for(connection, _SELECT, (1,), False)

    assert capture.analyze is False
    assert plan.analyzed is False
    assert _statements(connection.cursor_object)[1].startswith("EXPLAIN (FORMAT JSON) ")


def test_a_read_statement_is_explained_with_analyze_buffers_and_no_timing() -> None:
    """``TIMING OFF`` is this package's thesis said to PostgreSQL, not a micro-optimisation."""
    capture = PlanCapture()
    connection = _Connection()

    plan = capture._plan_for(connection, _SELECT, (1,), False)

    assert plan.root is not None
    assert plan.analyzed is True
    explains = [sql for sql in _statements(connection.cursor_object) if sql.startswith("EXPLAIN")]
    assert explains == [f"EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) {_SELECT}"]
    assert connection.cursor_object.statements[1][1] == (1,)
    assert connection.cursor_object.closed is True


def test_a_statement_with_no_parameters_is_sent_with_none_rather_than_an_empty_tuple() -> None:
    """The same split Django's own cursor wrapper makes, for the same reason.

    Under client-side binding an empty parameter sequence makes a literal ``%`` in
    the statement an interpolation, so "no parameters" and "an empty tuple of
    parameters" are different requests.
    """
    capture = PlanCapture()
    connection = _Connection()

    capture._plan_for(connection, "SELECT 100 % 3", None, False)

    assert connection.cursor_object.statements[1] == (
        "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) SELECT 100 % 3",
        None,
    )


def test_the_explain_is_wrapped_in_a_savepoint_inside_a_transaction() -> None:
    capture = PlanCapture()
    connection = _Connection(in_atomic_block=True)

    capture._plan_for(connection, _SELECT, (1,), False)

    assert _statements(connection.cursor_object) == [
        "SAVEPOINT django_query_contract_plan",
        f"EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) {_SELECT}",
        "RELEASE SAVEPOINT django_query_contract_plan",
    ]


def test_outside_a_transaction_there_is_no_savepoint_because_there_can_be_none() -> None:
    """PostgreSQL refuses SAVEPOINT outside a transaction block outright.

    Verified against a real server rather than assumed, and outside one there is
    nothing to protect: a failed statement in autocommit poisons only itself.
    """
    capture = PlanCapture()
    connection = _Connection(in_atomic_block=False)

    capture._plan_for(connection, _SELECT, (1,), False)

    assert _statements(connection.cursor_object) == [
        f"EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) {_SELECT}"
    ]


def test_a_failing_explain_inside_a_transaction_rolls_back_to_the_savepoint() -> None:
    capture = PlanCapture()
    cursor = _Cursor(fails=RuntimeError("relation does not exist: secret_value"))
    connection = _Connection(cursor, in_atomic_block=True)

    plan = capture._plan_for(connection, _SELECT, (1,), False)

    assert plan.root is None
    assert _statements(cursor) == [
        "SAVEPOINT django_query_contract_plan",
        f"EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) {_SELECT}",
        "ROLLBACK TO SAVEPOINT django_query_contract_plan",
    ]
    assert cursor.closed is True


def test_a_failing_explain_reports_the_error_class_and_never_its_message() -> None:
    """A driver error can quote a bound value, and this package retains none.

    The retention rule does not get an exception on an error path: the statement
    is on the record beside the refusal, and the class name is what a reader
    needs to tell "the server said no" from "the statement was not a SELECT".
    """
    capture = PlanCapture()
    connection = _Connection(_Cursor(fails=RuntimeError("value 'hunter2' is out of range")))

    plan = capture._plan_for(connection, _SELECT, (1,), False)

    assert plan.refusal is not None
    assert "EXPLAIN raised RuntimeError" in plan.refusal
    assert "hunter2" not in plan.refusal


def test_a_failing_explain_outside_a_transaction_rolls_nothing_back() -> None:
    capture = PlanCapture()
    cursor = _Cursor(fails=RuntimeError("no"))
    connection = _Connection(cursor, in_atomic_block=False)

    plan = capture._plan_for(connection, _SELECT, (1,), False)

    assert plan.refusal is not None
    assert _statements(cursor) == [f"EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) {_SELECT}"]


def test_a_write_is_not_explained_because_explain_analyze_would_perform_it() -> None:
    capture = PlanCapture()
    connection = _Connection()

    plan = capture._plan_for(
        connection, "INSERT INTO testapp_book (title) VALUES (%s)", ("x",), False
    )

    assert plan.root is None
    assert plan.refusal is not None
    assert "does not begin with SELECT" in plan.refusal
    assert connection.cursor_object.statements == []


def test_a_statement_beginning_with_with_is_not_explained_either() -> None:
    """A data-modifying CTE has to be written ``WITH ... INSERT``, so it is not a SELECT.

    That is the whole reason the rule is "begins with SELECT" rather than "does
    not begin with INSERT": the dangerous statement does not announce itself in
    its first word.
    """
    capture = PlanCapture()
    connection = _Connection()

    plan = capture._plan_for(
        connection, "WITH moved AS (DELETE FROM x RETURNING *) SELECT * FROM moved", None, False
    )

    assert plan.refusal is not None
    assert connection.cursor_object.statements == []


def test_leading_whitespace_does_not_hide_a_select() -> None:
    capture = PlanCapture()
    connection = _Connection()

    plan = capture._plan_for(connection, "\n  select id from testapp_book", None, False)

    assert plan.root is not None


def test_executemany_has_no_single_plan_and_says_so() -> None:
    capture = PlanCapture()
    connection = _Connection()

    plan = capture._plan_for(connection, _SELECT, [(1,), (2,)], True)

    assert plan.root is None
    assert plan.refusal is not None
    assert "executemany" in plan.refusal
    assert connection.cursor_object.statements == []


def test_an_ordinary_capture_takes_no_plans_at_all() -> None:
    """The seam returns ``None`` on the path the plugin puts around every test."""
    assert QueryCapture()._plan_for(_Connection(), _SELECT, (1,), False) is None


def test_the_relations_a_plan_touched_are_asked_about_once_at_the_end() -> None:
    capture = PlanCapture()
    cursor = _Cursor(rows=[[(WHALE_JOIN,)], [("testapp_book",)]])
    connection = _Connection(cursor)
    capture._plan_for(connection, _SELECT, (1,), False)

    unanalyzed = capture._read_statistics()

    assert unanalyzed == ("testapp_book",)
    statistics = [sql for sql, _ in cursor.statements if "pg_stat_all_tables" in sql]
    assert len(statistics) == 1
    # Both relations the plan named, sorted so two runs send one statement.
    assert cursor.statements[-1][1] == [["testapp_author", "testapp_book"]]


def test_a_connection_the_block_closed_is_not_reopened_to_ask() -> None:
    """A diagnostic is not worth a reconnection, and saying nothing is honest here."""
    capture = PlanCapture()
    connection = _Connection()
    capture._plan_for(connection, _SELECT, (1,), False)
    connection.connection = None

    assert capture._read_statistics() == ()


def test_a_refused_statement_names_no_relations() -> None:
    capture = PlanCapture()
    connection = _Connection()

    capture._plan_for(connection, "INSERT INTO testapp_book DEFAULT VALUES", None, False)

    assert capture._read_statistics() == ()
