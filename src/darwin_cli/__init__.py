# src/darwin_cli/__init__.py

"""
darwin-cli

Declaration-driven CLI engine: parameters can compute values, infer other
parameters and generate new parameter definitions at runtime. Supports
config-file driven parameter declarations and cross-parameter constraints.

Zero third-party dependencies.
"""

from darwin_cli.actions import (
    ACTION_REGISTRY,
    GLOBAL_ACTIONS,
    ActionError,
    ActionRegistry,
    ConflictError,
    ConstraintError,
    CycleDetected,
    HelpRequested,
    MaxIterationsExceeded,
    RequiredError,
    clear_actions,
    get_action,
    has_action,
    list_actions,
    load_actions_from_file,
    load_actions_from_module,
    register_action,
    validate_before,
)
from darwin_cli.app import CliApp
from darwin_cli.base import (
    ActionResult,
    CliResult,
    Constraint,
    Param,
    ParamInfo,
    ValidationRule,
)
from darwin_cli.constraints import check_constraint, check_constraints
from darwin_cli.loader import (
    KNOWN_PARAM_KEYS,
    RELATION_RULES,
    compile_constraints,
    get_param_by_name,
    merge_params,
    param_definitions_from_objects,
    params_to_dict,
    parse_constraints,
    parse_params_from_config,
    resolve_groups,
    validate_param_definitions,
)
from darwin_cli.parser import build_parser, parse_args_with_meta
from darwin_cli.validator import Validator, create_validator

__version__ = "0.3.0"

__all__ = [
    # core
    "CliApp",
    "Param",
    "ParamInfo",
    "ValidationRule",
    "Constraint",
    "ActionResult",
    "CliResult",
    # registry
    "ActionRegistry",
    "GLOBAL_ACTIONS",
    "ACTION_REGISTRY",
    "register_action",
    "get_action",
    "has_action",
    "list_actions",
    "clear_actions",
    "validate_before",
    "load_actions_from_module",
    "load_actions_from_file",
    # config helpers
    "parse_params_from_config",
    "parse_constraints",
    "compile_constraints",
    "resolve_groups",
    "validate_param_definitions",
    "param_definitions_from_objects",
    "KNOWN_PARAM_KEYS",
    "RELATION_RULES",
    "merge_params",
    "params_to_dict",
    "get_param_by_name",
    # constraints
    "check_constraint",
    "check_constraints",
    # lower-level
    "parse_args_with_meta",
    "build_parser",
    "Validator",
    "create_validator",
    # exceptions
    "ActionError",
    "ConflictError",
    "ConstraintError",
    "CycleDetected",
    "HelpRequested",
    "MaxIterationsExceeded",
    "RequiredError",
    "__version__",
]
