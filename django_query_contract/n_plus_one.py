"""One N+1: a statement shape that ran more than once from a single call path."""

from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.query_record import QueryRecord
from django_query_contract.stack_frame import StackFrame
from django_query_contract.utils import innermost_frame_outside_django


@dataclass(frozen=True, slots=True)
class NPlusOne:
    """A repeated statement, and the one place it was repeated from.

    **The definition is the product.** More than one execution with the same
    normalised SQL *and* the same call stack is an N+1 by construction: the same
    line of code ran the same statement again, with different data, instead of
    asking for the data once. There is no threshold, no rule about lazy loads
    and no confidence score, so there is nothing to tune and nothing to be wrong
    about.

    That matters because of how the ground looks. Four Python N+1 detectors are
    dead on PyPI -- ``nplusone`` (2018, and still what every blog post
    recommends), ``django-query-capture`` (2022), ``django-nplusone`` (2020) and
    ``django-explain`` (2016) -- and the most probable reason is that they
    classified by rule. ``nplusone`` listens for lazy loads, which flags
    legitimate code and misses real N+1s behind an explicit loop. A detector
    people disable finds nothing at all.

    **The identity is the whole stack, not the call site.** Two weaker keys were
    considered and both are rules about which frames matter, which is exactly
    the judgement that turns into a knob:

    - *The fingerprint alone* would merge a loop in a view with a loop in a
      template that happen to emit the same SQL, and report one finding whose
      "call site" is whichever of the two was seen first.
    - *The innermost frame outside Django alone* would merge two callers of one
      helper. ``get_books(author)`` called from two different loops is two
      defects with two fixes, and a report pointing at the helper points at the
      one line that is fine.

    The whole stack cannot make either mistake, because two executions with
    identical stacks did run the identical code path. It also cannot split a
    loop: every iteration of a loop enters the query through the same frames at
    the same lines. The one shape it does split is recursion, where the same
    line is reached at several depths and each depth is its own finding -- true,
    a little noisy, and preferred over the alternative of pointing a reader at a
    line that is not where the fix goes.

    **The connection alias is not part of the identity**, because the claim
    above does not mention it: a loop that queries two databases from one line
    is one loop with one fix. ``aliases`` reports the span instead of encoding
    it, so the report says what happened without the rule acquiring a clause.

    **Where "the whole stack" stops being whole, stated rather than glossed.**
    The capture keeps the innermost ``stack_depth`` frames, so the identity is
    really that window. Measured under pytest, a query issued from a test
    function is 38 frames deep and 30 of them are the runner's own constant
    preamble, so at the default depth of 25 the window reaches well past the
    test function and the frames it drops cannot tell two call paths apart
    anyway. It is an application whose own stack is deeper than the window that
    can put two paths in one bucket -- and the error it makes is a *merge*: two
    findings reported as one, never a repetition that did not happen. Raise
    ``stack_depth`` to narrow the window, and read ``stack_truncated`` to know
    it was one.

    **Legitimate repetition is still a finding.** A ``bulk_create`` batched into
    a hundred inserts is one statement shape executed a hundred times from one
    line, and there is no structural difference between that and a defect --
    only an intention, which is not in the capture. So this reports it, and the
    package refuses to fail anything on it: a finding is a diagnosis attached to
    a failure somebody else's assertion already produced, or a list somebody
    asked for. An exemption list would be the first tunable, and the first
    tunable is how a detector starts being wrong.
    """

    fingerprint: str
    """The normalised SQL shared by every record here. See ``normalise_sql``."""

    stack: tuple[StackFrame, ...]
    """The call stack shared by every record here, outermost first."""

    records: tuple[QueryRecord, ...]
    """Every execution on this path, in capture order. Always at least two."""

    @property
    def count(self) -> int:
        """How many times the statement ran. The N in N+1, near enough."""
        return len(self.records)

    @property
    def call_site(self) -> StackFrame | None:
        """The innermost frame outside Django: the line to go and look at.

        ``None`` when the stack reaches no such frame, which in practice means
        it was truncated below the caller. Reported rather than approximated,
        for the reason ``QueryRecord.call_site`` gives.
        """
        return innermost_frame_outside_django(self.stack)

    @property
    def aliases(self) -> tuple[str, ...]:
        """The connections this ran on, in the order they were first seen.

        Usually one. More than one means a single line queried more than one
        database, which the identity deliberately does not split on.
        """
        return tuple(dict.fromkeys(record.alias for record in self.records))

    @property
    def stack_truncated(self) -> bool:
        """``True`` when any execution here had frames dropped above the ones kept.

        ``any``, not "all of them equally", because the kept frames can match
        while the dropped ones did not: a recursive walk reaches the same line
        from a different depth each time.

        Not printed per finding by either report, and that is on purpose. Under
        a test runner this is true of every capture at any workable depth -- the
        dropped frames are the runner's own -- so a caveat on every line would
        say nothing on any of them. It is here for a reader who wants to know
        whether the window described above was full.
        """
        return any(record.stack_truncated for record in self.records)

    @property
    def first_index(self) -> int:
        """Position in the capture of the first execution on this path.

        The tie-break that makes an ordering by ``count`` total, so two runs
        over the same capture list findings in the same order.
        """
        return self.records[0].index
