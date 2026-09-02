"""A query-capture engine for Django, and a pytest plugin over it."""

from django_query_lens.capture_stack import capture_stack
from django_query_lens.format_capture_report import format_capture_report
from django_query_lens.log_ceiling import LogCeiling
from django_query_lens.normalise_sql import normalise_sql
from django_query_lens.query_capture import QueryCapture
from django_query_lens.query_log_ceiling_warning import QueryLogCeilingWarning
from django_query_lens.query_record import QueryRecord
from django_query_lens.stack_frame import StackFrame
from django_query_lens.version import __version__

__all__ = [
    "LogCeiling",
    "QueryCapture",
    "QueryLogCeilingWarning",
    "QueryRecord",
    "StackFrame",
    "__version__",
    "capture_stack",
    "format_capture_report",
    "normalise_sql",
]
