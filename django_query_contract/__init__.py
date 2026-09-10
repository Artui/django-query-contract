"""A query-capture engine for Django, and a pytest plugin over it."""

from django_query_contract.analysis.assert_query_growth import assert_query_growth
from django_query_contract.analysis.find_n_plus_one import find_n_plus_one
from django_query_contract.analysis.find_plan_defects import find_plan_defects
from django_query_contract.analysis.group_by_call_site import group_by_call_site
from django_query_contract.analysis.group_by_relation import group_by_relation
from django_query_contract.analysis.measure_query_growth import measure_query_growth
from django_query_contract.capture.normalise_sql import normalise_sql
from django_query_contract.capture.plan_capture import PlanCapture
from django_query_contract.capture.plans_unsupported import PlansUnsupported
from django_query_contract.capture.query_capture import QueryCapture
from django_query_contract.capture.query_log_ceiling_warning import QueryLogCeilingWarning
from django_query_contract.reporting.format_attributions import format_attributions
from django_query_contract.reporting.format_capture_report import format_capture_report
from django_query_contract.reporting.format_n_plus_one import format_n_plus_one
from django_query_contract.reporting.format_n_plus_one_summary import format_n_plus_one_summary
from django_query_contract.reporting.format_query_growth import format_query_growth
from django_query_contract.reporting.format_query_plans import format_query_plans
from django_query_contract.reporting.format_relation_access import format_relation_access
from django_query_contract.source_location.capture_stack import capture_stack
from django_query_contract.source_location.in_project_tree import in_project_tree
from django_query_contract.source_location.relative_to_cwd import relative_to_cwd
from django_query_contract.types.attribution import Attribution
from django_query_contract.types.growth import Growth
from django_query_contract.types.growth_point import GrowthPoint
from django_query_contract.types.log_ceiling import LogCeiling
from django_query_contract.types.n_plus_one import NPlusOne
from django_query_contract.types.plan_defect import PlanDefect
from django_query_contract.types.plan_finding import PlanFinding
from django_query_contract.types.plan_node import PlanNode
from django_query_contract.types.query_growth import QueryGrowth
from django_query_contract.types.query_plan import QueryPlan
from django_query_contract.types.query_record import QueryRecord
from django_query_contract.types.relation_access import RelationAccess
from django_query_contract.types.stack_frame import StackFrame
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
    "RelationAccess",
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
    "format_relation_access",
    "group_by_call_site",
    "group_by_relation",
    "in_project_tree",
    "measure_query_growth",
    "normalise_sql",
    "relative_to_cwd",
]
