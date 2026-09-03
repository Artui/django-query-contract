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

### The cheapest assertion in the package, and the one that pays

`PlanCapture(analyze=False)` plus `assert not plans.unanalyzed_relations` costs
about **1.02x** -- the server plans and does not execute -- which is cheap enough
to leave switched on permanently rather than reaching for when something looks
slow. Nothing else here has that property: the measured findings are worth more
per run and cost enough that you turn them on deliberately.

It is also the check most likely to fire on a suite that has never used this
package. A consumer ran it for the first time and found that **their entire
performance fixture had never been `ANALYZE`d** -- every plan that suite had
taken since it was written was over tables the planner could not see. One
`ANALYZE` took the suite from 531s to 210s.

If you adopt one thing from this page, adopt this one, and add the measured
findings afterwards.

## Every row count is per loop, and that changes what an assertion means

`actual_rows`, `rows_removed_by_filter` and `estimated_rows` are what PostgreSQL
printed, and PostgreSQL prints them **per loop**. Over a small database every
node runs once, `loops` is 1, and the printed number is the whole truth. Over a
big one it is a share, and nothing in the plan announces the change except a loop
count nobody was reading.

Two things cause it, and they are not the same thing:

- a **parallel** node ran once in each participating process, so the work was
  *divided*;
- the inner side of a **nested loop** ran once per row of the outer side, so the
  work was *repeated*.

Measured on one statement over 1,200,000 rows, run twice with nothing changed but
whether parallelism was allowed:

| | one process | three processes |
| --- | --- | --- |
| `Rows Removed by Filter` | 1,124,098 | 374,699 |
| `Actual Rows` | 75,902 | 25,301 |
| `Actual Loops` | 1 | 3 |

Both plans did the same work. An assertion written against the left-hand column
is written against numbers the right-hand plan does not report, and a suite that
grew its fixtures past the point where PostgreSQL reaches for a second process
would see it change with no error and no warning.

### So read the totals

```python
node.total_actual_rows  # actual_rows multiplied by loops
node.total_rows_removed_by_filter  # rows_removed_by_filter multiplied by loops
node.parallel_aware  # which of the two causes the loops were
```

Where `loops` is 1 these are the numbers they always were, so adopting them costs
nothing on a small world. Where it is not, they are what a reader means. The
report prints them, and shows its working:

```text
  testapp_order  1 read, 1 without an index
       filtering ((reference)::text < %s::text)
       most one read discarded: 1,124,097 rows, keeping 75,903
       across 3 loops (parallel workers); PostgreSQL states 374,699 discarded per loop
```

**They are reconstructions, and the error is bounded by half a loop.** PostgreSQL
divides by the loop count and rounds before printing, so multiplying back can be
out by up to `loops / 2` -- the totals above are each one row off the truth. That
is stated rather than hidden, because the alternative is a number the server does
not print at all.

**And they are not a budget currency.** The first instinct on meeting these is to
write `assert node.total_actual_rows < 50_000`, precisely because this is the
number that finally exposes fan-out -- and it is the wrong assertion. It moves
with the plan the server chose on the day, which moves with the statistics, the
row count and how many workers were free. A consumer tried it and recorded three
consecutive pairs on unchanged code: 46,768 then 542,613; 84,731 then 416,086;
2,462 then 76,475.

A row count is evidence about a plan, not a threshold to hold a build against.
Assert on the **shape** -- that a relation was not read without an index, that
nothing was planner-blind, that the statement count did not grow with the data --
and read the totals when one of those fires. It is the same rule durations get,
and for the same reason: a performance assertion that mentions milliseconds is a
flaky test with extra steps, and one that mentions a row count is the same test
with a more convincing number in it.

### There is no total for the estimate, on purpose

The measurements are divided by the loop count. The estimate is not, and the two
multiplications are different ones:

- Under a `Gather`, the planner divided its estimate by the number of workers
  plus the fraction of a worker it credits the leader with -- 2.4 for two workers,
  against a loop count of 3. Measured on the pair above: 400,000 estimated
  serially against 166,667 on the parallel node, and 400,000 / 166,667 is exactly
  2.4. That divisor is not in the output, so no arithmetic over the node recovers
  it.
