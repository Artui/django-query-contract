# django-query-contract

[![CI](https://github.com/Artui/django-query-contract/workflows/tests/badge.svg)](https://github.com/Artui/django-query-contract/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/django-query-contract.svg)](https://pypi.org/project/django-query-contract/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-query-contract.svg)](https://pypi.org/project/django-query-contract/)
[![Django versions](https://img.shields.io/pypi/djversions/django-query-contract.svg)](https://pypi.org/project/django-query-contract/)
[![Docs](https://img.shields.io/badge/docs-artui.github.io-blue.svg)](https://artui.github.io/django-query-contract/)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Artui/django-query-contract/gh-pages/coverage.json)](https://github.com/Artui/django-query-contract/actions/workflows/tests.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/pypi/l/django-query-contract.svg)](LICENSE)

A query-capture engine for Django, and a pytest plugin over it.

Every statement is recorded with a normalised SQL fingerprint and the call stack
that emitted it, through `connection.execute_wrapper()`. When a query-count
assertion fails, the failure gains a paragraph saying which shape repeated and
where it came from. When a block runs past the ceiling on Django's own query
log, that is reported instead of papered over.

## Install

```bash
pip install django-query-contract
```

The pytest plugin loads itself. There is nothing to add to `INSTALLED_APPS`, and
no fixture to request.

## It ships no count assertion, on purpose

`django_assert_num_queries` is the assertion. It is typed, it handles
`connection=` / `using=` and a custom failure note, and it yields the captured
queries. Keep writing it:

```python
def test_listing_is_flat(django_assert_num_queries, authors):
    with django_assert_num_queries(2):
        render_author_list()
```

When it fails, the failure now carries a diagnosis underneath it:

```
------------------------------ django-query-contract ------------------------------
13 statements captured: 13 on 'default'.

Repeated statement shapes:
  11 x  #1, #2, #3, #4, #5, #6, #7, #8, ...
       SELECT "shop_book"."id", "shop_book"."author_id", "shop_book"."title" FROM "shop_book" WHERE "shop_book"."author_id" = %s
       from shop/views.py:16 in render_author_list
  2 shape(s) ran once.
```

## The ceiling nobody mentions

`assertNumQueries` and `django_assert_num_queries` both count through
`CaptureQueriesContext`, which slices `connection.queries` between two absolute
indices. That log is a `deque(maxlen=connection.queries_limit)` -- 9000 by
default -- so once it rotates the indices no longer point at what they did.
Measured against Django 6.1:

| Already in the log | Queries in the block | Reported |
| --- | --- | --- |
| 0 | 8999 | 8999 |
| 0 | 9001 | 9000 |
| 8990 | 100 | 10 |
| 9000 | 5 | **0** |

The last row is a passing `django_assert_max_num_queries(1)` around five real
queries, and the regime it happens in -- thousands of statements in one block --
is exactly the N+1-at-scale case worth catching.

Capture here rides on `execute_wrapper`, which has no bound, so this package
raises a `QueryLogCeilingWarning` naming the test, the real count and the number
the assertion was handed.

## Reading the capture directly

```python
from django_query_contract import QueryCapture

with QueryCapture() as capture:
    render_author_list()

for fingerprint, records in capture.by_fingerprint().items():
    if len(records) > 1:
        print(len(records), records[0].call_site, fingerprint)
```

A `QueryRecord` carries the statement, its fingerprint, the connection alias and
vendor, the parameter count and the call stack. It carries **no parameters** --
a `bulk_create` is one execution and ten thousand values, and a runtime reader
of this capture has no business holding them -- and **no duration**, because a
performance assertion that mentions milliseconds is a flaky test with extra
steps.

`QueryCapture.from_capture_context(...)` builds one from the
`CaptureQueriesContext` that `django_assert_num_queries` yields. It is honestly
degraded: no call stacks, no parameter counts, and no ceiling, because a count
taken from a rotated deque cannot report what it lost.

## Where the capture stops

`execute_wrapper` wraps Django's cursor wrapper, so it sees `execute` and
`executemany` and nothing else. A statement issued on the raw driver connection
is invisible, and so is a driver API that is neither -- psycopg 3's
`cursor.copy()`, for instance. Django's own query log has the same blind spot,
so the two agree, and there is a test that pins it rather than a note that
assumes it.

## Turning it off

```ini
[pytest]
query_contract = false
query_contract_stack_depth = 25
```

or `--no-query-contract` for one run.

## Status

Early. The capture engine and the pytest diagnosis. N+1 by
(call stack, fingerprint), the growth assertion, call-site attribution and plan
capture come next.

Full documentation: <https://artui.github.io/django-query-contract/>

## License

MIT
