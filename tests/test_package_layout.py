"""The package root is a table of contents, not a drawer.

The other structural rules in ``CLAUDE.md`` all govern a *file* -- one exported
symbol, a ``snake_case`` name, top-level imports -- and a package can obey every
one of them while putting all thirty-eight of its modules in one directory,
which is what this one did. A rule that only exists as prose is obeyed exactly
as far as somebody remembers it, so it is a test instead.

Two assertions, because the flat root has two ways back. The first is the
allowlist: a new module lands at the root because that is where the last one
was, and nothing objects. The second is the collision: once a name is free to
appear at the root *and* inside a subpackage, the same concern grows a copy in
both -- ``django-domain-events`` grew ``catalogue`` and ``outbox_health`` twice
each that way -- and the two drift without ever disagreeing loudly.
"""

from __future__ import annotations

from pathlib import Path

import django_query_contract

_PACKAGE = Path(django_query_contract.__file__).resolve().parent

# Everything on this list is here because it cannot be anywhere else, and the
# reason is written beside it. Adding a name here is a structural decision;
# adding a module to a subpackage is not, which is the asymmetry the rule wants.
_ALLOWED_ROOT_MODULES = frozenset(
    {
        # The single re-export point. Holds no logic.
        "__init__",
        # Read by hatchling's version hook through a path in ``pyproject.toml``.
        "version",
        # What more than one subpackage must agree on: the stack depth, the
        # scale factors, and the two frame walks. Named by the shared standard.
        "utils",
        # pytest discovers hooks by *name in a module*, so there is nowhere else
        # to put them. It stays thin and delegates everything testable.
        "plugin",
    }
)


def _root_modules() -> set[str]:
    return {path.stem for path in _PACKAGE.glob("*.py")}


def _subpackages() -> dict[str, set[str]]:
    return {
        directory.name: {path.stem for path in directory.glob("*.py")} - {"__init__"}
        for directory in sorted(_PACKAGE.iterdir())
        if directory.is_dir() and (directory / "__init__.py").exists()
    }


def test_the_package_being_measured_is_the_one_in_this_repository() -> None:
    # Both tests below discover their own inputs, and a test that discovers its
    # own inputs passes by finding nothing. This is what makes them honest.
    assert (_PACKAGE.parent / "pyproject.toml").exists()
    assert len(_subpackages()) >= 5


def test_the_root_holds_only_the_allowlisted_modules() -> None:
    """Everything the package actually *does* lives in a subpackage."""
    unexpected = _root_modules() - _ALLOWED_ROOT_MODULES

    assert not unexpected, (
        f"{sorted(unexpected)} sit at the package root. A module that does "
        f"something belongs in a subpackage named for its concern; see rule 7 "
        f"in CLAUDE.md. If it genuinely cannot live anywhere else, add it to "
        f"_ALLOWED_ROOT_MODULES with the reason."
    )


def test_no_name_is_used_both_at_the_root_and_inside_a_subpackage() -> None:
    """A name free to appear twice eventually does, and the copies drift."""
    root_names = _root_modules() | set(_subpackages())

    collisions = {
        f"{package}/{module}.py"
        for package, modules in _subpackages().items()
        for module in modules
        if module in root_names
    }

    assert not collisions, (
        f"{sorted(collisions)} each share a name with something at the package "
        f"root, so ``django_query_contract.<name>`` means two things."
    )