- Under a nested loop, `loops` is the number of outer rows that *arrived*, which
  is a measurement. Multiplying a per-loop estimate by it gives a number nobody
  predicted: measured on an inner node estimating 60 rows over 1,260 loops, the
  product is 75,600, which is exactly what the join produced -- while the
  planner's own estimate for that join was 400,020.

A `total_estimated_rows` would therefore be wrong under a `Gather`, and would
agree with the measurement under a nested loop. The second is worse: it would
read as perfect agreement on the plan the planner got most wrong.

**One consequence is visible in the report.** `estimate_error` on a parallel-aware
node divides an estimate scaled by 2.4 by a measurement scaled by 3, so it reads
about 25% high even where the planner was right -- on the pair above, 6.6x against
a real error of 5.3x. There is no honest repair, so the block says so under the
node it applies to.

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

#### Reproducing it needs the right query shape and enough parents

The example above joins **through the parent**, and the wording matters. Filter
the child's foreign key column directly and PostgreSQL consults that column's
most-common-values list, which is a different mechanism with a different answer.
Both are measured below, on a Zipf fan-out where parent *k* holds roughly 1/*k*
of the rows:

| Distinct parents | MCV entries | What the estimates do |
| --- | --- | --- |
| 50 | 50 | every parent priced individually, and right to within 10% |
| 5,000 | 100 | the hundred commonest priced individually; every other parent shares one number |

At 50 parents the list covers all of them, so the head *and* the tail are priced
separately and no two executions share an estimate -- the finding is not merely
hard to reproduce, it is **unreachable**, and correctly so, because the planner
was not blind. At 5,000 it holds 100 entries, which is `default_statistics_target`,
and every parent outside it is estimated at **402** rows against measured answers
of 4,000, 800 and 80. That is one estimate and more than one truth: the finding.

So two things decide whether a direct filter can produce this:

- **the tail is where it lives.** The head of a skewed fan-out is in the MCV list
  and is priced roughly right, which is the opposite of where a reader looks
  first;
- **there has to be a tail at all**, which means more distinct parents than the
  statistics target -- 100 by default, and per-column through
  `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS`.

Joining through the parent sidesteps both. The join condition is a column
comparison, no MCV list applies to it, and every value of the join key gets the
same average -- so head and tail both qualify at any parent count. That is why
the measured example above is written that way, and it is worth copying.

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

Index advice was declined for the same reason and is a longer story, told
[below](#index-advice-and-why-there-is-none).

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

**Take 1.7x as a floor, not a budget.** It is one measurement on one shaped
world, and the multiplier is worst on exactly the statements you most want a
plan for: instrumenting a plan whose nodes loop millions of times costs far more
than instrumenting a plan that scans once. A consumer measured a 15-second
endpoint go past a 120-second `statement_timeout` under `analyze=True`.

So **plan capture needs timeout headroom**. A cancelled `EXPLAIN` is caught and
refused like any other failure -- there is a test that cancels one with a
`statement_timeout` and asserts the connection survives -- but the plan is lost,
and losing it on the slowest statement in the suite is losing the one that
mattered. Raise `statement_timeout` for the tests that capture plans, or capture
them with `analyze=False`.

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

**It does not break your transaction.** A failing `EXPLAIN` inside a transaction
would leave the connection in "current transaction is aborted, commands ignored
until end of transaction block", and every later statement in the test would
fail. So the `EXPLAIN` runs under a savepoint, and a statement PostgreSQL
declines to explain costs a plan rather than the test. Both halves are tested
against a real server: one that the savepoint holds, and one that removing it
poisons the transaction.

"Inside a transaction" is asked of the connection rather than of Django. Django
answers two different questions -- `in_atomic_block` is *did I open one*, and
`get_autocommit()` is *is this connection in one at all* -- and they disagree
under manual transaction management, where `set_autocommit(False)` puts the
driver in a transaction with `in_atomic_block` still `False`. Reading only the
first left that case unguarded, which is how a consumer lost two suite runs to a
cascade of `InFailedSqlTransaction`.

The refusal names the exception class and never its message, because a driver
error can quote a bound value and this package
[retains no parameters](reference.md).

## Index advice, and why there is none

"These twelve statements sequentially scanned a two-million-row table, here are
the `CREATE INDEX` statements" is the output people actually want, and this was
the milestone that was going to produce it. It does not, and the reason is the
rule that decides every other question here: **a finding is a fact the server
states, or an equality over measurements, never a number somebody picked.**

Three routes to an assertable version were tried against a real server. All
three ended in a threshold.

**A sequential scan on a table another captured statement reaches by index.**
This one is the near miss, because it reads like a comparison between two
measurements rather than a cut-off. It is not: two statements filtering
*different columns* of one table are not measuring the same thing. Measured --
one statement reached `testapp_order` through the foreign key index while
another read it end to end for a predicate that kept **every** row, which is the
plan PostgreSQL should have chosen and the one no index improves. Both halves of
the rule hold and the conclusion is still wrong, because the index it would
point at is on the other statement's column. There is a test that runs exactly
that pair against a server.

**A filter whose discarded rows PostgreSQL counted itself.** `Rows Removed by
Filter` is the server's number, not ours, which is what made it a candidate. The
verdict is still nobody's: a five-row table discards four rows in the same shape
a hundred-thousand-row table discards 99,999 -- same node type, same key, same
everything a rule could read -- and only a magnitude separates them. The count
does not even rank the candidates, because the read that discarded *nothing* is
the whole-table read that was right to be a scan. There is a test that puts both
tables in one capture.

**Emitting the `CREATE INDEX` itself.** That needs a column, and the only place
a column can be got is PostgreSQL's rendered predicate -- an expression that
would have to be parsed, in a package that
[declines a SQL parser](reference.md#django_query_contract.normalise_sql) on
evidence, and whose text carries the bound value this package retains nowhere.

### What is here instead

Every fact the decision needs, and no decision. `group_by_relation` reads a
capture back as the tables it touched, and `format_relation_access` prints them:

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

The table, how PostgreSQL reached it, the predicate it applied, how many rows it
said it threw away, the line that asked, and the indexes that already exist --
in the server's own words, from `pg_get_indexdef`, so an expression index, a
partial index and a non-default operator class all come out right without this
package learning any of the three. Put the filter next to the index list and the
gap is visible. The judgement is yours.

It is a **grouping**, in the sense
[call-site attribution](attribution.md) is one, and not a detector. Nothing here
is a finding, nothing fails on it, and there is no rule anywhere in it about
which read is the interesting one -- which is exactly what makes it safe to put
a sequential read of a table beside an indexed read of the same table, where a
finding would not be.

The relations are ordered by how many times they were read, and **deliberately
not by rows discarded** -- which is the order a reader would find most useful,
and is exactly why it is refused. Ranking tables by how badly they want an index
is the judgement being declined, and a sort key is a quiet way of making it
anyway.

### A filter carries a value, and this package retains none

`EXPLAIN` renders a predicate with the parameter substituted. A real server
writes this for a query bound with `%s`:

```text
Filter: ((reference)::text = '601980.6826913885'::text)
```

That is a customer's data, on a record this package would otherwise hold for the
length of a capture and print into CI output. So `PlanNode.condition` is put
through the same [`normalise_sql`](reference.md#django_query_contract.normalise_sql)
rules the statement fingerprint is made with: the column, the operator and the
casts survive, and the value becomes `%s`.

That redaction is also what makes the predicate groupable. With the value in it,
one statement shape run with twelve parameters is twelve conditions and no
report could say the twelve executions did the same thing. Without it, they are
one.

### An index two levels down is still an index

PostgreSQL splits a bitmap read across nodes: the `Bitmap Heap Scan` names the
table and carries no index at all, while the `Bitmap Index Scan` beneath it
names the index and no table. Put a `BitmapAnd` between them -- two indexes
combined -- and the index is two levels down.

`PlanNode.indexes_used` walks down to find them, stopping at the next node that
names a relation, because that node is a different read of a different table.
Reading the node alone would report a table PostgreSQL reached through two
indexes as one it read end to end, which is the single worst thing this report
could say. Both shapes are pinned by a real server's payload.
