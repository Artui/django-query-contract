"""The kinds of plan defect this package is willing to name."""

from __future__ import annotations

from enum import Enum


class PlanDefect(Enum):
    """What a plan finding accuses, and there are only two because only two qualify.

    **A finding here holds by construction, exactly as an N+1 does.** The plan
    that produced this package listed four candidates: sequential scans over a
    row threshold, nested loops with a large inner, sorts spilling to disk, and
    planner estimates off by orders of magnitude from actual. Two of them are
    numbers wearing a description -- *how many* rows makes a sequential scan
    wrong, *how* large an inner is large -- and a number is a knob. The four dead
    N+1 detectors on PyPI are what a package of knobs looks like a few years
    later, so both are declined here rather than shipped with a default nobody
    would agree with.

    The two that survived did so for different reasons, and the difference is
    worth keeping in view:

    - a spill is a fact **PostgreSQL asserts**, using a threshold of its own
      (``work_mem``) that belongs to the database rather than to this package;
    - blindness is a fact about **a pair of measurements**, decided by equality
      and inequality, with no magnitude anywhere in it.

    The estimate-versus-actual ratio itself is not here, and its absence is the
    design rather than an omission. It is on every node as
    :attr:`~django_query_contract.PlanNode.estimate_error`, ordered by the
    report and read by a person: "the planner expected 20 and 20,323 arrived" is
    a fact, while "more than fifty times out is a defect" is a policy about
    size. This package reports the first and refuses to write the second.
    """

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
