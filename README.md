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

N+1 -- one statement shape, executed more than once from one call path:
  11 x  from shop/views.py:16 in render_author_list
       SELECT "shop_book"."id", "shop_book"."author_id", "shop_book"."title" FROM "shop_book" WHERE "shop_book"."author_id" = %s
       queries #1, #2, #3, #4, #5, #6, #7, #8, ...
  2 statement(s) were not repeated from any one call path. They came from:
  1 x  from shop/views.py:15 in render_author_list
       SELECT "shop_author"."id", "shop_author"."name" FROM "shop_author"
  1 x  from shop/middleware.py:12 in __call__
       SELECT "django_session"."session_key" FROM "django_session" WHERE ...
```

## N+1 by construction, with nothing to tune

**More than one execution with the same normalised SQL and the same call stack
is an N+1.** No threshold, no confidence score, no rule about lazy loads: the
same line ran the same statement again with different data instead of asking
once.

Four Python N+1 detectors are dead on PyPI -- `nplusone` (2018, 1068 stars, and
still what the blog posts recommend), `django-query-capture`, `django-nplusone`
and `django-explain`. The probable reason is that they classified by rule, so
they cried wolf and were removed. A detector nobody disables is a different
package from a detector that finds more.

The identity is the **whole call stack**, not the call site. Two callers of one
`get_books(author)` helper are two defects with two fixes, and a report grouped
by call site would name the one line that is fine. The identity does *not*
include the connection, so a loop that queries two databases stays one finding.
A statement with no call stack -- everything in a capture rebuilt from a
`CaptureQueriesContext` -- is not grouped at all, because guessing there would
manufacture a finding out of a gap in the input.

Nothing fails on a finding. A batched `bulk_create` is one shape run a hundred
times from one line, structurally identical to the defect, so it is reported
like any other repetition and costs nobody a red build. That is what keeps this
from crying wolf, rather than an exemption list -- which would be the first
tunable.

```bash
pytest --n-plus-one
```

lists every finding in the run, worst first, and changes no outcome:

```
=============================== django-query-contract ===============================
2 N+1 finding(s), most repeated first:
  40 x  from shop/views.py:16 in render_author_list
       in tests/test_views.py::test_author_listing
       SELECT "shop_book"."id", "shop_book"."author_id" FROM "shop_book" WHERE ...
       queries #3, #4, #5, #6, #7, #8, #9, #10, ...
```

Or read them yourself:

```python
from django_query_contract import QueryCapture, find_n_plus_one

with QueryCapture(using="default") as capture:
    view(request)

for finding in find_n_plus_one(capture):
    print(finding.count, finding.call_site, finding.fingerprint)
```

## The growth assertion

A count asserted against three fixture rows is asserted against a defect that
costs one query per row, because at three rows a prefetch and a loop cost almost
the same. **Run the block at two sizes of world instead and ask whether the
count moved.**

```python
from django_query_contract import assert_query_growth


def test_the_author_listing_does_not_grow(world):
    assert_query_growth(world, lambda: render_author_list())
```

A hundred rows, then a thousand, and the two counts have to be equal. Ruby has
had this since `n_plus_one_control`; no Python package does it.

`world` is anything callable as `world(factor)` returning a context manager -- a
five-line `@contextmanager` in your own `conftest.py`, or
[`django-data-shape`](https://pypi.org/project/django-data-shape/)'s
`scale_fixture`. It is a shape rather than a dependency, because a growth
assertion needs *scale* (a hundred rows against a thousand, any backend) and not
*size*.

**Never open a capture around the call that builds the world.** A world's own
loader emits statements, and off PostgreSQL they are ordinary inserts, so the
count grows with the factor: measured on a two-table world, 8 statements at
factor 1 and 17 at factor 10 on SQLite. A harness reading that reports a
confident `O(N)` for an `O(1)` block. This one opens the capture *inside* the
world, and you never write `QueryCapture` at all -- there is nowhere to put it
in the wrong place.

```text
The query count is not constant across the scale factors.

  factor  1    4 rows    3 statements
  factor 10   40 rows   21 statements

A constant count runs the same statements whatever the data, so every factor
has to produce the same number. Factor 1 ran 3 and factor 10 ran 21.

At factor 10 the block ran:
21 statements captured: 21 on 'default'.

