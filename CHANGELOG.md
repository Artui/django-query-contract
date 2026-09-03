# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.0] — 2026-09-03

### Fixed
- **A failing `EXPLAIN` no longer aborts a transaction this package did not
  open.** The savepoint guard read `connection.in_atomic_block`, which answers
  *did Django open a transaction* -- not *is this connection in one*. Manual
  transaction management, which Django documents and `ATOMIC_REQUESTS` reaches by
  another road, puts the driver inside a transaction with that flag still
  `False`, so no savepoint was taken and a statement PostgreSQL declined to
  explain left the connection in "current transaction is aborted", cascading
  `InFailedSqlTransaction` into every later statement. A consumer lost two full
  suite runs to it. The guard now also asks `get_autocommit()`.
  - **The test double was missing the method, which is why every test agreed
    with the bug.** The stub connection answered `in_atomic_block` and nothing
    else, so a guard reading only that had nothing to disagree with it. It
    answers both now.
  - **The reported cause was a cancelled statement escaping the savepoint, and
    that is not what happens.** A cancel is caught and refused like any other
    failure, verified against a real server either side of an atomic block -- the
    case that escaped was the one where no savepoint was taken at all.

- **A cancelled `EXPLAIN` now says what to do about it.** Cancellation is the one
  failure here with a remedy the caller can act on, so it is the one refusal
  that says more than a class name: the cause is almost always
  `statement_timeout`, `EXPLAIN (ANALYZE)` runs the statement a second time, and
  the ways out are more headroom or `analyze=False`. Everything it adds is
  derived from the exception class and never from its message, so the rule that
  keeps a bound value out of a refusal is untouched. Both spellings are
  recognised -- psycopg 3 raises `QueryCanceled` and psycopg 2 raises
  `QueryCanceledError` -- matched by name, because this package imports neither
  driver and issues `EXPLAIN` through whichever one the connection already has.

### Documentation
- **Plan capture needs timeout headroom, and 1.7x is a floor rather than a
  budget.** The multiplier is worst on exactly the statements a plan is most
  wanted for, because instrumenting a plan whose nodes loop millions of times
  costs more than instrumenting one that scans once. A consumer measured a
  15-second endpoint pass a 120-second `statement_timeout` under `analyze=True`.
- **`total_actual_rows` is not a budget currency**, said plainly where it is
  introduced. It is the number that finally exposes fan-out, which is exactly
  why the first instinct is to assert a ceiling on it -- and it moves with the
  plan the server chose on the day: three consecutive pairs on unchanged code
  read 46,768 then 542,613, 84,731 then 416,086, 2,462 then 76,475. The rule is
  the one durations get.
- **The free check is promoted to its own section.** `analyze=False` plus
  `unanalyzed_relations` costs about 1.02x, which is cheap enough to leave on
  permanently, and it is the check most likely to fire on a suite that has never
  used this package: a consumer found their entire performance fixture had never
  been `ANALYZE`d, and one `ANALYZE` took that suite from 531s to 210s.
- **A monkeypatching library becomes the call site, and the next frame down is
  the answer.** `django-zeal` patches the ORM in place, so it is genuinely the
  innermost frame outside Django and the rule is not wrong about that. Named as
  an expectation rather than fixed with an exclusion list, which is the tuning
  every dead N+1 detector died of.


## [0.7.0] — 2026-09-03

### Added

- **`PlanNode.total_actual_rows` and `PlanNode.total_rows_removed_by_filter`**
  multiply by `loops`, and `PlanNode.parallel_aware` says which of the two causes
  the loops were: a parallel node's work was *divided* between processes, a
  nested loop's inner side *repeated* once per outer row. Where `loops` is 1 the
  totals are the numbers they always were, so adopting them costs nothing on a
  small world. They are reconstructions -- PostgreSQL rounds the average before
  printing it, so multiplying back can be out by up to `loops / 2` -- and that is
  stated on the accessor rather than hidden, because the alternative is a number
  the server does not print at all.

- **Two new payloads, and they are a pair.** One `SELECT COUNT(*)` over 1,200,000
  rows, captured twice with nothing different but whether parallelism was
  allowed: `Rows Removed by Filter` reads 1,124,098 in one process and 374,699 in
  three, for the same work. A checked-in payload can only ever agree with itself
  about which of two numbers is the reconstruction, so the same claim is asserted
  against a live server in the `postgres` job as well, where the two plans are
  produced by running one statement twice.

