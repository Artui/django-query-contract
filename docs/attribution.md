# Call-site attribution

## The question

Not *what is wrong* -- that is what a finding answers -- but **where did these
statements come from**. Every captured statement has an answer, and until this
page's API existed a capture would only ever tell you about the repeated ones,
because a call site was rendered only where a finding rendered.

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

Two shapes of the same answer:

- [`QueryRecord.call_site`][django_query_contract.QueryRecord] -- the line that
  emitted **one** statement. It has been on every record since the first
  release.
- [`group_by_call_site`][django_query_contract.group_by_call_site] -- the same
  question asked of a whole capture, which is where "these forty statements came
  from these three lines" comes from.

## The call site is the innermost frame outside Django

That is the entire rule, and there is nothing to configure.

Django is the only package skipped. Anything else in the stack -- a REST
framework, a factory library, your own service layer -- did emit the query, and
deciding that some libraries are more interesting than others is exactly the
kind of tuning this package is built without.

When the stack reaches no frame outside Django, the answer is `None`. It is
reported rather than approximated with the innermost frame available, because
"the query came from `django/db/models/query.py`" is true of every query ever
executed and tells a reader nothing.

Two things can produce that `None`:

- the capture kept no stack at all, which is every record in one rebuilt by
  [`QueryCapture.from_capture_context`][django_query_contract.QueryCapture];
- the window was too small to reach out of the ORM. See
  [where the window stops](n-plus-one.md#where-the-window-stops).

## Attribution is not identity

**This is the one thing on the page worth being careful about.**

Grouping by call site merges call paths that
[`find_n_plus_one`][django_query_contract.find_n_plus_one] deliberately keeps
apart. Take the helper from the [N+1 page](n-plus-one.md#the-identity-is-the-whole-stack-not-the-call-site):

```python
def get_books(author):
    return list(author.books.all())  # the call site of every one of them


def author_list(request):
    return [get_books(a) for a in Author.objects.all()]


def author_feed(request):
    return [get_books(a) for a in Author.objects.filter(active=True)]
```

- As **findings**, that is two: two call stacks, two defects, two fixes. The
  identity is the whole stack precisely so that a report never points at the
  helper's line, which is the one line that is fine.
- As **attribution**, it is one: six statements from `get_books`. That is where
  they were emitted, and both call paths really did emit them there.

Both are true at once, and the difference is the question. Attribution may merge
because it claims nothing about defects: a group of forty is not a finding of
forty, it is forty statements and an address. Nothing here fails a test and
nothing here says a loop was found.

**So the frame rule is a display rule, and it stays one.** A rule about which
frames matter is a judgement, a judgement is a knob, and a knob in a detector's
*identity* is how four earlier N+1 detectors came to cry wolf and get deleted.
Keeping that rule out of the identity is what the whole-stack key is for; it
does no harm in a rendering, where a reader can see the line and disagree with
it.

## What a group holds

An [`Attribution`][django_query_contract.Attribution] is a call site and every
statement that entered the database from it.

| | |
| --- | --- |
| `call_site` | The line, or `None` when there was none to name. |
| `records` | Every statement from it, in capture order. |
| `count` | How many. |
| `fingerprints` | The distinct statement shapes it emitted, first seen first. |
| `aliases` | The connections it ran on, in the order first seen. |
| `first_index` | Where its first statement was in the capture. |

`fingerprints` can hold more than one, and that is the other half of what makes
an attribution not a finding: a finding is one statement shape by definition,
while a line that evaluates a queryset carrying a related object emits several.

**Every record lands in exactly one group**, including the ones with no call
site. A grouping that dropped what it could not place would be the silently
incomplete measurement this package exists to complain about -- and it would be
silent about exactly the statements a reader has no other way to see.

Groups are ordered busiest first, then by where each line's first statement
appeared, so the order is total and two runs over one capture never reshuffle.
The unaddressed group is ordered on its size like any other: there is no rule
here about which group is interesting, and in a capture rebuilt from a
`CaptureQueriesContext` it is genuinely the headline.

## Where it shows up

Under a failing count assertion, beneath the N+1 section, for the statements no
finding accounted for:

```text
------------------------------ django-query-contract ------------------------------
6 statements captured: 6 on 'default'.

N+1 -- one statement shape, executed more than once from one call path:
  3 x  from shop/views.py:31 in author_list
       SELECT "shop_book"."id", "shop_book"."author_id" FROM "shop_book" WHERE ...
       queries #1, #2, #3
  3 statement(s) were not repeated from any one call path. They came from:
  1 x  from shop/views.py:30 in author_list
       SELECT "shop_author"."id", "shop_author"."name" FROM "shop_author"
  1 x  from shop/serializers.py:88 in to_representation
       SELECT "shop_book"."id", "shop_book"."author_id" FROM "shop_book"
  1 x  from shop/middleware.py:12 in __call__
       SELECT "django_session"."session_key" FROM "django_session" WHERE ...
```

The statements a finding already accounts for are not attributed a second time:
the finding named their call site three lines higher up, and the counts in this
section add up to the number of statements captured.

The same section is what a growth failure prints under its curve, so a block
that grew for no reason a loop explains still names the lines it grew on.

[`format_attributions`][django_query_contract.format_attributions] renders the
blocks and nothing else -- no heading -- because the caller is what knows why it
is printing them.

## There is no `--call-sites` flag, and the reason is memory

`--n-plus-one` gathers findings across a run and prints them at the end. The
matching listing for attribution would have to hold the statements themselves,
because a call site's group *is* its records -- and that is the retention bug
this package already fixed once. A capture left in `item.stash` was held for the
whole session: about 50 KiB per test, 64 MiB across twelve hundred tests. A
package that asks to be left on session-wide can only honestly do that if it
does not accumulate.

A run-wide profile of query counts per line is a real thing to want, and it
belongs to the reporting face, which can aggregate to counts and drop the
records. Until then, attribution is per capture.

## Prior art: `django-sqlcommenter` answers this from the other end

[`django-sqlcommenter`](https://pypi.org/project/django-sqlcommenter/) (0.1.0,
August 2026) attributes queries too, and does it by **annotating the SQL**: a
`callsite='shop/services/pricing.py:118'` tag, alongside the route and the
controller, spliced into the statement by a per-connection `execute_wrapper`.

It is the same idea delivered to a different reader, and the difference is not a
disagreement:

- **Its reader is the database.** The tag exists so that `pg_stat_activity`, the
  slow-query log and pgBadger show the code that issued the statement they are
  complaining about. That is a production question, asked by whoever has the
  database open.
- **This package's reader is a test.** There is no slow-query log to read at
  test time, and the answer has to arrive as a Python object, because something
  is going to assert on it or render it under a failure.
- **It changes the statement; this does not.** A comment is text inside the SQL,
  which is the only way to get an answer out to a tool that only ever sees SQL,
  and exactly what a fingerprint should not have to see.
- **It answers for one statement at a time.** A comment travels with its own
  query, so "these forty statements came from these three lines" is not a
  question that shape can be asked.

They do not overlap, and running both is reasonable: one tells your DBA which
view is hammering the database, the other tells your test suite which line to
edit.

## Reading it yourself

```python
from django_query_contract import QueryCapture, format_attributions, group_by_call_site

with QueryCapture(using="default") as capture:
    view(request)

attributions = group_by_call_site(capture)
print(attributions[0].count, attributions[0].call_site, attributions[0].fingerprints)
print(format_attributions(attributions, max_sites=10))
```

`group_by_call_site` takes any iterable of records, so it reads a capture, a
slice of one, or the records of a single connection.
