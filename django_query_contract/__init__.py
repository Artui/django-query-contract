"""A query-capture engine for Django, and a pytest plugin over it."""

from django_query_contract.assert_query_growth import assert_query_growth
from django_query_contract.attribution import Attribution
from django_query_contract.capture_stack import capture_stack
from django_query_contract.find_n_plus_one import find_n_plus_one
from django_query_contract.find_plan_defects import find_plan_defects
from django_query_contract.format_attributions import format_attributions
from django_query_contract.format_capture_report import format_capture_report
from django_query_contract.format_n_plus_one import format_n_plus_one
from django_query_contract.format_n_plus_one_summary import format_n_plus_one_summary
from django_query_contract.format_query_growth import format_query_growth
from django_query_contract.format_query_plans import format_query_plans
from django_query_contract.group_by_call_site import group_by_call_site
from django_query_contract.growth import Growth
from django_query_contract.growth_point import GrowthPoint
from django_query_contract.log_ceiling import LogCeiling
from django_query_contract.measure_query_growth import measure_query_growth
from django_query_contract.n_plus_one import NPlusOne
from django_query_contract.normalise_sql import normalise_sql
from django_query_contract.plan_capture import PlanCapture
from django_query_contract.plan_defect import PlanDefect
from django_query_contract.plan_finding import PlanFinding
from django_query_contract.plan_node import PlanNode
from django_query_contract.plans_unsupported import PlansUnsupported
from django_query_contract.query_capture import QueryCapture
from django_query_contract.query_growth import QueryGrowth
from django_query_contract.query_log_ceiling_warning import QueryLogCeilingWarning
from django_query_contract.query_plan import QueryPlan
from django_query_contract.query_record import QueryRecord
from django_query_contract.stack_frame import StackFrame
from django_query_contract.version import __version__

__all__ = [
    "Attribution",
    "Growth",
    "GrowthPoint",
    "LogCeiling",
    "NPlusOne",
    "PlanCapture",
    "PlanDefect",
    "PlanFinding",
    "PlanNode",
    "PlansUnsupported",
    "QueryCapture",
    "QueryGrowth",
    "QueryLogCeilingWarning",
    "QueryPlan",
    "QueryRecord",
    "StackFrame",
    "__version__",
    "assert_query_growth",
    "capture_stack",
    "find_n_plus_one",
    "find_plan_defects",
    "format_attributions",
    "format_capture_report",
    "format_n_plus_one",
    "format_n_plus_one_summary",
    "format_query_growth",
    "format_query_plans",
    "group_by_call_site",
    "measure_query_growth",
    "normalise_sql",
]
