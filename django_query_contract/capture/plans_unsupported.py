"""The refusal raised when a plan could not mean anything."""

from __future__ import annotations


class PlansUnsupported(Exception):
    """Plan capture was asked for on a connection that cannot produce a plan.

    Raised by :class:`~django_query_contract.PlanCapture` on entry, before a
    single statement has run, and carrying the sentence that names what was
    refused, which connection, and what that connection actually is.

    **It raises rather than degrading, and that is the whole point of the class.**
    Every other honest degradation in this package reports and carries on: a
    capture rebuilt from a ``CaptureQueriesContext`` says it has no stacks, a
    block above the query-log ceiling says the count is wrong. Those are still
    measurements. A plan capture on SQLite would not be a degraded measurement,
    it would be an empty one, and an empty one is indistinguishable from a
    healthy one -- so an assertion over it passes because the backend could not
    check it, which is the exact failure this package exists to expose.

    The pytest face turns this into a **skip** rather than an error, through the
    ``query_plans`` fixture: a test that never ran is honest, and a test that ran
    against a database with no planner is not.
    """