N+1 -- one statement shape, executed more than once from one call path:
  20 x  from shop/views.py:16 in render_author_list
       SELECT "shop_book"."id", "shop_book"."author_id" FROM "shop_book" WHERE ...
       queries #1, #2, #3, #4, #5, #6, #7, #8, ...
```

`Growth.LINEAR` is how genuine bulk work says so, and it still refuses a nested
loop. Both claims are exact integer comparisons rather than a fitted curve: a
fit needs a tolerance, a fit floor and a rule for what counts as linear, and a
growth assertion that is itself flaky gets deleted and takes the idea with it.

Full detail, including the one remaining way to make it flaky and the `warm_up`
that fixes it, is in
[Growth assertions](https://artui.github.io/django-query-contract/growth/).

## Where every query came from

A finding needs a repetition, so before this a capture named a call site only
where an N+1 rendered one. **Every statement has an answer**, repeated or not:

```python
from django_query_contract import QueryCapture, group_by_call_site

with QueryCapture() as capture:
    render_author_list()

for attribution in group_by_call_site(capture):
    print(attribution.count, attribution.call_site)
```

```text
40 shop/views.py:31 in author_list
 3 shop/serializers.py:88 in to_representation
 1 shop/middleware.py:12 in __call__
```

The call site is the innermost frame outside Django, and that is the whole rule.
It needs no project root and no depth setting, and when the stack reaches no
such frame the answer is `None` rather than a guess -- "it came from
`django/db/models/query.py`" is true of every query ever executed.

**Grouping by call site merges what a finding keeps apart, on purpose.** Two
callers of one `get_books()` helper are two findings, because the identity of a
defect is the whole call stack and the helper's line is the one line that is
fine. They are one *attribution*, because that line is genuinely where the
statements were emitted. Both are true, and attribution is allowed the merge
only because it claims nothing about defects: a group of forty is not a finding
of forty, it is forty statements and an address.

That is also why the frame rule stays on the display side and out of every
identity -- a rule about which frames matter is a knob, and a knob in a
detector's identity is how the four dead ones came to cry wolf.

[`django-sqlcommenter`](https://pypi.org/project/django-sqlcommenter/) answers
the same question from the other end, by annotating the SQL so a `callsite=` tag
reaches `pg_stat_activity` and the slow-query log. That is a production reader
and a different delivery: at test time there is no database log to read, the
answer has to arrive as a Python object, and the statement should not have to
change to carry it. Running both is reasonable.

Full detail, including why there is no run-wide listing, is in
[Call-site attribution](https://artui.github.io/django-query-contract/attribution/).

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

## Plans, where a plan can mean something

PostgreSQL only, and it **skips rather than passing** anywhere else.

```python
def test_the_dashboard(db, orders, query_plans):
    dashboard()

    assert not query_plans.unanalyzed_relations
```

`EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)` on every statement that
begins with `SELECT`, taken at execution time because that is the one moment the
statement and its parameters are both in hand. Two findings, and there are two
because only two can be stated without a threshold:

```text
Plan findings -- what PostgreSQL's own output states:
  planner blind  2 executions, one estimate of 20 rows, actuals 20,323, 6
       SELECT "testapp_order"."id" FROM "testapp_order" INNER JOIN ...
       from tests/test_dashboard.py:31 in whales, tests/test_dashboard.py:32 in tail
       queries #0, #1
  spilled to disk  Sort, external merge, 14,208 kB
       SELECT "testapp_order"."id" FROM "testapp_order" ORDER BY ...
       from tests/test_dashboard.py:44 in test_ordering
       queries #4

Where the planner was furthest out (reported, not judged -- a node under a
LIMIT is meant to fall short):
  1,016.1x  #0  Nested Loop: expected 20 rows, 20,323 arrived
