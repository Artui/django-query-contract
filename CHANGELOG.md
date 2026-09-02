# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Artui/django-query-contract/compare/v0.0.0...HEAD