### Changed

- **`LogCeiling.headroom` is now `LogCeiling.headroom_at_enter`.** The number was
  always right and the name was not: a capture reads the log length once, on the
  way in, so four thousand statements later it still reports the room there was
  at the start. It sits beside a field already spelled `log_length_at_enter`. The
  log length at *exit* is not obtainable -- Django writes a statement to the log
  only when the debug cursor is on, while a capture counts every execution
  regardless -- so this is the only honest reading and it is now named for the
  moment it describes. **The old name is removed rather than aliased**, which is
  a call this package can make at `0.x` and would not be able to make later: the
  point of the rename is that the short name reads as a live number, so keeping
  it would keep the misreading it exists to end.

- **`RelationAccess.most_rows_discarded` now ranks and reports on the whole
  read**, not one loop of it. A read PostgreSQL split across three processes is
  still one read of that table and it discarded everything the three of them
  discarded; ranking on the printed number would order two reads by how many
  workers the server happened to start. The relation block shows its working --
  `across 3 loops (parallel workers); PostgreSQL states 374,699 discarded per
  loop` -- so the report can still be checked against `EXPLAIN` output line by
  line. **This changes the value the property returns** for a multi-loop node.

- **The query log is emptied at the start of each test, which is what stops one
  test's ceiling warning naming another test.** Django clears `queries_log`
  itself in `TransactionTestCase._pre_setup`, with the comment that
  `assertNumQueries` stops working once it overflows -- pytest-django runs that,
  but only for a test that asked for the database. Verified at a log shrunk to
  five entries: a test that runs six statements leaves it full, and the next test
  that does not use the `db` fixture is told its own single statement is
  invisible, under its own name. The reset happens before any fixture of the test
  has run, which is where Django would have done it and is the only place that
  cannot disturb a fixture holding a `CaptureQueriesContext` open across the test
  body. `--no-query-contract` turns it off with everything else.

### Notes

