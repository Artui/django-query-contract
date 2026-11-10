from __future__ import annotations

from dataclasses import dataclass, field

from django_query_contract.types.query_plan import QueryPlan
from django_query_contract.types.stack_frame import StackFrame
from django_query_contract.utils import (
    innermost_frame_in_project,
    innermost_frame_outside_django,
)


@dataclass(frozen=True, slots=True)
class QueryRecord:
    """A single statement, its fingerprint and the stack that emitted it."""

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
        """The innermost frame outside Django: the line that asked for this query."""
        return innermost_frame_outside_django(self.stack)

    @property
    def project_call_site(self) -> StackFrame | None:
        """The innermost frame that is the reader's own: the line to go and edit."""
        return innermost_frame_in_project(self.stack)
