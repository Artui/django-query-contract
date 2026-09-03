# The growth assertion

## The claim, and why a fixed count cannot make it

A query count asserted against three fixture rows is asserted against a defect
that costs one query per row, because at three rows a prefetch and a loop cost
almost the same. `django_assert_num_queries(3)` passes either way, and it goes
on passing in production at fifty thousand rows.

**A growth assertion runs the same block against worlds of two sizes and asks
whether the count moved.** That is the only question that separates the two, and
no Python package asks it. Ruby has had it since `n_plus_one_control`, which
runs the code at several scale factors and asserts the count is `O(1)`.

```python
from django_query_contract import assert_query_growth


def test_the_author_listing_does_not_grow(world):
    assert_query_growth(world, lambda: render_author_list())
```

A hundred rows, then a thousand, and the two statement counts have to be equal.

## What a world is

Anything callable as `world(factor)` that returns a context manager:

```python
import contextlib

import pytest

from myapp.models import Author


@pytest.fixture
def world(db):
    @contextlib.contextmanager
    def at(factor):
        Author.objects.bulk_create([Author(name=f"a{i}") for i in range(100 * factor)])
        yield Author.objects.count()
        Author.objects.all().delete()

    return at
```

That is the whole seam. It is a **shape**, not a dependency: this package
requires nothing to be installed for a project to supply one, because a growth
assertion needs *scale* -- a hundred rows against a thousand, on any backend --
and not *size*, which is the two-million-row database a query **plan** assertion
needs and a different problem with a different cost.

