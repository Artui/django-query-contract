# Plan capture

What PostgreSQL decided to do with a statement, what it then did, and where the
two disagree.

```python
from django_query_contract import PlanCapture, format_query_plans


def test_the_dashboard(db, orders):
    with PlanCapture() as plans:
        dashboard()

    print(format_query_plans(plans))
```

Under pytest there is a fixture that does the same thing and skips where a plan
could not mean anything:

```python
def test_the_dashboard(db, orders, query_plans):
    dashboard()

    assert not query_plans.unanalyzed_relations
```

## It is PostgreSQL-only, and it refuses rather than degrading

Every other honest degradation in this package reports and carries on. A capture
rebuilt from a `CaptureQueriesContext` says it has no call stacks; a block above
Django's query-log ceiling says the count taken from that log is wrong. Those are
still measurements.

A plan capture on SQLite would not be a degraded measurement. It would be an
empty one, and an empty one is indistinguishable from a healthy one -- so an
assertion over it passes because the backend could not check it, which is the
exact failure this package exists to expose.

So `PlanCapture` raises `PlansUnsupported` on entry, before a statement has run,
and the `query_plans` fixture turns that into a **skip** carrying the same
sentence. A test that never ran is honest; a test that ran against a database
with no planner is not.

```text
SKIPPED [1] Plan capture needs PostgreSQL; connection 'default' is sqlite.
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and the plan vocabulary this package
reads are PostgreSQL's, and a plan assertion that passed because the backend
could not check it is worse than no assertion.
```

By default every configured connection has to be PostgreSQL, because a capture
that quietly skipped the one it could not explain would be the silent gap the
class exists to refuse. A project whose second database is a SQLite cache names
the one it means by overriding a fixture:

```python
# conftest.py
import pytest


@pytest.fixture
def query_plan_connections():
    return "default"
```

## A plan over ten rows is a lie, and the vendor check cannot see that

The backend is the easy half. The harder half is a database that *is* PostgreSQL
and was given nothing to reason with: rows loaded in a fixture and never
analyzed leave the planner guessing from a default selectivity, and the plan it
prints is confident and meaningless. Measured while this package was designed --
two million rows never analyzed produced a bitmap heap scan estimated at 10,000
rows for two predicates whose real answers were 30,298 and 1,959,743.

So a capture asks the catalogue, once, at the end of the block:

```python
assert not plans.unanalyzed_relations
```

and the report says it before anything else, because it can invalidate
everything under it:

```text
  PostgreSQL has never gathered statistics for testapp_order.
  Every plan below is a guess: the planner is working from a default
  selectivity rather than from these tables. Load the rows, then ANALYZE.
```

