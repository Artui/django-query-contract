# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-09-02

### Added
- Call-site attribution as a public surface. `group_by_call_site` reads a
  capture back as the lines its statements came from -- "these forty statements
  came from these three lines" -- and `Attribution` is one such line with every
  statement that entered the database from it: its `count`, the distinct
  statement shapes it emitted, and the connections it ran on. The per-statement
  half of the same question, `QueryRecord.call_site`, has been there since the
  first release; what was missing was the ability to ask it of a whole capture.
- **A finding needs a repetition, so until now a capture named a call site only
  where an N+1 rendered one.** The section under a failed query-count assertion
  now attributes the statements no finding accounted for, which is exactly the
  case that section exists for: a count assertion that failed with no N+1 in the
  capture at all used to print a number of unexplained statements and not one
  line of code to go and look at. A growth failure renders the same section
  under its curve, so it gained the same lines.
- **Grouping by call site merges call paths that `find_n_plus_one` deliberately
  keeps apart, and that is the one thing here worth being careful about.** Two
  callers of one `get_books()` helper are two findings, because the identity of
  a defect is the whole call stack and the helper's own line is the one line
  that is fine. They are one attribution, because that line is genuinely where
  the statements were emitted. Both are true, and the merge is allowed only
  because an attribution claims nothing about defects: a group of forty is not a
  finding of forty, it is forty statements and an address. So the frame rule
  stays on the display side and out of every identity -- a rule about which
  frames matter is a knob, and a knob in a detector's identity is how the four
  dead ones came to cry wolf. One test runs a single capture through both
  readings and pins that they disagree.
- Every record lands in exactly one group, including the ones with no call site.
  A capture with no stacks, or a window too small to reach out of the ORM, gets
  the group whose `call_site` is `None` rather than being dropped, so the
  statements in a capture and the statements in its attribution always add up. A
  grouping that quietly lost what it could not place would be the silently
  incomplete measurement this package exists to complain about, and it would be
  silent about the statements a reader has no other way to see.
- `format_attributions`, which renders the blocks and no heading, because the
  caller is what knows why it is printing them; and `max_call_sites` on
  `format_capture_report`.
- `docs/attribution.md`, carrying the positioning against `django-sqlcommenter`
  -- the same question answered from the other end, by annotating the SQL so a
  `callsite=` tag reaches `pg_stat_activity` and the slow-query log. That is a
  production reader: at test time there is no database log to read, the answer
  has to arrive as a Python object, and a comment travels with one statement, so
  "these forty came from these three lines" is not a question that shape can be
  asked. The two do not overlap.
- The growth assertion. `assert_query_growth` runs one block against worlds of
  several sizes and asserts the query count kept its shape -- `O(1)` by
  default, and `Growth.LINEAR` for genuine bulk work. It is the claim a fixed
  count cannot make: a listing asserted at three queries against three fixture
  rows is asserted at three queries against a defect that costs one query per
  row, because at three rows a prefetch and a loop cost almost the same. Ruby
  has had this since `n_plus_one_control`; no Python package does it.
- `measure_query_growth`, the same run with no claim in it, so a CI report can
  plot a curve without failing anything; `QueryGrowth` and `GrowthPoint`, the
  measurement; `Growth`, the two claims; and `format_query_growth`, which
  renders a curve whether it held or not.
- **The capture is opened inside the world, never around it, and the API is what
  enforces that.** A world's own loader emits statements, and off PostgreSQL
  they are ordinary inserts, so a capture wrapped around the build sees a count
  that grows with the factor -- measured on a two-table world, 8 statements at
  factor 1 rising to 17 at factor 10 on SQLite, flat at 9 on PostgreSQL where
  `COPY` bypasses Django's cursor wrapper. A harness reading that curve reports
  a confident `O(N)` for an `O(1)` block. A caller hands over a world and a
  block and never writes `QueryCapture`, so there is nowhere to put it in the
  wrong place, and every rendering states in its own text what its numbers are
  counts of.
- Both claims are **exact integer comparisons**, not a fitted curve. `CONSTANT`
  is equality; `LINEAR` is one cross-multiplication that holds for any affine
  count and fails for any super-linear one. A fit would need a tolerance, a
  goodness-of-fit floor and a rule for what counts as linear -- three knobs
  where this has none -- and a growth assertion that is itself flaky is worse
  than no growth assertion, because it gets deleted and takes the idea with it.
- The world is a **shape rather than a dependency**: anything callable as
  `world(factor)` returning a context manager, so a five-line
  `@contextmanager` in a project's own `conftest.py` works exactly as well as
  `django_data_shape.fixtures.scale_fixture`. Growth needs *scale* -- a hundred
  rows against a thousand, on any backend -- and not the size a query plan
  needs. A world that yields no row count is accepted and its size reported as
  unknown.
- A growth failure names the count at every factor, the rule that broke stated
  in the numbers that broke it, and the capture from the failing world rendered
  by the same `format_capture_report` that appears under a failed
  `django_assert_num_queries` -- so the reader gets the line to edit and not
  only the arithmetic.
- `warm_up`, which runs once inside the first world before the first capture
  opens. The one remaining way a growth assertion can be flaky is a block whose
  first run fills a per-process cache, which moves one statement onto whichever
  factor ran first.
- `docs/growth.md`.

