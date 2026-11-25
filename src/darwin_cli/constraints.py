# src/darwin_cli/constraints.py

"""
Cross-parameter constraint engine.

Rules are checked against CLI-provided parameters only (``from_source == "cli"``)
by default, so values produced by Actions (e.g. date -> start_date/end_date)
never trigger a false conflict. Pass ``include_generated=True`` on a Constraint
via config if a rule must also consider Action-produced values.
"""

from typing import Any, Dict, Iterable, List

from darwin_cli.actions import ConstraintError
from darwin_cli.base import Constraint, ParamInfo

# ============================================================
# Source selection
# ============================================================


def _is_explicit(info: ParamInfo, include_generated: bool = False) -> bool:
    """Whether a value counts as user-provided for constraint checking."""
    if info is None or info.value is None:
        return False
    if info.from_source == "cli":
        return True
    if include_generated and info.from_source == "action":
        return True
    return False


def _names_in(
    names: Iterable[str],
    current_args: Dict[str, ParamInfo],
    include_generated: bool = False,
) -> List[str]:
    return [name for name in names if _is_explicit(current_args.get(name), include_generated)]


# ============================================================
# Default English messages
# ============================================================


def _default_message(constraint: Constraint, given: List[str], missing: List[str]) -> str:
    rule = constraint.rule
    if rule == "mutually_exclusive":
        return f"Parameters {given} are mutually exclusive; provide at most one"
    if rule == "together":
        return f"Parameters {missing} must be provided together with {constraint.params}"
    if rule == "requires":
        return f"Parameter --{constraint.param} requires --{constraint.requires}"
    if rule == "exclusive_with":
        return f"Parameter --{constraint.param} is exclusive with {given}"
    if rule == "at_least_one":
        return f"At least one of {constraint.params} must be provided"
    return f"Constraint '{rule}' violated"


# ============================================================
# Single rule evaluation
# ============================================================


def check_constraint(
    constraint: Constraint,
    current_args: Dict[str, ParamInfo],
) -> None:
    """Raise ConstraintError if ``constraint`` is violated."""
    include_generated = bool(getattr(constraint, "include_generated", False))

    given = _names_in(constraint.params, current_args, include_generated)
    violation: List[str] = []
    missing: List[str] = []

    if constraint.rule == "mutually_exclusive":
        if len(given) > 1:
            violation = given

    elif constraint.rule == "together":
        if given and len(given) < len(constraint.params):
            missing = [p for p in constraint.params if p not in given]

    elif constraint.rule == "requires":
        if (
            constraint.param
            and _is_explicit(current_args.get(constraint.param), include_generated)
            and not _is_explicit(current_args.get(constraint.requires), include_generated)
        ):
            missing = [constraint.requires]

    elif constraint.rule == "exclusive_with":
        if constraint.param and _is_explicit(
            current_args.get(constraint.param), include_generated
        ):
            others = _names_in(constraint.group, current_args, include_generated)
            if others:
                violation = [constraint.param] + others

    elif constraint.rule == "at_least_one":
        if not given:
            missing = list(constraint.params)

    if violation or missing:
        message = constraint.message or _default_message(constraint, violation, missing)
        raise ConstraintError(
            message,
            violations=[
                {
                    "rule": constraint.rule,
                    "params": constraint.params,
                    "given": violation,
                    "missing": missing,
                    "message": message,
                }
            ],
        )


def check_constraints(
    constraints: List[Constraint],
    current_args: Dict[str, ParamInfo],
) -> None:
    """Evaluate all constraints; the first violation raises ConstraintError."""
    for constraint in constraints or []:
        check_constraint(constraint, current_args)
