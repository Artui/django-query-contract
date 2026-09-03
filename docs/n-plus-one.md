# N+1 by fingerprint

## The definition, and why there is nothing to tune

**More than one execution with the same normalised SQL and the same call stack
is an N+1.** The same line of code ran the same statement again, with different
data, instead of asking for the data once.

That is the whole rule. There is no threshold, no confidence score, no list of
patterns and no rule about lazy loads, so there is nothing to configure and
nothing to be wrong about.

The reason it is written that way is on PyPI. Four Python N+1 detectors are
dead: `nplusone` (last released 2018, 1068 stars, and still what most blog posts
recommend), `django-query-capture` (2022), `django-nplusone` (2020) and
`django-explain` (2016). The most probable reason is that they classified by
rule. `nplusone` detects by listening for lazy loads, which flags legitimate
code and misses real N+1s hidden behind an explicit loop, so it cried wolf and
was removed. **A detector nobody disables is a different package from a detector
that finds more.**

## What one finding is

An [`NPlusOne`][django_query_contract.NPlusOne] is a fingerprint, a call stack,
and every execution that shared both.

```python
from django_query_contract import QueryCapture, find_n_plus_one

with QueryCapture() as capture:
    render_author_list()

for finding in find_n_plus_one(capture):
    print(finding.count, finding.call_site)
```

### The identity is the whole stack, not the call site

Two weaker keys were considered. Both are rules about which frames matter, and a
rule about which frames matter is the kind of judgement that turns into a knob.

**The fingerprint alone** merges a loop in a view with a loop in a template that
happen to emit the same SQL, and reports one finding whose call site is
whichever of the two ran first.

**The innermost frame outside Django alone** merges two callers of one helper:

```python
def get_books(author):
    return list(author.books.all())  # both findings name this line


def author_list(request):
    return [get_books(a) for a in Author.objects.all()]


def author_feed(request):
    return [get_books(a) for a in Author.objects.filter(active=True)]
```

Those are two defects with two fixes. Grouping on the call site reports one
finding of six, pointing at the one line that is fine.

The whole stack cannot make either mistake, because two executions with
identical stacks really did run the identical code path. It also cannot split a
loop: every iteration enters the query through the same frames at the same
lines.

**The one shape it does split is recursion.** The same line reached at two
depths is two stacks, so it is two findings. Both are true and both name the
line to edit; a longer report is the price of never pointing a reader at a line
that is fine.

### The connection is not part of it

A loop that queries two databases from one line is one loop with one fix, so it
stays one finding, and `aliases` reports the span. Putting the alias in the
identity would split one loop into two findings, which is the failure mode the
whole-stack key exists to avoid.

### A statement with no call stack is not considered at all

[`QueryCapture.from_capture_context`][django_query_contract.QueryCapture]
rebuilds a capture from the `CaptureQueriesContext` that
`django_assert_num_queries` yields, and that object records `{"sql", "time"}`
per query and nothing else. Those records carry no frames.

Bucketing them together would say "these ran from one place" on the strength of
knowing nothing about where any of them ran -- a false positive manufactured out
of a gap in the input, on exactly the repetition a reader is most likely to be
staring at. They are skipped, and the report says how many were skipped rather
than issuing a clean bill of health it did not earn.

### Where the window stops

The capture keeps the innermost `stack_depth` frames, so the identity is really
that window rather than the literal whole stack.

Measured: a query issued from a test function under pytest is 38 frames deep,
and 30 of those are pytest's and pluggy's own preamble, identical for every test
in the session. At the default depth of 25 the window reaches past the test
function, and the frames it drops could not tell two call paths apart anyway.

An application whose own stack is deeper than the window can put two paths in
one bucket. The error that makes is a **merge** -- two findings reported as one,
with a count that spans both -- never a repetition that did not happen.

**To find out whether a finding is one, raise `stack_depth` and run it again.** A
merge is the thing that stops being one when the window widens: twelve identical
frames of recursion between two callers and a query produce one finding of four
at a depth that reaches only the recursion, and two findings of two at a depth
that reaches past it. The knob is `stack_depth` on the capture, or the
`query_contract_stack_depth` ini for the plugin.

