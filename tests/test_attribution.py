"""The attribution, and the four questions it answers about itself.

Records are built by hand here rather than captured, for the reason
``test_n_plus_one.py`` gives about its own subject: these are the properties of
a value, and a real capture cannot be steered into every shape one can hold.
``test_group_by_call_site.py`` does the opposite -- every capture there is real
-- so the grouping rule and the value it produces are each covered against
something that can disagree with them.
"""

from __future__ import annotations

from django_query_contract import Attribution, QueryRecord, StackFrame

_CALLER = StackFrame(filename="/app/views.py", lineno=112, function="render")


def _record(index: int, **overrides: object) -> QueryRecord:
    fields: dict[str, object] = {
        "index": index,
        "sql": "SELECT 1",
        "fingerprint": "SELECT %s",
        "alias": "default",
        "vendor": "sqlite",
        "many": False,
        "param_count": None,
        "stack": (_CALLER,),
    }
    fields.update(overrides)
    return QueryRecord(**fields)


def _attribution(*records: QueryRecord, call_site: StackFrame | None = _CALLER) -> Attribution:
    return Attribution(call_site=call_site, records=records)


def test_the_count_is_how_many_statements_the_line_emitted() -> None:
    assert _attribution(_record(0), _record(1), _record(2)).count == 3


def test_the_shapes_are_named_in_the_order_they_appeared() -> None:
    """A line is allowed more than one shape, and that is the point.

    A finding is one statement shape by definition. An attribution is one
    *line*, and a line that evaluates a queryset carrying a related object
    emits several. Deduplicated and ordered, so a report is stable rather than
    however a set happened to iterate.
    """
    attribution = _attribution(
        _record(0, fingerprint="SELECT b"),
        _record(1, fingerprint="SELECT a"),
        _record(2, fingerprint="SELECT b"),
    )
    assert attribution.fingerprints == ("SELECT b", "SELECT a")


def test_the_aliases_are_named_in_the_order_they_appeared() -> None:
    """The group is keyed on the line and says nothing about the connection.

    Same shape as a finding's ``aliases`` and for the same reason: one line
    querying two databases is one line, so the span is reported rather than
    encoded in the key.
    """
    attribution = _attribution(
        _record(0, alias="other"),
        _record(1, alias="default"),
        _record(2, alias="other"),
    )
    assert attribution.aliases == ("other", "default")


def test_the_first_index_is_where_the_line_started() -> None:
    """The tie-break that makes ordering by count a total order."""
    assert _attribution(_record(4), _record(9)).first_index == 4


def test_a_group_with_no_call_site_is_still_a_group() -> None:
    """The one group that has no address, and it is a value like any other.

    Records with no stack at all, and records whose kept frames were all
    Django's own, land here. They are kept rather than dropped so that the
    statements in a capture and the statements in its attribution add up.
    """
    attribution = _attribution(_record(0, stack=()), _record(1, stack=()), call_site=None)
    assert attribution.call_site is None
    assert attribution.count == 2
