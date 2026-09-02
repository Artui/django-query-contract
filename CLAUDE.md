# CLAUDE.md

Guidance for working in this repository. The design that produced it lives in the
workspace roadmap, not here; this file is about how the code is written.

## What this package is

`django-query-contract` captures every statement a Django connection executes, with a
normalised SQL fingerprint and the call stack that emitted it, and reads that
capture back as a diagnosis. The pytest plugin and call-site attribution are two
faces of it. A CI report and a runtime budget middleware are the other two, and
they are not written yet.

Two claims decide every design question here.

**A performance assertion that mentions a duration is a flaky test with extra
steps.** Assert on shape: counts, growth, plans. Never on milliseconds. That is
why `QueryRecord` has no duration field. Timing is a profiler's job and
`django-silk` does it well.

**An assertion that passes because the measurement stopped working is worse than
no assertion.** `assertNumQueries` and pytest-django's
`django_assert_num_queries` both count through `CaptureQueriesContext`, which
slices `connection.queries` between two absolute indices taken from a
`deque(maxlen=connection.queries_limit)`. Past that bound the count is wrong and
Django says only that the log truncated. With a full log it reports **zero** for
a block that ran five queries. This package counts through
`connection.execute_wrapper`, which has no bound, and says so.

It is **not** a count assertion. `django_assert_num_queries` is the assertion,
and it is a good one: typed, `using=`-aware, and it yields the captured queries.
This package makes its failures diagnostic and covers the regime above its
ceiling. Shipping a count assertion of our own would re-implement all of that to
add a paragraph.

Also out of scope, deliberately: query-sequence snapshots (`django-perf-rec`),
forbidding queries in a block (`django-zen-queries`), timing benchmarks
(`pytest-benchmark`), and a profiler UI (`django-silk`).

## Commands

```bash
make init          # uv sync --all-groups + pre-commit install
make test          # pytest, 100% line+branch required
make lint          # ruff check + ty check
make format        # ruff format
make docs-build    # mkdocs build --strict
```

## Structural rules

- **One exported symbol per file**, file named in `snake_case` after it. The one
  exception is `plugin.py`: pytest finds hooks by name in a module, so there is
  nowhere else to put them. It stays thin for that reason and delegates
  everything testable to a module that can be exercised without a test runner.
- Private one-file helpers are prefixed `_`; helpers used across files go in
  `utils.py`.
- **Top-level imports only.** No function-level imports.
- **Full type annotations** on every function and method.
- `__init__.py` is the only re-export point, and holds no logic.
- Every annotated module starts with `from __future__ import annotations`. Ruff's
  `required-imports` enforces this rather than leaving it to memory.

## Public API naming

`QueryCapture`, `QueryRecord`, `StackFrame`, `NPlusOne`, `Attribution`,
`LogCeiling`, `QueryLogCeilingWarning`, `Growth`, `GrowthPoint`, `QueryGrowth`,
`normalise_sql`, `capture_stack`, `find_n_plus_one`, `group_by_call_site`,
`assert_query_growth`, `measure_query_growth`, `format_capture_report`,
`format_n_plus_one`, `format_n_plus_one_summary`, `format_attributions`,
`format_query_growth`. Nouns for what is recorded, verbs for what is done to it.
Nothing is named after pytest, because three of the four faces are not pytest.

**`group_by_call_site` is a grouping and `find_n_plus_one` is a detector**, and
the verbs say so. Anything named `find_` produces findings and keys on the whole
call stack; `group_by_` re-files the same records under a display rule and claims
nothing. Do not rename either into the other's register.

`utils.py` holds what more than one of them must agree on: `DEFAULT_STACK_DEPTH`
(read by both `QueryCapture` and the plugin's ini default, rather than the same
literal in three places), `DEFAULT_FACTORS`, the `ScaleWorld` alias, and the
three call-site helpers -- `innermost_frame_outside_django`, which is the one
place the package decides which frame is the interesting one, plus
`relative_to_cwd` and `shorten`, so two renderings of a call site cannot spell
one path or one `max_sql` two ways. Extend it rather than forking a second
copy: a record, a finding and an attribution disagreeing about where a statement
came from is worse than any of them having no answer.

**The growth rules are exact integer comparisons, and that is the design.** A
fitted curve would need three thresholds to become a verdict -- how near zero is
flat, how linear is linear, how good a fit is believable -- and three knobs in a
package whose thesis is "by construction, never by heuristic" is three ways to be
wrong. `CONSTANT` is equality; `LINEAR` cross-multiplies so it never leaves the
integers. Do not introduce a tolerance: a growth assertion that fails once a
fortnight gets deleted and takes the idea with it.

**`QueryRecord` is a public, documented artifact from the first release**, and
the reason is that four faces read it and two of them are still unwritten. A
record kept private until they existed would grow a private accessor per face
instead of a shape -- and attribution, the second face to arrive, read the
record without needing a field added to it. The contract in `0.x` is
**additive**: fields may be added, never removed and never given a new meaning.
It is frozen at `1.0`.

