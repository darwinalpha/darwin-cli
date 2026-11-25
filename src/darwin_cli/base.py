# src/darwin_cli/base.py

"""
Core data types for darwin-cli.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union


@dataclass
class ValidationRule:
    """Validation constraints for a parameter value."""

    choices: Optional[List[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    custom: Optional[str] = None


@dataclass
class Constraint:
    """A cross-parameter relationship rule.

    Supported rules (see constraints.py):
        mutually_exclusive  - at most one of ``params`` may be an explicit CLI arg
        together            - all of ``params`` must appear together, or none
        requires            - if ``param`` is explicit, ``requires`` must be explicit too
        exclusive_with      - ``param`` excludes every name in ``group``
        at_least_one        - at least one of ``params`` must be explicit
    """

    rule: str
    params: List[str] = field(default_factory=list)
    param: Optional[str] = None
    group: List[str] = field(default_factory=list)
    requires: Optional[str] = None
    message: Optional[str] = None
    include_generated: bool = False


@dataclass
class Param:
    """Static parameter declaration.

    Fields:
        name: parameter name, used on the command line as ``--name``
        type: "str" | "int" | "float" | "bool", or a ValidationRule (implies str)
        required: must be provided by the user or produced by an Action
        default: static value, or Callable[current_args] -> value
        help: static text, or Callable[current_args] -> text
        action: registered action name, or Callable(value, current_args) -> result
        validation: rule object when ``type`` is a string
        depends_on: names that must be processed before this parameter
        mutually_exclusive / together / at_least_one / exclusive_with /
        requires: optional one-to-one relations, each naming a single other
            parameter. They are compiled into ``Constraint`` objects at load
            time; group-level relations belong in the ``groups`` config section.
    """

    name: str
    type: Union[str, ValidationRule] = "str"
    required: bool = False
    default: Any = None
    help: Union[str, Callable] = ""
    action: Optional[Union[str, Callable]] = None
    validation: Optional[ValidationRule] = None
    depends_on: Optional[List[str]] = None
    mutually_exclusive: Optional[str] = None
    together: Optional[str] = None
    at_least_one: Optional[str] = None
    exclusive_with: Optional[str] = None
    requires: Optional[str] = None


@dataclass
class ParamInfo:
    """Runtime information for a parameter."""

    value: Any
    defined: bool = False
    from_source: str = "cli"  # cli | default | action
    processed: bool = False


@dataclass
class ActionResult:
    """Return value of an Action.

    values: values to add or overwrite
    params: new parameter definitions discovered at runtime
    """

    values: Dict[str, Any] = field(default_factory=dict)
    params: List[Param] = field(default_factory=list)


@dataclass
class CliResult:
    """Result of a CLI run.

    ``success``, ``error`` and ``exit_code`` are kept for backward compatibility.
    ``outcome`` gives an unambiguous three-way classification:
        "ok"    - parsed successfully
        "help"  - help was requested (exit_code 0, success False)
        "error" - validation / action / required failure (exit_code 1)
    """

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    exit_code: int = 0
    outcome: str = "ok"

    @classmethod
    def ok(cls, data: Dict[str, Any]) -> "CliResult":
        return cls(success=True, data=data, outcome="ok")

    @classmethod
    def help(cls) -> "CliResult":
        return cls(success=False, exit_code=0, outcome="help")

    @classmethod
    def fail(cls, error: str, exit_code: int = 1) -> "CliResult":
        return cls(success=False, error=error, exit_code=exit_code, outcome="error")
