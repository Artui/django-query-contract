from __future__ import annotations

from enum import Enum


class PlanDefect(Enum):
    """What a plan finding accuses, and there are only two because only two qualify."""

    PLANNER_BLIND = "planner blind"
    """One statement shape, one estimate, and more than one truth.

    Two or more executions of the same normalised SQL whose plans agree exactly
    on how many rows the query would produce, and whose measured rows do not.
    The planner cannot tell those executions apart; the data can. There is no
    threshold in that sentence -- only ``==`` and ``!=`` -- and it is the defect
    the shaped-database dependency exists for.

    Measured on a Zipf fan-out of 400,000 rows over 20,000 parents, joined
    through the parent rather than through the foreign key column: a whale and a
    tail row both estimated at **20** rows, against actuals of **20,323** and
    **6**. Across a join PostgreSQL has only ``n_distinct`` for the edge, so it
    hands every value of the join key the same average, and the average is the
    one number that is wrong for both ends of a skewed distribution.

    **The identity is the fingerprint alone, and deliberately not the call
    stack.** That is the opposite choice from
    :class:`~django_query_contract.NPlusOne`, and the rule behind both is the
    same one: a finding is keyed on what the thing being accused can actually
    see. An N+1 accuses your code, so it is keyed on your code's call path. This
    accuses the planner, which is handed a statement and never hears about the
    stack, so keying on the stack would split one blind spot into one finding per
    line that happened to reach it.
    """

    SPILLED_TO_DISK = "spilled to disk"
    """A sort, hash join or hash aggregate that did not fit in ``work_mem``.

    PostgreSQL says so itself -- ``Sort Space Type: Disk``, more than one hash
    batch, or a hash aggregate reporting disk usage -- so the threshold is
    ``work_mem``, which is the configuration of the database under test and not
    a number chosen here.

    That is also its limitation, stated rather than glossed: it is as much a
    finding about the server as about the query, and a suite whose CI database
    is configured differently from production will find different ones. Nothing
    in this package fails a test on it.
    """
