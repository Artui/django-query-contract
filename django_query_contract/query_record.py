"""One database execution, as this package remembers it."""

from __future__ import annotations

from dataclasses import dataclass, field

from django_query_contract.query_plan import QueryPlan
from django_query_contract.stack_frame import StackFrame
from django_query_contract.utils import innermost_frame_outside_django


@dataclass(frozen=True, slots=True)
class QueryRecord:
    """A single statement, its fingerprint and the stack that emitted it.

    This is the artifact the whole package is built around, and it is public and
    documented from the first release on purpose: four separate faces read it --
    the pytest plugin, a CI report, call-site attribution and a runtime budget
    middleware -- and two of them are still unwritten. A record kept private
    until they are would grow a private accessor per face instead of a shape.
    Attribution is the evidence that the bet paid: it reads this record and
    needed no field added to it.

    The contract in ``0.x`` is additive: fields may be added, never removed and
    never given a new meaning. It is frozen at ``1.0``.

    Two things are deliberately absent.

    **No parameters.** Retaining them would pin every bound value for the length
    of a capture -- a ``bulk_create`` of ten thousand rows arrives here as one
    execution and ten thousand values -- and the runtime middleware face would
    then be holding customer data in memory to answer a question about query
    counts. ``param_count`` is what the diagnosis actually needs ("the ``IN``
    list had five hundred entries"), and the plan face runs ``EXPLAIN`` at
    execution time, where the parameters are still in hand.

    **No duration.** This package's argument is that a performance assertion
    mentioning a number of milliseconds is a flaky test with extra steps, and a
    field invites the assertion. Timing a query is a profiler's job;
    ``django-silk`` does it well and is deliberately out of scope.
    """

    index: int
    """Position within the capture, counting from zero. Names a query in a report."""

    sql: str
    """The statement exactly as handed to the cursor, placeholders and all."""

    fingerprint: str
    """``sql`` reduced to the part that repeats. See ``normalise_sql``."""

    alias: str
    """The Django connection alias this ran on."""

    vendor: str
    """The backend's ``vendor`` string: ``sqlite``, ``postgresql``, ``mysql``, ``oracle``."""

    many: bool
    """``True`` when this arrived through ``executemany`` rather than ``execute``."""

    param_count: int | None
    """How many bindings were passed -- rows, for ``executemany``.

    ``None`` when the parameters were not sized: ``None`` itself, as every
    transaction control statement passes, or an iterator, which Django permits
    and which cannot be measured without consuming it.
    """

    stack: tuple[StackFrame, ...] = field(default=())
    """The call stack, outermost first. Empty when reconstructed from a source that had none."""

    stack_truncated: bool = False
    """``True`` when the stack was deeper than the capture's limit and outer frames were dropped."""

    plan: QueryPlan | None = field(default=None)
    """What PostgreSQL said it would do with this statement, when it was asked.

    ``None`` means nobody asked: an ordinary
    :class:`~django_query_contract.QueryCapture` takes no plans, and neither does
    a capture rebuilt from a ``CaptureQueriesContext``. A
    :class:`~django_query_contract.PlanCapture` puts a
    :class:`~django_query_contract.QueryPlan` on every record it makes, including
    the statements it declined to explain -- those carry a plan whose ``root`` is
    ``None`` and whose ``refusal`` says why, so "not asked" and "asked and
    declined" stay distinguishable.

    **This is the first field added under the additive contract, and it is what
    the contract was for.** The record has been public since 0.1.0 on the bet
    that four faces would read it, and the docstring above has said since then
    that the plan face runs ``EXPLAIN`` at execution time because that is where
    the parameters still are. Adding the field changes nothing for a reader that
    does not want it, which is the promise ``0.x`` made.
    """

    @property
    def call_site(self) -> StackFrame | None:
        """The innermost frame outside Django: the line that asked for this query.

        ``None`` when the stack holds no such frame -- an empty stack, or one
        truncated before it reached the caller. That is reported rather than
        approximated with the innermost frame available, because "the query came
        from ``django/db/models/query.py``" is true of every query and tells a
        reader nothing.

        Django is the only package skipped. Anything else in the stack -- a REST
        framework, a factory library, a service layer -- did emit the query, and
        deciding that some libraries are more interesting than others is the
        kind of tuning this package exists without.

        An :class:`~django_query_contract.NPlusOne` names its call site the same
        way, through the same helper, so a finding and the records inside it can
        never disagree about where they came from.
        """
        return innermost_frame_outside_django(self.stack)
