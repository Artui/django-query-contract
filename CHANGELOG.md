# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Artui/django-query-contract/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Artui/django-query-contract/compare/v0.0.0...v0.1.0
