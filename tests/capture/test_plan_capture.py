from __future__ import annotations

from typing import Any

import pytest

from django_query_contract import PlanCapture, PlansUnsupported, QueryCapture
from tests.plan_payloads import WHALE_JOIN

_SELECT = "SELECT id FROM testapp_book WHERE author_id = %s"


class QueryCanceled(Exception):
    """psycopg 3's cancellation error, by name only."""


class QueryCanceledError(Exception):
    """psycopg 2's spelling of the same thing, which is a different word."""


class _Cursor:
    """A driver cursor that remembers what it was asked and answers with real JSON."""

    def __init__(
        self, *, rows: list[list[tuple[Any, ...]]] | None = None, fails: Exception | None = None
    ):
        self.statements: list[tuple[str, Any]] = []
        self.closed = False
        # Rows exactly as a driver hands them back: one list per statement.
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
        autocommit: bool = True,
    ):
        self.alias = alias
        self.in_atomic_block = in_atomic_block
        self.autocommit = autocommit
        self.cursor_object = cursor if cursor is not None else _Cursor()
        self.connection: _Driver | None = _Driver(self.cursor_object)

    def get_autocommit(self) -> bool:
        """Django's second transaction question, and the double used to lack it."""
        return self.autocommit


def _statements(cursor: _Cursor) -> list[str]:
    return [sql for sql, _ in cursor.statements]


def test_a_connection_that_is_not_postgres_is_refused_by_name() -> None:
    """The whole refusal, decided from a vendor string and nothing else."""
    capture = PlanCapture()

    refusal = capture.refusal()

    assert refusal is not None
    assert "is sqlite" in refusal
    assert "worse than no assertion" in refusal


def test_entering_a_capture_that_cannot_produce_a_plan_raises_before_anything_runs() -> None:
    """It raises rather than degrading, and that is the whole class."""
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
    """The same split Django's own cursor wrapper makes, for the same reason."""
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
    """PostgreSQL refuses SAVEPOINT outside a transaction block outright."""
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
    """A driver error can quote a bound value, and this package retains none."""
    capture = PlanCapture()
    connection = _Connection(_Cursor(fails=RuntimeError("value 'hunter2' is out of range")))

    plan = capture._plan_for(connection, _SELECT, (1,), False)

    assert plan.refusal is not None
    assert "EXPLAIN raised RuntimeError" in plan.refusal
    assert "hunter2" not in plan.refusal


def test_a_cancelled_explain_says_what_to_do_about_it() -> None:
    """The one failure with a remedy, so it is the one that gets named."""
    cursor = _Cursor(fails=QueryCanceled("canceling statement due to statement timeout"))

    plan = PlanCapture()._explain(_Connection(cursor), "SELECT 1", None)

    assert plan.refusal is not None
    assert "QueryCanceled" in plan.refusal
    assert "statement_timeout" in plan.refusal
    assert "analyze=False" in plan.refusal
    assert "canceling statement" not in plan.refusal


def test_psycopg2_spells_cancellation_differently_and_is_recognised_too() -> None:
    """Two drivers, two class names, one condition. Neither is imported here."""
    cursor = _Cursor(fails=QueryCanceledError("canceling statement due to statement timeout"))

    plan = PlanCapture()._explain(_Connection(cursor), "SELECT 1", None)

    assert plan.refusal is not None
    assert "statement_timeout" in plan.refusal


def test_any_other_failure_says_only_which_class_arrived() -> None:
    """The remedy is named where there is one, and nowhere else."""
    cursor = _Cursor(fails=ValueError("a bound value: 'secret@example.com'"))

    plan = PlanCapture()._explain(_Connection(cursor), "SELECT 1", None)

    assert plan.refusal is not None
    assert "ValueError" in plan.refusal
    assert "statement_timeout" not in plan.refusal
    assert "secret@example.com" not in plan.refusal


def test_a_transaction_django_did_not_open_is_still_savepointed() -> None:
    """`in_atomic_block` False and autocommit off: the driver is in a transaction."""
    cursor = _Cursor()
    connection = _Connection(cursor, in_atomic_block=False, autocommit=False)

    PlanCapture()._explain(connection, "SELECT 1", None)

    assert "SAVEPOINT django_query_contract_plan" in _statements(cursor)
    assert "RELEASE SAVEPOINT django_query_contract_plan" in _statements(cursor)


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
    """A data-modifying CTE has to be written ``WITH ..."""
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


def test_the_indexes_of_every_relation_a_plan_touched_are_asked_for_once() -> None:
    """The catalogue half of the index report, and the only CREATE INDEX it prints."""
    capture = PlanCapture()
    cursor = _Cursor(
        rows=[
            [(WHALE_JOIN,)],
            [
                ("testapp_book", "CREATE INDEX book_author ON testapp_book (author_id)"),
                ("testapp_book", "CREATE UNIQUE INDEX book_pkey ON testapp_book (id)"),
                ("testapp_author", "CREATE UNIQUE INDEX author_pkey ON testapp_author (id)"),
            ],
        ]
    )
    connection = _Connection(cursor)
    capture._plan_for(connection, _SELECT, (1,), False)

    indexes = capture._read_indexes()

    assert indexes == {
        "testapp_book": (
            "CREATE INDEX book_author ON testapp_book (author_id)",
            "CREATE UNIQUE INDEX book_pkey ON testapp_book (id)",
        ),
        "testapp_author": ("CREATE UNIQUE INDEX author_pkey ON testapp_author (id)",),
    }
    asked = [sql for sql, _ in cursor.statements if "pg_get_indexdef" in sql]
    assert len(asked) == 1
    assert cursor.statements[-1][1] == [["testapp_author", "testapp_book"]]


def test_a_capture_that_planned_over_nothing_knows_of_no_indexes() -> None:
    """Absent rather than empty: an empty tuple would claim a table has none."""
    assert PlanCapture()._read_indexes() == {}
    assert PlanCapture().relation_indexes == {}
