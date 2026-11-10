from __future__ import annotations

import pytest

from django_query_contract import normalise_sql


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        # A variable-width IN list is one shape at every width.
        (
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s)',
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s)',
        ),
        (
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s, %s, %s)',
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s)',
        ),
        (
            'INSERT INTO "b" ("x", "y") VALUES (%s, %s), (%s, %s), (%s, %s)',
            'INSERT INTO "b" ("x", "y") VALUES (%s)',
        ),
        ('SELECT "a"."id" FROM "a" LIMIT 21', 'SELECT "a"."id" FROM "a" LIMIT %s'),
        (
            'SELECT "a"."id" FROM "a" LIMIT 10 OFFSET 340',
            'SELECT "a"."id" FROM "a" LIMIT %s OFFSET %s',
        ),
        ('SAVEPOINT "s8384995712_x1"', "SAVEPOINT <savepoint>"),
        ('RELEASE SAVEPOINT "s8384995712_x2"', "RELEASE SAVEPOINT <savepoint>"),
        ('ROLLBACK TO SAVEPOINT "s8384995712_x3"', "ROLLBACK TO SAVEPOINT <savepoint>"),
        ("SAVEPOINT `s1_x1`", "SAVEPOINT <savepoint>"),
        ("SAVEPOINT [s1_x1]", "SAVEPOINT <savepoint>"),
        ("SAVEPOINT s1_x1", "SAVEPOINT <savepoint>"),
        ("SELECT * FROM a WHERE name = 'bob'", "SELECT * FROM a WHERE name = %s"),
        ("SELECT * FROM a WHERE name = 'o''brien'", "SELECT * FROM a WHERE name = %s"),
        ("SELECT * FROM a WHERE total > 12.5", "SELECT * FROM a WHERE total > %s"),
        ("SELECT  1\n  FROM   a", "SELECT %s FROM a"),
    ],
)
def test_what_collapses(sql: str, expected: str) -> None:
    assert normalise_sql(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        # Digits belonging to an identifier are not values.
        'SELECT "col2" FROM "app_address2"',
        "SELECT col1, col2 FROM t1",
        'SELECT * FROM "2fa_tokens"',
        'SELECT "a"."id" FROM "a" WHERE "a"."x" = %s',
    ],
)
def test_what_survives(sql: str) -> None:
    assert normalise_sql(sql) == sql


def test_two_different_shapes_do_not_collide() -> None:
    """The rules collapse data, never structure."""
    one = normalise_sql('SELECT "a"."id" FROM "a" WHERE "a"."x" = %s')
    two = normalise_sql('SELECT "a"."id" FROM "a" WHERE "a"."y" = %s')
    three = normalise_sql('SELECT "b"."id" FROM "b" WHERE "b"."x" = %s')
    assert len({one, two, three}) == 3


def test_a_quoted_savepoint_word_is_not_mangled() -> None:
    """String literals are reduced first, so the savepoint rule cannot reach inside one."""
    assert normalise_sql("SELECT 'SAVEPOINT abc'") == "SELECT %s"


def test_an_insert_keeps_its_column_list() -> None:
    """Collapsing a placeholder run loses arity, which the column list already carries."""
    one = normalise_sql('INSERT INTO "b" ("x") VALUES (%s)')
    two = normalise_sql('INSERT INTO "b" ("x", "y") VALUES (%s, %s)')
    assert one != two


def test_the_result_is_cached() -> None:
    """The same statement is fingerprinted once."""
    sql = 'SELECT "cached"."id" FROM "cached" WHERE "cached"."x" = %s'
    first = normalise_sql(sql)
    second = normalise_sql("".join([sql[:10], sql[10:]]))
    assert first is second