[`django-data-shape`](https://pypi.org/project/django-data-shape/) implements
the same shape from a declaration, and its
`django_data_shape.fixtures.scale_fixture` yields one directly:

```python
from django_data_shape import Constant, Shape, Table
from django_data_shape.fixtures import scale_fixture

world = scale_fixture(Shape(Table(Author, rows=100, name=Constant("a"))))
```

The number the context manager yields is how many rows the world holds. It is a
diagnostic printed beside each count, not the curve's x-axis -- the caller
passed the factor in and already knows it -- so a world that simply `yield`s is
accepted and its size is reported as unknown.

## The mistake this makes unavailable

!!! danger "Never open a query capture around the call that builds the world"

    Building a world runs statements of its own. Where the backend has `COPY`
    they are invisible to Django's `execute_wrapper` and the count is flat; on
    every other backend the loader's inserts are ordinary statements, **so the
    captured count grows with the factor**.

    Measured against `django-data-shape` and reported by its own author: a
    two-table world captured from outside runs **8 statements at factor 1 and 17
    at factor 10** on SQLite, flat at 9 on PostgreSQL. A harness reading that
    curve reports a confident `O(N)` for a block that is `O(1)` -- **the harness
    reading its own loader's curve as its subject's.**

`assert_query_growth` and `measure_query_growth` own the capture, and open it
*inside* the world, after the build:

```python
with world(factor) as rows:
    with QueryCapture(...) as capture:  # inside, always
        block()
```

You hand over a world and a block and never write `QueryCapture` at all, so
there is nowhere to put it in the wrong place. There is deliberately no
parameter for passing a capture in, and every report says out loud what its
numbers are of:

```text
Every count above is of the block alone: each capture was opened inside world(factor),
after that world had been built, so the statements that built it are not in these numbers.
```

That line is printed on a passing curve as well as a failing one, because the
reader who most needs it is the one who has just seen a count grow and does not
know whose statements they are looking at.

## Two claims, both exact

| Claim | Rule | Reads as |
| --- | --- | --- |
| `Growth.CONSTANT` | the count is **equal** at every factor | `O(1)`. The default, and the common case |
| `Growth.LINEAR` | the count per unit of data never **increases** | `O(N)`. Legitimate bulk work |

```python
from django_query_contract import Growth, assert_query_growth


def test_the_import_is_batched_not_per_row(world):
    assert_query_growth(world, run_import, growth=Growth.LINEAR)
```

Both are **upper bounds**. `LINEAR` is satisfied by a block that turns out to be
constant, because growing less than allowed is never the defect; only growing
faster than the claim is. `LINEAR` still refuses a nested loop, which is what
keeps it from being a way of turning the assertion off.

### Why counts are compared and no curve is fitted

A fitted curve would use every measurement and produce a slope and a goodness of
fit -- and then need three thresholds to turn those into a verdict: how near
zero counts as flat, how linear counts as linear, and how good a fit has to be
before the answer is believed. Each is a knob, each is wrong for somebody, and a
growth assertion that fails once a fortnight for reasons nobody can reproduce
gets deleted, taking the idea with it.

Comparing counts is integer arithmetic on integers that were **counted rather
than estimated**. `CONSTANT` is equality. `LINEAR` is one cross-multiplication,
`larger.count * smaller.factor <= smaller.count * larger.factor`, which is
`count / factor` not increasing without ever leaving the integers. An affine
count `a + b*N` always satisfies it, a quadratic one never does, and the number
the rule allowed is the number the failure prints.

It is cruder than a fit. Crude is the correct trade for an assertion whose only
job is to be believed.

## The factors

`(1, 10)` by default. Two points, because both rules are exact comparisons over
a **pair** and both are transitive, so a third point tells them nothing a second
one did not -- with more factors the assertion checks consecutive pairs, and
the first pair that broke is the one the failure names.

Tenfold, because it is the smallest spread no batching can hide: a per-row
statement over ten times the rows lands nine times the base count away from
constant, while merely doubling can fall inside a single `bulk_create` batch and
produce the same count twice.

Factor 1 is the world the declaration describes, so the declaration should be
**the smallest world that still means something**. A hundred rows against a
thousand is the regime this is for, and it is milliseconds per factor.

Factors must be at least two, strictly ascending, and at least 1. They are
refused rather than sorted, because the order given is the order that runs and
the first run is the one that pays for whatever a per-process cache populates.

## Reading the failure

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
  1 statement(s) were not repeated from any one call path.
```

**Both counts are named**, because "the count grew" is the same sentence for a
hundredfold N+1 and for one extra statement from a cache that filled on the
first run. Under them is the rule that broke, stated in the numbers that broke
it -- and for a linear failure, the count that *would* have held: "against 5
statements at factor 1, that allows 50 at factor 10; 401 ran."

Under that is the capture from the failing world, rendered by the same
[`format_capture_report`](reference.md) that appears beneath a failed
`django_assert_num_queries`. So the N+1 that explains the growth is described
exactly as it is described everywhere else in this package, and the reader gets
the line to edit rather than only the arithmetic.

## The one way this can still be flaky

A block whose **first run populates a per-process cache** -- a content-type
lookup, a memoised settings read -- emits one statement more at whichever factor
ran first. The same test then passes in a suite where an earlier test happened
to fill that cache and fails when run alone.

That is what `warm_up` is for, and the usual value for it is the block itself:

```python
def test_the_dashboard_does_not_grow(world):
    def render():
        dashboard()

    assert_query_growth(world, render, warm_up=render)
```

It runs once inside the first world, before the first capture opens, so what it
costs lands in no measurement.

## It is still not a count assertion

`django_assert_num_queries` is the count assertion, and this package
[ships no second one](https://github.com/Artui/django-query-contract#it-ships-no-count-assertion-on-purpose).
There is no way to spell a fixed number here: the claim is about how a count
*changes*, which is exactly why fewer than two factors is an error rather than a
measurement of one world.

The two compose. Assert the count with theirs and the shape of it with this:

```python
def test_the_listing(world, django_assert_num_queries):
    with django_assert_num_queries(2):
        render_author_list()
    assert_query_growth(world, lambda: render_author_list())
```

## Measuring without asserting

`measure_query_growth` is the same run with no claim in it, for a report that
plots a curve rather than failing a build:

```python
from django_query_contract import Growth, format_query_growth, measure_query_growth

measured = measure_query_growth(world, lambda: render_author_list())
print(measured.factors, measured.counts)
print(measured.holds(Growth.LINEAR))

# The same paragraph a failed assertion would have printed. The claim is an
# argument because a curve on its own is not a verdict: the same measurement
# reads as a pass against LINEAR and a failure against CONSTANT, so a renderer
# with no claim in it would have to invent one.
print(format_query_growth(measured, Growth.CONSTANT))
```

One measurement can be judged against more than one claim, which is occasionally
what you want: a block that fails `CONSTANT` and holds `LINEAR` is bulk work,
and one that fails both is a defect.

Each `GrowthPoint` keeps the whole capture, so a curve is also a set of
diagnoses -- and it keeps the
[ceiling](https://github.com/Artui/django-query-contract#the-ceiling-nobody-mentions)
with it, which matters more here than anywhere else: a per-row statement over a
thousand rows at a factor or two more is thousands of statements in one block,
and that is precisely where a count taken from Django's own query log stops
being true.
