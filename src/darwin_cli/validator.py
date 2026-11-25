# src/darwin_cli/validator.py

"""
Value validator: type conversion, rule checks and custom validators.
"""

import re
from typing import Any, Callable, Dict, List, Optional

from darwin_cli.actions import ActionError
from darwin_cli.base import Param, ValidationRule

TRUE_VALUES = ("true", "1", "yes", "on", "t")
FALSE_VALUES = ("false", "0", "no", "off", "f")


class Validator:
    """Validate and coerce a single parameter value."""

    def __init__(self, params: Optional[List[Param]] = None):
        # ``params`` is accepted for API compatibility but intentionally not
        # stored: each value is validated against the Param passed to
        # validate_one, which also covers parameters discovered at runtime.
        self._custom_validators: Dict[str, Callable] = {}

    def register_custom(self, name: str, func: Callable) -> None:
        self._custom_validators[name] = func

    def validate_one(self, param: Param, value: Any) -> Any:
        if value is None and not param.required:
            return value

        param_type, validation = self._resolve_type_and_validation(param)
        value = self._validate_type(param, param_type, value)
        value = self._validate_rules(param, validation, value)
        value = self._validate_custom(param, validation, value)
        return value

    def _resolve_type_and_validation(self, param: Param) -> tuple:
        if isinstance(param.type, ValidationRule):
            return "str", param.type
        return param.type, param.validation

    def _validate_type(self, param: Param, type_name: str, value: Any) -> Any:
        if value is None:
            return value

        type_map = {"str": str, "int": int, "float": float, "bool": bool}
        expected_type = type_map.get(type_name)
        if expected_type is None:
            return value

        if type_name == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lower = value.lower()
                if lower in TRUE_VALUES:
                    return True
                if lower in FALSE_VALUES:
                    return False
            raise ActionError(
                f"Parameter '{param.name}' type error: expected bool, "
                f"got {type(value).__name__}, value: {value}"
            )

        try:
            return expected_type(value)
        except (ValueError, TypeError):
            raise ActionError(
                f"Parameter '{param.name}' type error: expected {type_name}, "
                f"got {type(value).__name__}, value: {value}"
            )

    def _validate_rules(
        self,
        param: Param,
        validation: Optional[ValidationRule],
        value: Any,
    ) -> Any:
        if value is None or validation is None:
            return value

        if validation.choices is not None and value not in validation.choices:
            choices_str = ", ".join(str(c) for c in validation.choices)
            raise ActionError(
                f"Parameter '{param.name}' value '{value}' is not in choices: [{choices_str}]"
            )

        if isinstance(value, (int, float)):
            if validation.min is not None and value < validation.min:
                raise ActionError(
                    f"Parameter '{param.name}' value {value} is below minimum {validation.min}"
                )
            if validation.max is not None and value > validation.max:
                raise ActionError(
                    f"Parameter '{param.name}' value {value} is above maximum {validation.max}"
                )

        if isinstance(value, str):
            if validation.min_length is not None and len(value) < validation.min_length:
                raise ActionError(
                    f"Parameter '{param.name}' length {len(value)} is below minimum "
                    f"{validation.min_length}"
                )
            if validation.max_length is not None and len(value) > validation.max_length:
                raise ActionError(
                    f"Parameter '{param.name}' length {len(value)} is above maximum "
                    f"{validation.max_length}"
                )
            if validation.pattern is not None and not re.match(validation.pattern, value):
                raise ActionError(
                    f"Parameter '{param.name}' value '{value}' does not match pattern: "
                    f"{validation.pattern}"
                )

        return value

    def _validate_custom(
        self,
        param: Param,
        validation: Optional[ValidationRule],
        value: Any,
    ) -> Any:
        if value is None or validation is None or validation.custom is None:
            return value

        name = validation.custom
        if name not in self._custom_validators:
            raise ActionError(f"Custom validator '{name}' is not registered (param: {param.name})")

        func = self._custom_validators[name]
        try:
            result = func(value)
        except Exception as e:
            raise ActionError(f"Parameter '{param.name}' custom validation failed: {e}")
        return result if result is not None else value


def create_validator(
    params: Optional[List[Param]] = None,
    custom_validators: Optional[Dict[str, Callable]] = None,
) -> Validator:
    validator = Validator(params)
    for name, func in (custom_validators or {}).items():
        validator.register_custom(name, func)
    return validator
