# src/darwin_cli/actions.py

"""
Action registry (global + per-app instances), built-in actions and exceptions.
"""

from functools import wraps
from typing import Any, Callable, Dict, Optional

# ============================================================
# Registry
# ============================================================


class ActionRegistry:
    """An isolated namespace of actions.

    The library keeps a global registry for the classic decorator style::

        @register_action("hello")
        def hello(value, ctx): ...

    Applications that need isolation can create their own and inject it::

        reg = ActionRegistry()
        @register_action("hello", registry=reg)
        def hello(value, ctx): ...
        app = CliApp(params=..., registry=reg)
    """

    def __init__(self) -> None:
        self._actions: Dict[str, Callable] = {}

    def register(self, name: str, func: Callable) -> None:
        if name in self._actions:
            raise ValueError(f"Action '{name}' already registered")
        self._actions[name] = func

    def get(self, name: str) -> Callable:
        if name not in self._actions:
            raise KeyError(f"Action '{name}' not registered")
        return self._actions[name]

    def has(self, name: str) -> bool:
        return name in self._actions

    def list_actions(self) -> Dict[str, Callable]:
        return dict(self._actions)

    def clear(self) -> None:
        self._actions.clear()

    # dict-like helpers for compatibility with code that inspects the registry
    def __contains__(self, name: str) -> bool:
        return name in self._actions

    def __getitem__(self, name: str) -> Callable:
        return self.get(name)

    def __iter__(self):
        return iter(self._actions)

    def __len__(self) -> int:
        return len(self._actions)


GLOBAL_ACTIONS = ActionRegistry()

# Backward-compatible alias: still points to the process-wide registry.
ACTION_REGISTRY = GLOBAL_ACTIONS


def register_action(name: str, *, registry: Optional[ActionRegistry] = None):
    """Decorator: register an action function.

    Args:
        name: action name referenced by ``Param.action``.
        registry: target registry; defaults to the global one.
    """
    target = registry if registry is not None else GLOBAL_ACTIONS

    def decorator(func: Callable) -> Callable:
        target.register(name, func)
        return func

    return decorator


def get_action(name: str, registry: Optional[ActionRegistry] = None) -> Callable:
    target = registry if registry is not None else GLOBAL_ACTIONS
    return target.get(name)


def has_action(name: str, registry: Optional[ActionRegistry] = None) -> bool:
    target = registry if registry is not None else GLOBAL_ACTIONS
    return target.has(name)


def list_actions(registry: Optional[ActionRegistry] = None) -> Dict[str, Callable]:
    target = registry if registry is not None else GLOBAL_ACTIONS
    return target.list_actions()


def clear_actions(registry: Optional[ActionRegistry] = None) -> None:
    target = registry if registry is not None else GLOBAL_ACTIONS
    target.clear()


def validate_before(validator: Callable):
    """Decorator: call ``validator(current_args)`` before the action runs.

    The validator must raise to reject the invocation.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(value, current_args):
            validator(current_args)
            return func(value, current_args)

        return wrapper

    return decorator


# ============================================================
# Built-in actions
# ============================================================


@register_action("print_help")
def print_help(value: bool, current_args: Dict[str, Any]) -> None:
    """Raise HelpRequested; CliApp turns it into formatted help output."""
    raise HelpRequested()


@register_action("set_overwrite")
def set_overwrite(value: bool, current_args: Dict[str, Any]) -> Dict[str, Any]:
    return {"overwrite": True} if value else {}


@register_action("set_fake")
def set_fake(value: bool, current_args: Dict[str, Any]) -> Dict[str, Any]:
    return {"fake": True} if value else {}


# ============================================================
# Dynamic loading
# ============================================================


def load_actions_from_module(module_path: str, registry: Optional[ActionRegistry] = None) -> None:
    """Import a module so its ``@register_action`` decorators execute.

    Note: a decorator without an explicit registry always targets the global
    registry. Use ``register_action(..., registry=reg)`` inside the module for
    isolated registration.
    """
    import importlib

    try:
        importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Cannot load action module '{module_path}': {e}")


def load_actions_from_file(filepath: str) -> None:
    """Load action definitions from a Python file (global registry)."""
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Action file not found: {filepath}")

    module_name = path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load action file: {filepath}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


# ============================================================
# Exceptions (English messages by design: for developers)
# ============================================================


class HelpRequested(Exception):
    """Request help output."""


class ActionError(Exception):
    """Action execution or validation failed."""


class ConflictError(ActionError):
    """Parameters conflict with each other."""


class ConstraintError(ActionError):
    """A cross-parameter constraint was violated.

    ``violations`` carries machine-readable details:
        [{"rule": ..., "params": [...], "message": ...}, ...]
    """

    def __init__(self, message: str, violations: Optional[list] = None):
        super().__init__(message)
        self.violations = violations or []


class RequiredError(Exception):
    """A required parameter is missing or came from an invalid source."""


class MaxIterationsExceeded(Exception):
    """The deferred-execution loop exceeded its iteration budget."""


class CycleDetected(ActionError):
    """A dependency cycle was detected among parameters."""
