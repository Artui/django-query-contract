"""One call site, and every statement that entered the database from it."""

from __future__ import annotations

from dataclasses import dataclass

from django_query_contract.query_record import QueryRecord
from django_query_contract.stack_frame import StackFrame


@dataclass(frozen=True, slots=True)
class Attribution:
    """Every statement one line of code emitted, and that line.

    **Attribution asks a different question from detection, so it groups by a
    different key**, and that difference is the whole reason this type exists
    beside :class:`~django_query_contract.NPlusOne` rather than inside it.

    A finding asks *what is one defect*. Its identity is the whole call stack,
    because two callers of one ``get_books(author)`` helper are two defects with
    two fixes, and the helper's own line is the one line that is fine.

    An attribution asks *where did these statements come from*. For those same
    two callers the honest answer is the helper's line: that is where the
    statements were emitted, and both call paths really did emit them there.

    So this deliberately merges what a finding keeps apart, and that is safe
    **only** because it claims nothing about defects. A group of forty is not a
    finding of forty; it is forty statements and an address. Nothing here fails
    a test, nothing here says a loop was found, and nothing here is a rule about
    which repetitions count -- which is what makes the merge a convenience
    rather than the first tunable.

    **The call site is a display rule, and it stays one.** It is picked by the
    single rule the whole package shares -- the innermost frame that is not
    inside Django, see :attr:`~django_query_contract.QueryRecord.call_site` --
    so a record, a finding and an attribution can never disagree about where a
    statement came from. That rule decides what is *printed*. It is not part of
    any identity, and the reason it must not become part of one is written out
    at :class:`~django_query_contract.NPlusOne`.

    ``call_site`` is ``None`` for the one group that has no address: records
    with no stack at all -- everything in a capture rebuilt from a
    ``CaptureQueriesContext`` -- and records whose kept frames were all Django's
    own. They are grouped rather than dropped, so the statements in a capture
    and the statements in its attribution always add up. An attribution that
    quietly lost the ones it could not place would be the silently incomplete
    measurement this package exists to complain about.
    """

    call_site: StackFrame | None
    """The line that emitted every statement here. ``None`` when there was none to name."""

    records: tuple[QueryRecord, ...]
    """Every statement from that line, in capture order. Always at least one."""

    @property
    def count(self) -> int:
        """How many statements this line emitted."""
        return len(self.records)

    @property
    def fingerprints(self) -> tuple[str, ...]:
        """The distinct statement shapes emitted here, in the order first seen.

        More than one is ordinary: a line that evaluates a queryset with a
        related object on it emits several shapes. It is also the other half of
        why an attribution is not a finding -- a finding is one shape by
        definition, and this can hold as many as the line produced.
        """
        return tuple(dict.fromkeys(record.fingerprint for record in self.records))

    @property
    def aliases(self) -> tuple[str, ...]:
        """The connections these ran on, in the order they were first seen.

        Usually one. More than one means a single line queried more than one
        database, which is worth printing because nothing else in the group
        would say so.
        """
        return tuple(dict.fromkeys(record.alias for record in self.records))

    @property
    def first_index(self) -> int:
        """Position in the capture of the first statement from this line.

        The tie-break that makes an ordering by ``count`` total, so two runs
        over one capture list the same attributions in the same order.
        """
        return self.records[0].index