### Changed
- `relative_to_cwd` and `shorten` moved into `utils.py` from
  `format_n_plus_one`, so the two renderings of a call site cannot spell one
  path, or one `max_sql`, two different ways. Both are internal.
- There is deliberately **no run-wide listing of call sites** to match
  `--n-plus-one`, and the reason is memory. A call site's group *is* its
  records, so gathering them across a session would re-create the retention bug
  0.2.0 fixed: 64 MiB across twelve hundred tests. A run-wide profile of query
  counts per line belongs to the reporting face, which can aggregate to counts
  and drop the records.
- Fewer than two scale factors, a repeated factor and a descending list are all
  refused with a stated reason. One factor is refused because it would make this
  a count assertion, and `django_assert_num_queries` is the count assertion --
  this package still ships no second one, and there is deliberately no way to
  spell a fixed count in the growth API.
- The default call-stack depth is one constant shared by the capture, the growth
  harness and the pytest plugin's ini default, instead of the same literal
  written in three places.

## [0.2.0] — 2026-09-02

### Added
- N+1 detection by fingerprint. `NPlusOne` is a finding and `find_n_plus_one`
  produces them: more than one execution with the same normalised SQL *and* the
  same call stack is an N+1 by construction, so there is no threshold to tune,
  no rule about lazy loads and no confidence score. The identity is the whole
  stack rather than the call site, because two callers of one helper are two
  defects with two fixes; it excludes the connection alias, so a loop querying
  two databases stays one finding; and a record with no call stack is not
  grouped at all, because guessing there would manufacture a finding out of a
  gap in the input.
- `format_n_plus_one` renders one finding, call site first, and
  `format_n_plus_one_summary` renders findings gathered from several blocks.
  Both reports in the package go through them, so a finding cannot be described
  one way under a failure and another way in a listing.
- `--n-plus-one` lists every finding a pytest run produced, worst first, at the
  end of the run. Opt-in, and it changes no outcome: this package ships no
  assertion, and a finding printed under every passing test is the crying wolf
  four dead N+1 detectors were removed for.
- `docs/n-plus-one.md`, which states the definition, the two weaker identities
  that were rejected and why, the case for reporting legitimate batched writes
  like any other repetition, and the one place the identity's window stops.

### Fixed
- The per-test capture is dropped from the item's stash once the report that
  reads it is built, instead of being left there. pytest holds every collected
  item in `session.items` until the run ends, so a capture left behind was
  retained for the whole session -- every statement's SQL and up to
  `query_contract_stack_depth` frames per statement, for every test that ran.
  Measured on a synthetic suite at twenty queries a test: **64 MiB retained
  across twelve hundred tests, falling to 14 MiB**, and growing linearly before
  the fix at roughly 50 KiB a test. The passing case was the one that leaked,
  because the hook returned early on a passing report before it reached the
  stash at all -- and a suite where every test passes is the ordinary suite.
  Shipped in 0.1.0 and unmeasured until now.

### Changed
- The report section under a failing `django_assert_num_queries` now names an
  N+1 with its call site on the first line, instead of listing repeated
  statement shapes. Statements that were not repeated from any one call path,
  and statements that carried no call stack, are counted separately, so the
  numbers still add up to what was captured.
- `format_capture_report`'s `max_shapes` argument is now `max_findings`, because
  what it limits is findings.

## [0.1.0] — 2026-09-02

### Added
- The capture engine. `QueryCapture` records every statement a Django connection
  executes through `connection.execute_wrapper()`, which is independent of
  `force_debug_cursor` and `queries_log` and therefore nests inside or around
  `django_assert_num_queries` without changing what that counts.
- `QueryRecord`, public and documented from the start because four faces read it
  and three are unwritten. It carries the statement, its normalised fingerprint,
  the connection alias and vendor, the parameter count, and the call stack with
  a `call_site` that names the innermost frame outside Django. It deliberately
  carries no parameters and no duration.
- `normalise_sql`, the fingerprint: a small list of named rules that collapse
  what varies between two executions of one statement and leave structure alone.
  Variable-width `IN` lists, multi-row `VALUES`, inlined `LIMIT` and `OFFSET`,
  string literals, and the per-savepoint identifier Django emits with no
  parameters at all.
- `LogCeiling` and `QueryLogCeilingWarning`. `CaptureQueriesContext` slices
  `connection.queries` between two absolute indices over a bounded deque, so past
  `connection.queries_limit` a query count is wrong: with a full log it reports
  zero for a block that ran five queries, and
  `django_assert_max_num_queries(1)` passes. This package counts without a bound
  and says when the other path stopped being reliable.
- The pytest plugin, loaded through a `pytest11` entry point. It ships no count
  assertion. A failing `django_assert_num_queries` gains a report section naming
  the repeated shapes and their call sites; a block over the ceiling raises a
  warning whatever its outcome. `query_contract`, `query_contract_stack_depth` and
  `--no-query-contract` control it.
- `format_capture_report`, the report as a function, so the CI-report face can
  use it without a test runner.
- `QueryCapture.from_capture_context`, which serves a caller who already holds
  the `CaptureQueriesContext` that pytest-django yields. Honestly degraded: no
  stacks, no parameter counts and no ceiling, because a count taken from a
  rotated deque cannot report what it dropped.

[Unreleased]: https://github.com/Artui/django-query-contract/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Artui/django-query-contract/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Artui/django-query-contract/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Artui/django-query-contract/compare/v0.0.0...v0.1.0