```

**Planner blindness** is two executions of one statement shape whose plans agree
exactly on the row count and whose measured rows do not: `==` and `!=`, and no
magnitude anywhere. Measured on a Zipf fan-out of 400,000 rows over 20,000
parents -- across a join PostgreSQL has only `n_distinct` for the edge, so a
whale and a tail row both come out at 20 estimated rows against 20,323 and 6
actual. **A spill** is PostgreSQL saying `work_mem` was not enough, so the
threshold is the database's own.

The estimate-versus-actual ratio is reported on every node and **classified
nowhere**. "Expected 20 rows, 20,323 arrived" is a fact; "more than fifty times
out is a defect" is a policy about size, and this package does not write those.
The two candidate findings that needed one -- a sequential scan over a row
threshold, a nested loop with a large inner -- were declined.

**Every row count on a plan node is per loop**, which is PostgreSQL's own
convention and the one thing about these numbers that changes meaning as a
database grows. The same `SELECT COUNT(*)` over 1,200,000 rows reports
`Rows Removed by Filter: 1124098` in one process and `374699` in three, because
the server reached for two workers on its own -- so an assertion written against
a small world is written against a number the big one does not report. Read
`node.total_actual_rows` and `node.total_rows_removed_by_filter`, which multiply
by `loops` and are unchanged where it is 1. There is deliberately **no total for
the estimate**: the planner divides that one by a number the plan does not print.

A plan over ten rows is a lie, so a capture also asks the catalogue whether the
tables it planned over have ever been analyzed, and says so before anything
else. [django-data-shape](https://github.com/Artui/django-data-shape) is what
builds a database worth taking a plan over.

It costs about 1.7x the block's own time, because `EXPLAIN ANALYZE` runs the
statement a second time. It does not change what `django_assert_num_queries`
counts -- the `EXPLAIN` goes out under Django's cursor, not through it -- and a
failing `EXPLAIN` costs a plan rather than your transaction, because it runs
under a savepoint. See
[plan capture](https://artui.github.io/django-query-contract/plans/).

## Index advice: the evidence, and no recommendation

"These twelve statements sequentially scanned a two-million-row table, here are
the `CREATE INDEX` statements" is the output people want, and **it is not here,
on purpose**. Three routes to it were tried against a real server and all three
ended in a threshold -- including the one that looks threshold-free, comparing a
table read sequentially by one statement against the same table reached by index
by another. Two statements filtering *different columns* of one table are not two
measurements of one thing, and the sequential read that keeps every row it looks
at is the plan PostgreSQL should have chosen.

So the facts are printed and the judgement is left to you:

```text
Relations these plans read, and how PostgreSQL reached them:
  No index is recommended below, and that is a decision rather than an omission.
  Whether one is worth adding is a judgement about size -- how many rows is too
  many to read -- and this package states what the server measured instead.
  testapp_order  2 reads, 1 without an index
       filtering ((reference)::text = %s::text)
       most one read discarded: 99,999 rows, keeping 1
       read through testapp_order_customer_id_85c0ed1a
       from tests/test_orders.py:13 in test_dashboard
       PostgreSQL has 2 indexes on testapp_order:
         CREATE INDEX testapp_order_customer_id_85c0ed1a ON public.testapp_order USING btree (customer_id)
         CREATE UNIQUE INDEX testapp_order_pkey ON public.testapp_order USING btree (id)
```

The only `CREATE INDEX` statements this package prints are the ones that already
exist, in PostgreSQL's own words. Put them beside the filter above and the gap is
visible.

The predicate is printed as a shape, and that is not cosmetic: `EXPLAIN` renders
it with the bound value spelled out -- `((reference)::text =
'601980.6826913885'::text)` -- so the value is taken back out by the same
`normalise_sql` rules the fingerprint is made with. This package retains no
parameters, and a plan node was the one place that promise could have quietly
stopped being true.

## Reading the capture directly

```python
from django_query_contract import QueryCapture

with QueryCapture() as capture:
    render_author_list()

for fingerprint, records in capture.by_fingerprint().items():
    print(len(records), fingerprint)
```

A `QueryRecord` carries the statement, its fingerprint, the connection alias and
vendor, the parameter count, the call stack, and -- where one was taken -- the
plan. It carries **no parameters** --
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

or `--no-query-contract` for one run. `query_contract_stack_depth` is also what
widens the window the N+1 identity is formed from -- see
[N+1 detection](https://artui.github.io/django-query-contract/n-plus-one/).

## Status

Early. The capture engine, the pytest diagnosis, N+1 by
(call stack, fingerprint), the growth assertion, call-site attribution, plan
capture, and the relation report that index advice reduced to.

Full documentation: <https://artui.github.io/django-query-contract/>

## License

MIT