## The rules the design rests on

- **Compose, do not compete.** Capture rides on `connection.execute_wrapper`,
  which is independent of `force_debug_cursor` and `queries_log`, so it nests
  inside or around `django_assert_num_queries` without changing what that sees.
  That is a fact about the two mechanisms, and there is a test that falsifies it
  in both nestings.
- **Identify by construction, never by heuristic.** More than one execution with
  the same normalised SQL *and* the same call stack is an N+1 with nothing to
  tune. Four earlier N+1 detectors are dead on PyPI, and the most probable reason
  is that they classified by rule -- `nplusone` listens for lazy loads -- so they
  cried wolf and were deleted. A detector nobody disables is a different package
  from a detector that finds more.
  **The identity is the whole stack, not the call site**: two callers of one
  helper are two defects with two fixes, and the call site alone would name the
  one line that is fine. It excludes the connection alias, because the rule above
  does not mention one and splitting on it would break one loop into two
  findings. A record with **no** stack is not grouped at all -- guessing there
  manufactures a finding out of a gap in the input.
  **The call site is a display rule and must stay one.** `Attribution` groups by
  the innermost frame outside Django, which merges the two callers of one helper
  that the identity above deliberately splits. That is safe *only* because a
  group claims nothing about defects -- it is statements and an address, nothing
  fails on it, and no rule about which repetition counts is anywhere near it. The
  moment a frame rule reaches an identity it is a knob, and a knob in an
  identity is how the four dead detectors came to cry wolf. The distinction is
  stated in `Attribution`, in `group_by_call_site`, and in
  `docs/attribution.md`; a test in `test_group_by_call_site.py` runs one capture
  through both readings and pins that they disagree.
  **The identity is really the innermost `stack_depth` frames**, which is the one
  place it can be wrong. Under pytest a query from a test function is 38 frames
  deep and 30 of them are the runner's own, so `stack_truncated` is set on every
  capture at any workable depth and neither report prints it. An application
  stack deeper than the window can merge two paths -- which understates findings,
  never invents one.
- **Nothing fails on a finding.** A batched `bulk_create` is structurally the
  defect and is reported like any other repetition; an exemption list would be
  the first tunable. What keeps it from crying wolf is that a finding only
  appears under a failure somebody else's assertion produced, or in the
  `--n-plus-one` listing somebody asked for.
- **Report the ceiling, never paper over it.** A package about honest performance
  assertions does not get to repeat the failure it was built to expose.
- **Degrade honestly and say where.** A capture rebuilt from a
  `CaptureQueriesContext` has no stacks and no ceiling; it says so rather than
  presenting an empty stack as a top-level call. When plan assertions arrive they
  will skip with a reason on non-PostgreSQL rather than pass vacuously.
- **Retain no parameters.** A `bulk_create` is one execution and ten thousand
  values, and the runtime face would be holding customer data to answer a
  question about query counts. `param_count` is what a diagnosis needs; the plan
  face runs `EXPLAIN` at execution time, where the parameters are still in hand.

## Adding a feature

Write the test first, watch it fail, then implement. A new public symbol gets its
own module, a re-export in `__init__.py`, and a docs entry.

## Tests

- `tests/` mirrors the source layout.
- `pytest-asyncio` runs in auto mode.
- **100% line and branch coverage.** Never `# pragma: no cover` -- restructure
  the code instead.
- **The suite runs with this package's own plugin disabled**, through
  `-p no:django_query_contract` in `addopts`. pytest imports entry-point plugins
  before pytest-cov starts measuring, so with the plugin on, every module it
  pulls in at import time is already loaded when coverage begins and is reported
  at 0% for lines that in fact ran. The hooks are covered by `test_plugin.py`,
  which runs pytest inside pytest with the plugin on, and by
  `test_plugin_hooks.py`, which drives each hook directly with real `Config`,
  `Item`, `TestReport` and `pluggy.Result` objects. Removing the flag does not
  make the suite dogfood the plugin; it makes the gate stop measuring the package.
- **Three consequences of that flag, all of which have bitten once.**
  `tests/conftest.py` registers the plugin's *options* without its hooks, or a
  hook driven against the live item raises `no option named '--no-query-contract'`.
  An inner `runpytest_subprocess` run must inherit no `COV_CORE_*` environment,
  or it writes statement data into the parent's branch data and the combine
  fails -- only at the dependency floor, because `branch` reaches a subprocess
  from the `--cov-branch` flag and this project declares it in `pyproject.toml`.
  And a hook test that touches the database must use the live item, never a
  second `Config`: each config builds its own pytest-django database blocker, so
  the outer one cannot give back what the inner one took, and the connection
  stays shut through teardown.
