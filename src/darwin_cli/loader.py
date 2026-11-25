# src/darwin_cli/loader.py

"""
Config-dict conversion helpers and constraint parsing.
"""

from typing import Any, Callable, Dict, List, Optional, Union

from darwin_cli.base import Constraint, Param, ValidationRule

# ============================================================
# Helpers
# ============================================================


def _is_valid_help(value: Any) -> bool:
    return isinstance(value, str) or callable(value)


def _is_valid_action(value: Any) -> bool:
    return isinstance(value, str) or callable(value)


def _callable_name(func: Callable) -> str:
    if hasattr(func, "__name__"):
        return func.__name__
    if hasattr(func, "__class__"):
        return func.__class__.__name__
    return "unknown"


# ============================================================
# Param conversion
# ============================================================


def parse_params_from_config(config: Dict[str, Dict[str, Any]]) -> List[Param]:
    """Convert a config dict into Param objects.

    Config format::

        {
            "param_name": {
                "type": "str",                 # or ValidationRule, or rule dict
                "required": true,
                "default": "value",            # or Callable
                "help": "description",         # or Callable
                "action": "action_name",       # or Callable
                "depends_on": ["other"],
                "validation": {"min": 1, "max": 100}
            }
        }
    """
    return [_parse_single_param(name, definition) for name, definition in config.items()]


def _parse_single_param(name: str, definition: Dict[str, Any]) -> Param:
    param_type, validation = _parse_type_and_validation(definition)

    help_value = definition.get("help", "")
    if not _is_valid_help(help_value):
        help_value = str(help_value) if help_value is not None else ""

    action_value = definition.get("action")
    if action_value is not None and not _is_valid_action(action_value):
        raise ValueError(
            f"Action of parameter '{name}' must be str or Callable, got {type(action_value)}"
        )

    default_value = definition.get("default")

    depends_on = definition.get("depends_on")
    if depends_on is not None:
        if not isinstance(depends_on, list):
            raise ValueError(f"depends_on of '{name}' must be a list, got {type(depends_on)}")
        if not all(isinstance(d, str) for d in depends_on):
            raise ValueError(f"depends_on of '{name}' must contain only strings")

    return Param(
        name=name,
        type=param_type,
        required=definition.get("required", False),
        default=default_value,
        help=help_value,
        action=action_value,
        validation=validation,
        depends_on=depends_on,
    )


def _parse_type_and_validation(definition: Dict[str, Any]) -> tuple:
    raw_type = definition.get("type", "str")
    raw_validation = definition.get("validation")

    if isinstance(raw_type, dict):
        return _to_validation_rule(raw_type), None
    if isinstance(raw_type, ValidationRule):
        return raw_type, None
    if isinstance(raw_type, str):
        validation_rule: Optional[ValidationRule] = None
        if raw_validation is not None:
            if isinstance(raw_validation, dict):
                validation_rule = _to_validation_rule(raw_validation)
            elif isinstance(raw_validation, ValidationRule):
                validation_rule = raw_validation
        return raw_type, validation_rule
    return "str", None


def _to_validation_rule(data: Union[Dict[str, Any], ValidationRule]) -> ValidationRule:
    if isinstance(data, ValidationRule):
        return data
    if not isinstance(data, dict):
        raise ValueError(f"Cannot convert to ValidationRule: {data}")
    return ValidationRule(
        choices=data.get("choices"),
        min=data.get("min"),
        max=data.get("max"),
        min_length=data.get("min_length"),
        max_length=data.get("max_length"),
        pattern=data.get("pattern"),
        custom=data.get("custom"),
    )


# ============================================================
# Constraint conversion
# ============================================================

KNOWN_RULES = {
    "mutually_exclusive",
    "together",
    "requires",
    "exclusive_with",
    "at_least_one",
}


def parse_constraints(config: List[Union[Dict[str, Any], Constraint]]) -> List[Constraint]:
    """Convert a list of constraint dicts into Constraint objects.

    Supported forms::

        {"rule": "mutually_exclusive", "params": ["date", "year"]}
        {"rule": "together", "params": ["user", "password"]}
        {"rule": "requires", "param": "type", "requires": "source"}
        {"rule": "exclusive_with", "param": "date", "group": ["start_date", "end_date"]}
        {"rule": "at_least_one", "params": ["source", "file"]}

    An optional ``message`` overrides the default English error message.
    An optional ``include_generated`` (default ``False``) also counts values
    produced by Actions when checking the rule.
    """
    result: List[Constraint] = []
    for item in config or []:
        if isinstance(item, Constraint):
            result.append(item)
            continue
        if not isinstance(item, dict):
            raise ValueError(f"Constraint must be a dict or Constraint, got {type(item)}")

        rule = item.get("rule")
        if rule not in KNOWN_RULES:
            raise ValueError(
                f"Unknown constraint rule '{rule}'. Expected one of: {sorted(KNOWN_RULES)}"
            )

        result.append(
            Constraint(
                rule=rule,
                params=list(item.get("params") or []),
                param=item.get("param"),
                group=list(item.get("group") or []),
                requires=item.get("requires"),
                message=item.get("message"),
                include_generated=bool(item.get("include_generated", False)),
            )
        )
    return result


# ============================================================
# Convenience helpers
# ============================================================


def get_param_by_name(params: List[Param], name: str) -> Optional[Param]:
    for p in params:
        if p.name == name:
            return p
    return None


def merge_params(base: List[Param], override: List[Param]) -> List[Param]:
    """Merge two lists; same-name entries in override win."""
    param_map = {p.name: p for p in base}
    for p in override:
        param_map[p.name] = p
    return list(param_map.values())


def params_to_dict(params: List[Param]) -> Dict[str, Dict[str, Any]]:
    """Serialize params for debugging. Callables become placeholder strings."""
    result: Dict[str, Dict[str, Any]] = {}
    for p in params:
        definition: Dict[str, Any] = {}
        if isinstance(p.type, ValidationRule):
            definition["type"] = _validation_rule_to_dict(p.type)
        else:
            definition["type"] = p.type
        if p.required:
            definition["required"] = True
        if p.default is not None:
            definition["default"] = (
                f"<Callable: {_callable_name(p.default)}>"
                if callable(p.default)
                else p.default
            )
        if p.help:
            definition["help"] = (
                f"<Callable: {_callable_name(p.help)}>" if callable(p.help) else p.help
            )
        if p.action:
            definition["action"] = (
                f"<Callable: {_callable_name(p.action)}>" if callable(p.action) else p.action
            )
        if p.validation:
            definition["validation"] = _validation_rule_to_dict(p.validation)
        if p.depends_on:
            definition["depends_on"] = p.depends_on
        result[p.name] = definition
    return result


def _validation_rule_to_dict(rule: ValidationRule) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in (
        "choices",
        "min",
        "max",
        "min_length",
        "max_length",
        "pattern",
        "custom",
    ):
        value = getattr(rule, key)
        if value is not None:
            result[key] = value
    return result
