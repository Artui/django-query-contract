"""The fingerprint keeps what repeats and drops what varies.

Every case here came off the wire: an ``execute_wrapper`` over an ORM session
recorded what Django actually hands a cursor, and each rule exists because one
of those statements needed it. The two halves that matter are symmetrical --
what must collapse, so a loop reads as one shape, and what must not, so two
different statements stay different.
"""

from __future__ import annotations

import pytest

from django_query_contract import normalise_sql


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        # A variable-width IN list is one shape at every width. This is what
        # prefetch_related and pk__in emit, and the width is the size of the
        # data rather than the shape of the query.
        (
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s)',
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s)',
        ),
        (
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s, %s, %s)',
            'SELECT "a"."id" FROM "a" WHERE "a"."id" IN (%s)',
        ),
        # bulk_create: one statement, a VALUES group per row.
        (
            'INSERT INTO "b" ("x", "y") VALUES (%s, %s), (%s, %s), (%s, %s)',
            'INSERT INTO "b" ("x", "y") VALUES (%s)',
        ),
        # Django inlines LIMIT and OFFSET rather than binding them, so a
        # paginating loop would otherwise be a new shape on every page.
        ('SELECT "a"."id" FROM "a" LIMIT 21', 'SELECT "a"."id" FROM "a" LIMIT %s'),
        (
            'SELECT "a"."id" FROM "a" LIMIT 10 OFFSET 340',
            'SELECT "a"."id" FROM "a" LIMIT %s OFFSET %s',
        ),
        # The savepoint identifier carries a thread id and a counter, so it is
        # different for every atomic block and different again next run. There
        # are no parameters on these statements at all, so a normaliser that
        # only strips placeholders leaves every nested atomic() looking unique.
        ('SAVEPOINT "s8384995712_x1"', "SAVEPOINT <savepoint>"),
        ('RELEASE SAVEPOINT "s8384995712_x2"', "RELEASE SAVEPOINT <savepoint>"),
        ('ROLLBACK TO SAVEPOINT "s8384995712_x3"', "ROLLBACK TO SAVEPOINT <savepoint>"),
        ("SAVEPOINT `s1_x1`", "SAVEPOINT <savepoint>"),
        ("SAVEPOINT [s1_x1]", "SAVEPOINT <savepoint>"),
        ("SAVEPOINT s1_x1", "SAVEPOINT <savepoint>"),
        # The escape hatches inline their values: .raw(), RawSQL, .extra(), a
        # hand-written cursor.execute, and every migration.
        ("SELECT * FROM a WHERE name = 'bob'", "SELECT * FROM a WHERE name = %s"),
        ("SELECT * FROM a WHERE name = 'o''brien'", "SELECT * FROM a WHERE name = %s"),
        ("SELECT * FROM a WHERE total > 12.5", "SELECT * FROM a WHERE total > %s"),
        # Whitespace, so a multi-line raw statement matches its one-line twin.
        ("SELECT  1\n  FROM   a", "SELECT %s FROM a"),
    ],
)
def test_what_collapses(sql: str, expected: str) -> None:
    assert normalise_sql(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        # Digits belonging to an identifier are not values. Over-collapsing here
        # is the failure mode that would make two different tables one shape,
        # which is a false positive of exactly the kind that got four earlier
        # N+1 detectors deleted.
        'SELECT "col2" FROM "app_address2"',
        "SELECT col1, col2 FROM t1",
        'SELECT * FROM "2fa_tokens"',
        # Different tables, different columns, different operators: all distinct.
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
    """String literals are reduced first, so the savepoint rule cannot reach inside one.

    Run the other way round the savepoint rule swallows the closing quote and
    leaves an unbalanced literal behind -- stable, but nonsense in a report.
    """
    assert normalise_sql("SELECT 'SAVEPOINT abc'") == "SELECT %s"


def test_an_insert_keeps_its_column_list() -> None:
    """Collapsing a placeholder run loses arity, which the column list already carries."""
    one = normalise_sql('INSERT INTO "b" ("x") VALUES (%s)')
    two = normalise_sql('INSERT INTO "b" ("x", "y") VALUES (%s, %s)')
    assert one != two


def test_the_result_is_cached() -> None:
    """The same statement is fingerprinted once. The cache is the whole reason it is cheap."""
    sql = 'SELECT "cached"."id" FROM "cached" WHERE "cached"."x" = %s'
    first = normalise_sql(sql)
    # A distinct but equal string: the cache keys on value, not identity, which
    # is what makes it hit at all -- Django builds its SQL fresh every call.
    second = normalise_sql("".join([sql[:10], sql[10:]]))
    assert first is second