- **Run the suite against the floor before pushing anything that touches
  `tests/`.** `uv lock --resolution lowest-direct --refresh` then
  `uv sync --frozen --all-groups`; restore `uv.lock` from git afterwards,
  because uv records the resolution mode inside it and a lock left that way
  re-resolves every later sync. Both bugs above were invisible at the pinned
  resolution and reproduced immediately at the floor.
- **A test that asserts a query count must assert the count, never a duration.**
- The ceiling is falsified at the real limit once, in
  `test_query_capture.py::test_the_ceiling_is_real`, and at a shrunken limit
  everywhere else through the `tiny_query_log` fixture. Keep that split: the
  expensive test is what makes the cheap ones honest.

## Type checking

`ty`, not mypy. `make type-check` runs it over the package.
No `# type: ignore` -- a pre-commit hook rejects it.

## Linting and formatting

Ruff is the source of truth for both. Use `...` over `pass` for empty bodies.
**`make lint` does not run `ruff format --check`; CI does.** Run
`uv run ruff format --check` before pushing.

## Imports inside the package

Absolute only. `from django_query_contract.x import y`, never `from .x import y` --
`ban-relative-imports = "all"` rejects every relative form including single-dot.

## Compatibility floor

`django>=4.2`, `python>=3.10`, checked per PR by the `lowest declared versions`
CI job, which resolves `--resolution lowest-direct` and runs the suite against
that resolution. Raise a floor only when the capture needs a newer API, never on
age.

**`pytest` is deliberately not a dependency.** The plugin reaches pytest through
the `pytest11` entry point, which only pytest reads. Declaring it would drag a
test runner into every consumer running the middleware face in production. The
floor job asserts this by importing the package into a venv with no dev group and
checking that `pytest` is absent from `sys.modules`.

## CI and pre-commit

Every action is pinned to a commit SHA with a trailing `# vX.Y.Z` comment. The
comment is functional -- Dependabot parses it and rewrites both together.

Pre-commit runs gitleaks, the standard hygiene hooks, ruff, ty, and four
convention guards: no absolute local paths, no internal plan labels, no
mypy-style `# type: ignore`, no emoji or marker glyphs in code, docs or
changelogs. Never add a `--no-verify` escape hatch; fix the cause.

**The coverage gate lives on the SQLite matrix**, unlike `django-data-shape`,
which gates on Postgres. The difference is what the package is for: everything
here is backend-neutral, so SQLite reaches every line. When plan assertions
arrive they will be PostgreSQL-only, and the rule that keeps the gate here is to
branch their refusals on the connection's **vendor**, so a degradation path is
covered by passing a vendor rather than by running the suite on the backend being
refused.

## Common pitfalls

- **Do not reach for a SQL parser.** The statements that arrive at
  `execute_wrapper` carry Django's `%s` placeholders -- the backend's own
  paramstyle is applied below the wrapper -- and `%s` is a syntax error to a
  PostgreSQL grammar, so `pglast` cannot read the input at all without the
  parameters being substituted back in, which is the opposite of what a
  fingerprint is for. It is also PostgreSQL-only, and about fifteen times a regex
  pass per query.
- **The fingerprint cache is bounded on purpose.** A wide `IN` list produces one
  distinct statement per width, so an unbounded cache would grow with the data.
- **Capture costs roughly a quarter of a query's own time** on the cheapest
  backend, and the stack walk is the part that scales. That is why
  `stack_depth` is a knob and why its default is measured rather than round: six
  frames separate `cursor.execute` from the line that iterated a queryset.
- **A savepoint name is not a parameter.** Django emits
  `SAVEPOINT "s<thread>_x<n>"` with no bindings at all, so a normaliser that only
  strips placeholders makes every nested `atomic()` a unique shape.
- **The capture stops where Django's cursor wrapper stops.** `execute_wrapper`
  sees `execute` and `executemany`; a statement on the raw driver connection, or
  a driver API that is neither -- psycopg 3's `cursor.copy()`, which is how
  `django-data-shape` loads rows -- is invisible. Django's own query log has the
  same blind spot, so the two agree, and a test pins it.
- **The plugin captures around the call phase only.** A limit or a log changed
  inside a test body is read after the ceiling has already been measured; set up
  that state in a fixture.
- **Do not name `pytest.TerminalReporter`.** That alias reached pytest's public
  namespace well after the declared `pytest>=8.0` floor, so a module or a test
  that references it passes at the pinned resolution and fails the floor job.
  Take the reporter off the plugin manager and annotate it `Any`.

## Releasing

```bash
make release-bump VERSION=X.Y.Z
# edit CHANGELOG.md to fill in the new section, review the diff
# open a PR, get it reviewed, merge to main
```

Merging to `main` triggers `release.yml`, which no-ops unless the version in
source has been bumped past the most recent `vX.Y.Z` tag.
**If a step after the PyPI upload fails, re-run the job** -- every phase is
idempotent and that is the designed recovery. Do **not** hand-push the tag:
`prepare` gates on the tag, so a manual one makes it report `released=false` and
skips both the finalize step and the docs deploy.