It says nothing about whether the tables are *big enough*, and it cannot: "ten
rows is too few" is a number, and a number is the knob this package refuses
everywhere else. [django-data-shape](https://github.com/Artui/django-data-shape)
is what builds a database worth taking a plan over -- it owns the ordering,
generate then load then index then `ANALYZE`, so the analyze-then-load trap
cannot happen.

## What a finding is

Two kinds, and there are two because only two can be stated without a threshold.

### The planner was blind

Two or more executions of the same normalised SQL whose plans agree **exactly**
on how many rows the query would produce, and whose measured rows do not. There
is no magnitude in that sentence -- only `==` and `!=`.

```text
  planner blind  2 executions, one estimate of 20 rows, actuals 20,323, 6
       SELECT "testapp_order"."id" FROM "testapp_order" INNER JOIN ...
       from tests/test_dashboard.py:31 in whales, tests/test_dashboard.py:32 in tail
       queries #0, #1
```

That pair is measured, not invented: a Zipf fan-out of 400,000 rows over 20,000
parents, joined through the parent rather than through the foreign key column.
Across a join PostgreSQL has only `n_distinct` for the edge, so it hands every
value of the join key the same average -- and an average is the one number that
is wrong for both ends of a skewed distribution.

**One measurement cannot make this claim.** It cannot separate "the planner is
wrong about this query" from "the planner is right on average and this row is
unusual". That is the same rule the [growth assertion](growth.md) keeps: a claim
about a shape needs two points. A growth claim needs two worlds; a blindness
claim needs two executions.

**Its identity is the statement shape and deliberately not the call stack**,
which is the opposite of how an [N+1](n-plus-one.md) is identified. The rule
behind both is one rule: a finding is keyed on what the accused can see. An N+1
accuses your code, so it is keyed on your code's call path. This accuses the
planner, which is handed a statement and never hears about the stack.

### Something spilled to disk

A sort that reports `Sort Space Type: Disk`, a hash join that needed more than
one batch, or a hash aggregate reporting disk usage. PostgreSQL states all three
itself, and the threshold that decided them is `work_mem` -- the configuration
of the database under test, not a number chosen here.

```text
  spilled to disk  Sort, external merge, 14,208 kB
       SELECT "testapp_order"."id" FROM "testapp_order" ORDER BY ...
       from tests/test_dashboard.py:44 in test_ordering
       queries #4
```

It is as much a finding about the server as about the query, which is worth
knowing before acting on one.

### What is reported and never classified

The estimate-versus-actual ratio is on every node, and no code here turns it into
a verdict:

```text
Where the planner was furthest out (reported, not judged -- a node under a
LIMIT is meant to fall short):
  1,016.1x  #0  Nested Loop: expected 20 rows, 20,323 arrived
       SELECT "testapp_order"."id" FROM "testapp_order" INNER JOIN ...
```

"The planner expected 20 rows and 20,323 arrived" is a fact about the plan.
"More than fifty times out is a defect" is a policy about size, and this package
does not write those. The caveat printed with the block is the reason: the
commonest large ratio has no defect under it at all, because a node under a
`LIMIT` stops early by design.

### What was declined

The design this package came from listed four candidate findings. Two are
missing on purpose:

- **a sequential scan over a row threshold** -- how many rows makes a scan wrong?
- **a nested loop with a large inner** -- how large is large?

Both are numbers wearing a description, and a number is a knob. Four Python N+1
detectors are dead on PyPI, and the most probable reason is that they classified
by rule, cried wolf, and were uninstalled. A detector nobody disables is a
different package from a detector that finds more.

## Nothing fails on a finding

The same rule as everywhere else here. A finding is a diagnosis printed under a
failure somebody else's assertion produced, or a report a caller asked for. A
failing test that used the `query_plans` fixture gains a section:

```text
------------------------- django-query-contract plans --------------------------
6 statements captured, 4 of them explained.

Plan findings -- what PostgreSQL's own output states:
  planner blind  2 executions, one estimate of 20 rows, actuals 20,323, 6
...
```

## What it costs, and what runs twice

`EXPLAIN ANALYZE` **executes** the statement. Measured against PostgreSQL 16 on
a shaped 400,000-row world, a two-statement block took 8.9 ms on its own and
14.8 ms with plan capture -- about **1.7x**, which is what running each statement
twice buys. With `analyze=False` it was 9.1 ms, or 1.02x, because the server only
plans.

`ANALYZE` is the default anyway: a plan with no measurement in it can produce no
finding at all, and a plan capture that can produce no finding is the vacuous
pass this package exists to refuse. `PlanCapture(analyze=False)` is there for
reading the planner's choice without paying for it, and the report says that
nothing was measured rather than showing an empty findings block.

Because the statement runs twice, **only a statement beginning with `SELECT` is
explained**. Explaining an `INSERT` would perform the insert, and then the
statement would run again for real. That is why the rule is "begins with SELECT"
rather than "does not begin with INSERT": a data-modifying CTE is written
`WITH ... INSERT`, so the dangerous statement does not announce itself in its
first word. Everything skipped is counted in the report with the reason:

```text
2 statement(s) carried no plan:
  2 x  a statement that does not begin with SELECT was not explained: EXPLAIN
       ANALYZE executes what it is given, so explaining a write would perform
       it, and then the statement would run again for real.
```

The one hole, stated rather than glossed: a `SELECT` calling a volatile function
that writes will have that function called twice. No reading of the statement
text could know, and this package does not parse SQL.

## Two things it will not do to your test

**It does not change what `django_assert_num_queries` counts.** The `EXPLAIN`
goes out on the driver connection, underneath Django's cursor, so neither it nor
the savepoints around it reach `connection.queries_log` -- which is what that
assertion counts through. The obvious implementation, `connection.cursor()`,
would have inflated every count in a suite that turned plan capture on. There is
a test that runs both together and pins it.

**It does not break your transaction.** A failing `EXPLAIN` inside an atomic
block would leave the connection in "current transaction is aborted, commands
ignored until end of transaction block", and every later statement in the test
would fail. So the `EXPLAIN` runs under a savepoint, and a statement PostgreSQL
declines to explain costs a plan rather than the test. Both halves are tested
against a real server: one that the savepoint holds, and one that removing it
poisons the transaction.

The refusal names the exception class and never its message, because a driver
error can quote a bound value and this package
[retains no parameters](reference.md).

## What is not here yet

Index advice -- "these twelve statements sequentially scanned a two-million-row
table, here are the `CREATE INDEX` statements" -- is the output people actually
want, and it falls out of having plans plus call sites. The record already
carries what it needs: each node keeps its relation, its filter and the rows that
filter threw away, beside the call stack that emitted the statement.
