"""How a call site reads, from real captures.

The block a reader acts on when nothing repeated. It is deliberately the same
shape as a finding's block -- count, then the line, then the statement -- so a
reader who has learned to read one has learned to read both.
"""

from __future__ import annotations

import os

import pytest

from django_query_contract import QueryCapture, format_attributions, group_by_call_site
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def authors() -> list[Author]:
    made = [Author.objects.create(name=f"a{index}") for index in range(3)]
    for author in made:
        Book.objects.create(author=author, title="b")
    return made


def test_the_call_site_comes_before_the_sql(authors: list[Author]) -> None:
    """A count with no address is the output people turn off.

    Same order as a finding's block, and for the same reason: the line somebody
    edits is the only part anybody acts on, so it goes above the statement.
    """
    with QueryCapture(using="default") as capture:
        for author in Author.objects.all():
            list(author.books.all())

    block = format_attributions(group_by_call_site(capture))
    lines = block.splitlines()
    assert lines[0].startswith("  3 x  from ")
    assert __file__ in lines[0] or "tests/test_format_attributions.py" in lines[0]
    assert '"testapp_book"."author_id" = %s' in lines[1]


def test_a_line_that_ran_several_shapes_is_counted_not_quoted(
    authors: list[Author],
) -> None:
    """One statement under one address is recognisable; five would bury the address.

    The count is what decides whether to go and look, which is the question a
    listing of call sites is being read to answer.
    """
    with QueryCapture(using="default") as capture:
        for model in (Author, Book):
            list(model.objects.filter(pk=1))

    (attribution,) = group_by_call_site(capture)
    assert "       2 statement shapes" in format_attributions([attribution])


def test_a_long_statement_is_cut_and_says_so(authors: list[Author]) -> None:
    """The records keep the whole statement; the block keeps the reader's attention."""
    with QueryCapture(using="default") as capture:
        list(Author.objects.all())

    attributions = group_by_call_site(capture)
    assert "... (truncated)" in format_attributions(attributions, max_sql=20)
    assert "... (truncated)" not in format_attributions(attributions, max_sql=10_000)


def test_a_call_site_under_the_working_directory_is_shortened(
    authors: list[Author], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the same helper a finding uses, so one report cannot spell one path twice."""
    monkeypatch.chdir(_REPO_ROOT)
    with QueryCapture(using="default") as capture:
        list(Author.objects.filter(pk=1))

    block = format_attributions(group_by_call_site(capture))
    assert "from tests/test_format_attributions.py:" in block


def test_a_call_site_outside_it_keeps_its_absolute_path(
    authors: list[Author], monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``os.path.relpath`` would walk out with a row of dot-dots, which is worse."""
    with QueryCapture(using="default") as capture:
        list(Author.objects.filter(pk=1))

    monkeypatch.chdir(tmp_path)
    block = format_attributions(group_by_call_site(capture))
    assert f"from {os.path.abspath(__file__)}:" in block


def test_an_unaddressed_group_names_both_ways_it_could_have_happened(
    authors: list[Author],
) -> None:
    """A finding can only be missing a call site one way; this can be missing it two.

    The detector never sees a stackless record, so a finding without a call site
    was always a window that did not reach far enough, and its block says so.
    Attribution groups every record it is handed, so the same group can hold
    statements that never had a stack at all. Naming one cause would be wrong
    half the time.
    """
    with QueryCapture(using="default", stack_depth=1) as capture:
        list(Author.objects.filter(pk=1))

    block = format_attributions(group_by_call_site(capture))
    assert "from no frame outside Django (an empty stack, or a window that did not reach one)" in (
        block
    )


def test_only_the_busiest_lines_are_named(authors: list[Author]) -> None:
    with QueryCapture(using="default") as capture:
        list(Author.objects.filter(pk=1))
        list(Author.objects.filter(pk=2))
        list(Author.objects.filter(pk=3))

    block = format_attributions(group_by_call_site(capture), max_sites=1)
    assert block.count("x  from ") == 1
    assert "and 2 more call site(s)." in block


def test_nothing_to_attribute_renders_nothing(authors: list[Author]) -> None:
    """Empty rather than a sentence, so a caller prints a heading only over a body.

    The two headings this can appear under both come from a caller that knows
    why it is printing, and neither wants an apology from the formatter when
    there is nothing to print.
    """
    assert format_attributions(()) == ""


@pytest.mark.django_db(databases=["default", "other"])
def test_a_line_spanning_two_connections_names_both() -> None:
    """Nothing else in the block would say so: the key is the line, not the alias."""
    with QueryCapture() as capture:
        for alias in ("default", "other"):
            list(Author.objects.using(alias).filter(pk=1))

    block = format_attributions(group_by_call_site(capture))
    assert "       across connections 'default', 'other'" in block


def test_a_line_on_one_connection_does_not_mention_it(authors: list[Author]) -> None:
    """The common case stays two lines; the capture report already counts per alias."""
    with QueryCapture(using="default") as capture:
        list(Author.objects.filter(pk=1))

    assert "across connections" not in format_attributions(group_by_call_site(capture))