**`stack_truncated` cannot answer it**, and this page said it could until 0.7.0.
Under a test runner it is `True` on every capture at every depth a suite would
use, because the frames beyond the window are pytest's own -- so it is a constant,
and a constant distinguishes nothing. It says the window was full, not that the
frames outside it were the ones that mattered.

## Legitimate repetition is a finding

A `bulk_create` batched into a hundred inserts is one statement shape executed a
hundred times from one line. Structurally that is the defect exactly; only the
intention differs, and the intention is not in the capture.

So it is reported like any other repetition, and **nothing fails because of it.**
That is the answer to crying wolf, rather than an exemption list:

- This package ships **no assertion**. `django_assert_num_queries` is the
  assertion, and it fails on the count the author declared.
- A finding appears **underneath a failure somebody else's assertion already
  produced**, where the author is already reading.
- Or it appears in a **listing somebody asked for**, with `--n-plus-one`.

An allowlist would be the first tunable, and the first tunable is a detector's
first step towards being wrong.

## How it is reported

### Under a failing count assertion

Nothing to add to a test. Keep writing the assertion:

```python
def test_listing_is_flat(django_assert_num_queries, authors):
    with django_assert_num_queries(2):
        render_author_list()
```

When it fails, the failure gains a section. The call site is on the first line
of each finding, because it is the only part anybody acts on:

```
------------------------------ django-query-contract ------------------------------
13 statements captured: 13 on 'default'.

N+1 -- one statement shape, executed more than once from one call path:
  11 x  from shop/views.py:16 in render_author_list
       SELECT "shop_book"."id", "shop_book"."author_id" FROM "shop_book" WHERE ...
       queries #1, #2, #3, #4, #5, #6, #7, #8, ...
  2 statement(s) were not repeated from any one call path. They came from:
  1 x  from shop/views.py:15 in render_author_list
       SELECT "shop_author"."id", "shop_author"."name" FROM "shop_author"
  1 x  from shop/middleware.py:12 in __call__
       SELECT "django_session"."session_key" FROM "django_session" WHERE ...
```

The counts add up to the number of statements captured, on purpose. A report
that lists the interesting queries and stays quiet about the rest invites a
reader to assume the rest were fine.

The statements no finding accounts for are attributed to the lines that ran
them, so every statement in the section has an address whether it repeated or
not. That grouping merges call paths a finding keeps apart, deliberately and
only because it claims nothing about defects -- see
[call-site attribution](attribution.md#attribution-is-not-identity).

When nothing repeated, it says so -- which under a failed count assertion is
worth knowing, because it means the fix is not a prefetch.

### The whole run, on request

```bash
pytest --n-plus-one
```

prints every finding in the run, worst first, at the end:

```
=============================== django-query-contract ===============================
2 N+1 finding(s), most repeated first:
  40 x  from shop/views.py:16 in render_author_list
       in tests/test_views.py::test_author_listing
       SELECT "shop_book"."id", "shop_book"."author_id" FROM "shop_book" WHERE ...
       queries #3, #4, #5, #6, #7, #8, #9, #10, ...
```

It changes no outcome: a run with the flag exits exactly as it would without it.

Findings are **not merged across tests**. One call site reached from two tests is
two findings here, because a finding's identity is its whole call stack and two
tests are two stacks. Merging them would need a second grouping rule -- "these
are the same one really" -- which is the judgement this package is built
without. The listing orders instead.

## Reading findings yourself

[`find_n_plus_one`][django_query_contract.find_n_plus_one] takes any iterable of
records, so it reads a capture, a slice of one, or the records of a single
connection:

```python
from django_query_contract import QueryCapture, find_n_plus_one

with QueryCapture(using="default") as capture:
    view(request)

worst = find_n_plus_one(capture)[0]
print(worst.count, worst.call_site, worst.fingerprint)
```

[`format_n_plus_one`][django_query_contract.format_n_plus_one] renders one
finding and
[`format_n_plus_one_summary`][django_query_contract.format_n_plus_one_summary]
renders many, keyed by whatever names the block they came from. Both reports in
this package go through those two functions, so a finding cannot be described
one way in a failure and another way in a listing.
