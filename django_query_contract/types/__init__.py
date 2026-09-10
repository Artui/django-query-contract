"""The value shapes a capture is made of, and the findings read back out of it.

Carriers only: a dataclass or an enum, its invariants, and the arithmetic that
reads its own fields. Nothing here opens a connection, walks a stack or renders
a line, so a consumer can build one by hand to test its own report.

Re-exported from the package root rather than from here, because
``django_query_contract/__init__.py`` is the only re-export point in this
package -- and because ``types.growth_point`` reads a ``QueryCapture``, so a
re-export here would put a cycle between two subpackages one import away.
"""