- **Every row count on a plan node is per loop, and that is now readable as a
  total.** `actual_rows` and `rows_removed_by_filter` are exactly what PostgreSQL
  prints, and PostgreSQL divides both by `Actual Loops` first. Over a small
  database every node runs once and the printed number is the whole truth; over a
  big one the same statement is handed to three processes, or the same scan runs
  once per outer row, and the number silently becomes a share. An assertion
  written against the first world goes on passing against a different claim in
  the second, with no error and no warning -- which is the one failure mode this
  package exists to refuse, found in its own output by a consumer composing it
  with [django-data-shape](https://github.com/Artui/django-data-shape) over 1.5M
  rows.

- **There is deliberately no total for the estimate**, and the two payloads that
  decided it are checked in. Under a `Gather` the planner divides its estimate by
  `parallel_workers` plus the fraction of a worker it credits the leader with:
  measured, 400,000 estimated serially against 166,667 on the parallel node,
  which is 2.4 and not the loop count of 3, and 2.4 appears nowhere in the
  output. Under a nested loop `loops` is the number of outer rows that *arrived*,
  so multiplying a per-loop estimate by it produces a number nobody predicted --
  measured on an inner node estimating 60 rows over 1,260 loops, the product is
  75,600, exactly what the join measured, while the planner's own estimate for
  that join was 400,020. A `total_estimated_rows` would be wrong under a `Gather`
  and would agree with the measurement under a nested loop, which is worse: it
  would read as perfect agreement on the plan the planner got most wrong.

- **`PlanNode.estimate_error` is inflated on a parallel-aware node and now says
  so.** It divides an estimate scaled by 2.4 by a measurement scaled by 3, so it
  reads about 25% high even where the planner was right -- 6.6x against a real
  5.3x on the checked-in pair. There is no repair, because the divisor is not in
  the output, so the ratio stays what the server's two numbers say and the report
  prints the caveat under the node it applies to.

- **Corrected: `stack_truncated` was documented as the way to know whether a
  finding merged two call paths, and it cannot be.** Under a test runner it is
  `True` on every capture at every depth a suite would use, because the frames
  beyond the window are pytest's own -- so it is a constant, and a constant
  distinguishes nothing. What does is a second measurement: raise `stack_depth`
  and see whether the finding splits, because a merge is the thing that stops
  being one when the window widens. There is now a test that widens it, on twelve
  identical frames of recursion between two callers and a query.

- **The "planner blind" documentation says which query shape can reproduce it,
  and how many parents that needs.** Filter a child's foreign key column directly
  and PostgreSQL consults that column's most-common-values list, so the head of a
  skewed fan-out is priced individually and roughly right and only the tail
  shares an estimate -- and the tail exists only where there are more distinct
  parents than `default_statistics_target`. Measured: at 50 parents the list
  covers all of them and every one is priced to within 10%, so the finding is
  unreachable and correctly so; at 5,000 the list holds 100 and every parent
  outside it is estimated at 402 rows against measured answers of 4,000, 800 and
  80. Joining *through the parent* sidesteps both, because a column comparison
  has no MCV list and every value gets the same average -- which is why the
  documented example is written that way.

- **The `measure_query_growth` documentation shows `format_query_growth`**, whose
  second argument is required and had no example. It stays required and gets no
  default: one curve reads as a pass against `LINEAR` and a failure against
  `CONSTANT`, so defaulting would put a claim nobody made into a report.

## [0.6.0] — 2026-09-02

### Notes
- **The `ty` floor was raised to `0.0.32`, because the declared one was false.**
  `ty==0.0.1a10` cannot parse the `[tool.ty.environment]` table this repository
  has shipped since its first commit -- it fails with a TOML parse error. The
  `lowest declared versions` job passed only because the resolver it runs under
  rounds the pre-release up. A floor nothing can resolve to is not a floor.

- **Index advice was the milestone and it is declined, in writing.** The plan
  this package came from said the output people actually want is "these twelve
  queries sequentially scanned a two-million-row table, here are the
  `CREATE INDEX` statements", and that it falls straight out of having plans plus
  call sites. It does not. Three routes to an assertable version were tried
  against a real server and all three ended in a threshold, which is the knob
  this package refuses everywhere else.
- **The near miss is worth recording, because it reads threshold-free and is
  not.** "A sequential scan on a relation that another captured statement
  reaches by index" looks like a comparison between two measurements rather than
  a cut-off. Two statements filtering *different columns* of one table are not
  measuring the same thing: measured against a server, one statement reached
  `testapp_order` through the foreign key index while another read it end to end
  for a predicate that kept all 100,000 of its rows -- the correct plan, and the
  one no index improves. Both halves of the rule hold and the index it names
  could not have helped. `Rows Removed by Filter` failed for the plainer reason:
  the server supplies the number and nobody supplies the verdict, so a five-row
  table discards four rows in the same shape a hundred-thousand-row table
  discards 99,999. Both refutations are tests, run rather than argued.
- **What ships instead is the evidence, with the judgement left to the reader.**
  `RelationAccess`, `group_by_relation` and `format_relation_access` read a
  capture back as the tables it touched: how PostgreSQL reached each one, the
  predicate it applied, how many rows it said it threw away, the lines that
  asked, and the indexes that already exist. It is a **grouping** and not a
  detector, in the sense call-site attribution is one -- which is exactly what
  makes it safe to put a sequential read of a table beside an indexed read of the
  same table, where a finding would not be. The block is printed under
  `format_query_plans`, so a failing test that used the `query_plans` fixture
  gains it.
- **The relations are ordered by how many times they were read and deliberately
  not by rows discarded.** That second order is the one a reader would find most
  useful, and is exactly why it is refused: ranking tables by how badly they want
  an index is the declined judgement, and a sort key is a quiet way of making it
  anyway. The test that pins this pulls the two orders apart, because a fixture
  where they agree passes either way -- and the first one written did.
- **Fixed: a plan node retained the value bound to the statement.** `EXPLAIN`
  renders a predicate with the parameter substituted, so a real server writes
  `Filter: ((reference)::text = '601980.6826913885'::text)` for a query bound
  with `%s`, and `PlanNode.condition` kept that string verbatim. This package
  retains no parameters anywhere else, and the sentence it prints when it
  declines to quote a driver error says so to the reader. `condition` is now put
  through the same `normalise_sql` rules the statement fingerprint is made with:
  the column, the operator and the casts survive and the value becomes `%s`.
  **This changes what the field holds**, one release after it shipped, and it is
  the right way round -- the field's documented purpose never included the
  values. The redaction is also what makes the predicate groupable: with the
  value in it, one statement shape run with twelve parameters is twelve
  conditions and no report could say the twelve executions did the same thing.
- **`PlanNode.indexes_used` walks, because PostgreSQL splits a bitmap read
  across nodes.** The `Bitmap Heap Scan` names the table and carries no index at
  all, while the `Bitmap Index Scan` beneath it names the index and no table; put
  a `BitmapAnd` between them and the index is two levels down. Reading the node
  alone would report a table PostgreSQL reached through two indexes as one it
  read end to end, which is the single worst thing this report could say. The
  walk stops at the next node naming a relation, because that is a different read
  of a different table. Both shapes are pinned by a real server's payload.
- **`PlanCapture.relation_indexes` asks the catalogue what already indexes the
  tables a capture planned over**, on the driver cursor beside the statistics
  question that was already there, so a diagnostic still cannot inflate the count
  `django_assert_num_queries` reads. The definitions come from
  `pg_get_indexdef` unedited, so an expression index, a partial index and a
  non-default operator class all come out right without this package learning any
  of the three -- and they are the only `CREATE INDEX` statements it prints: the
  ones that exist, beside the filter nothing covers.

## [0.5.0] — 2026-09-02

- Plan capture, and it is the milestone the dependency on
  [django-data-shape](https://github.com/Artui/django-data-shape) existed for.
  `PlanCapture` runs `EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)` on
  every captured statement that begins with `SELECT` and hangs the result off
  `QueryRecord.plan`, so a plan travels with the statement it belongs to and with
  the call stack that emitted it. `QueryPlan`, `PlanNode`, `PlanDefect`,
  `PlanFinding`, `find_plan_defects`, `format_query_plans` and `PlansUnsupported`
  are the rest of the surface, and the `query_plans` fixture is the pytest face.
- **The plan is taken at execution time because it has to be.** This package
  retains no parameters, so a plan cannot be taken after the fact from a record
  -- which was written into `QueryRecord` in the first release, before the plan
  face existed. `QueryRecord.plan` is the first field added under the additive
  `0.x` contract, and adding it changes nothing for a reader that does not want
  it.
- **Two findings ship, and there are two because only two can be stated without
  a threshold.** `PLANNER_BLIND` is two or more executions of one statement shape
  whose plans agree exactly on the row count and whose measured rows do not --
  `==` and `!=`, with no magnitude anywhere in it. Measured against a Zipf
  fan-out of 400,000 rows over 20,000 parents: joined through the parent rather
  than through the foreign key column, a whale and a tail row are both estimated
  at **20** rows against actuals of **20,323** and **6**, because across a join
  PostgreSQL has only `n_distinct` for the edge and an average is the one number
  that is wrong at both ends of a skew. `SPILLED_TO_DISK` is PostgreSQL saying
  `work_mem` was not enough -- a sort's `Sort Space Type: Disk`, more than one
  hash batch, a hash aggregate's disk usage -- so its threshold belongs to the
  database under test rather than to this package.
- **The estimate-versus-actual ratio is reported on every node and classified
  nowhere**, and that is the design rather than an omission. "The planner
  expected 20 rows and 20,323 arrived" is a fact about a plan; "more than fifty
  times out is a defect" is a policy about size, and a policy about size is the
  knob this package refuses everywhere else. The report orders nodes by it and
  prints the caveat beside them, because the commonest large ratio has no defect
  under it at all -- a node under a `LIMIT` stops early by design. The two
  candidate findings that needed a number, a sequential scan over a row threshold
  and a nested loop with a large inner, are declined in writing.
- **One measurement cannot make a blindness claim**, which is the same rule the
  growth assertion keeps from the other side: a claim about a shape needs two
  points. A growth claim needs two worlds; a blindness claim needs two
  executions. Its identity is also the statement shape and deliberately **not**
  the call stack, the opposite of the N+1 identity -- because a finding is keyed
  on what the accused can see, and the planner is handed SQL and never hears
  about the stack.
- **It refuses rather than degrading, on a backend with no planner.**
  `PlanCapture` raises `PlansUnsupported` on entry, before a statement has run,
  and the `query_plans` fixture turns that into a skip carrying the same
  sentence. Every other degradation here reports and carries on, because those
  are still measurements; an empty plan capture is indistinguishable from a
  healthy one, so an assertion over it would pass because the backend could not
  check it. The decision is made from the connection's `vendor` string, which is
  what keeps this repository's coverage gate on the SQLite matrix.
- **A plan over ten rows is a lie, and a vendor check cannot see that half.** A
  capture asks the catalogue once, at the end of the block, which of the
  relations it planned over PostgreSQL has never gathered statistics for, and
  `format_query_plans` says so above everything else because it invalidates
  everything else. It deliberately says nothing about whether the tables are big
  *enough*: "ten rows is too few" is a number.
- **`TIMING OFF` is this package's thesis said to PostgreSQL**, not a cost
  optimisation that happens to agree with it. A per-node duration would be a
  field inviting an assertion about milliseconds, and the argument here is that
  such an assertion is a flaky test with extra steps. What it costs is measured
  rather than estimated: against PostgreSQL 16 on a shaped 400,000-row world, a
  two-statement block took 8.9 ms alone and 14.8 ms with plan capture, about
  1.7x, which is what running each statement twice buys. `analyze=False` was
  1.02x and can produce no finding at all, so `ANALYZE` is the default and the
  report says when it was not used.
- **Only a statement beginning with `SELECT` is explained, because
  `EXPLAIN ANALYZE` executes what it is given.** The rule is "begins with
  SELECT" rather than "does not begin with INSERT" because a data-modifying CTE
  is written `WITH ... INSERT` and does not announce itself in its first word.
  Everything skipped carries a `QueryPlan` whose `refusal` says why, so "nobody
  asked for plans" and "we declined to explain this one" stay distinguishable,
  and the report counts them.
- **Two things plan capture must not do to a test, both tested against a real
  server.** The `EXPLAIN` goes out on the driver connection *underneath* Django's
  cursor rather than through it, so neither it nor the savepoints around it reach
  `connection.queries_log` -- which is what `django_assert_num_queries` counts
  through, and the obvious implementation would have inflated every count in a
  suite that turned this on. And it runs under a savepoint, so a statement
  PostgreSQL declines to explain costs a plan rather than the transaction; there
  is a test for the savepoint holding and a test for removing it poisoning the
  transaction.
- A `postgres` CI job, because everything above is covered on SQLite by passing a
  vendor string or a real server's checked-in payload, and both of those agree
  with whatever this repository believes PostgreSQL does. The job runs the same
  entry points against a real one over a database shaped by `django-data-shape`,
  asserts that every key the parser reads is a key the server still writes, and
  fails if the plan tests skipped rather than ran. It carries no coverage gate;
  one gate, on the SQLite matrix, is still the design.
- `query_plan_connections`, a fixture to override where a project's second
  database is not PostgreSQL. `PlanCapture()` requires *every* configured
  connection to be one, because a capture that quietly skipped the connection it
  could not explain would be the silent gap it exists to refuse -- and without a
  way to name the one you meant, that rule would skip every plan test in a
  project with a SQLite cache.
- `docs/plans.md`, and the index advice this milestone deliberately does not
  build: each node keeps its relation, its filter and the rows that filter threw
  away, beside the call stack that emitted the statement, which is what an advisor
  needs.

## [0.4.0] — 2026-09-02

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
- `relative_to_cwd` and `shorten` moved into `utils.py` from
  `format_n_plus_one`, so the two renderings of a call site cannot spell one
  path, or one `max_sql`, two different ways. Both are internal.
- There is deliberately **no run-wide listing of call sites** to match
  `--n-plus-one`, and the reason is memory. A call site's group *is* its
  records, so gathering them across a session would re-create the retention bug
  0.2.0 fixed: 64 MiB across twelve hundred tests. A run-wide profile of query
  counts per line belongs to the reporting face, which can aggregate to counts
  and drop the records.

## [0.3.0] — 2026-09-02

### Added
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

[Unreleased]: https://github.com/Artui/django-query-contract/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/Artui/django-query-contract/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Artui/django-query-contract/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Artui/django-query-contract/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Artui/django-query-contract/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Artui/django-query-contract/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Artui/django-query-contract/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Artui/django-query-contract/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Artui/django-query-contract/compare/v0.0.0...v0.1.0
