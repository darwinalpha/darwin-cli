# src/darwin_cli/executor.py

"""
Deferred execution engine with dependency ordering, dynamic parameters,
true cycle detection and constraint checking.
"""

from typing import Any, Callable, Dict, List, Optional

from darwin_cli.actions import (
    ActionError,
    ActionRegistry,
    CycleDetected,
    GLOBAL_ACTIONS,
    HelpRequested,
    MaxIterationsExceeded,
    RequiredError,
    get_action,
)
from darwin_cli.base import ActionResult, Constraint, Param, ParamInfo
from darwin_cli.constraints import check_constraints
from darwin_cli.loader import get_param_by_name
from darwin_cli.validator import Validator

USER_SOURCES = ("cli", "action")


class Executor:
    """Deferred parameter-processing engine.

    Responsibilities:
        1. value validation
        2. action execution
        3. dependency ordering with re-queueing
        4. dynamic parameter generation
        5. iteration control and true cycle detection
        6. cross-parameter constraint checking
    """

    def __init__(
        self,
        params: List[Param],
        max_iterations: int = 100,
        custom_validators: Optional[Dict[str, Callable]] = None,
        constraints: Optional[List[Constraint]] = None,
        registry: Optional[ActionRegistry] = None,
    ):
        self.params = params
        self.max_iterations = max_iterations
        self.custom_validators = custom_validators or {}
        self.constraints = constraints or []
        self.registry = registry if registry is not None else GLOBAL_ACTIONS

        self._validator: Optional[Validator] = None
        self._dynamic_params: Dict[str, Param] = {}
        self._current_args: Optional[Dict[str, ParamInfo]] = None
        self._dirty_values: set = set()
        self._iteration: int = 0

    @property
    def current_args(self) -> Optional[Dict[str, ParamInfo]]:
        return self._current_args

    def _get_validator(self) -> Validator:
        if self._validator is None:
            self._validator = Validator()
            for name, func in self.custom_validators.items():
                self._validator.register_custom(name, func)
        return self._validator

    def _find_param(self, name: str) -> Optional[Param]:
        if name in self._dynamic_params:
            return self._dynamic_params[name]
        return get_param_by_name(self.params, name)

    def _get_all_params(self) -> List[Param]:
        return self.params + list(self._dynamic_params.values())

    def _has_action(self, name: str) -> bool:
        param = self._find_param(name)
        return param is not None and param.action is not None

    def _is_required(self, name: str) -> bool:
        param = self._find_param(name)
        return param is not None and param.required

    def _check_required_from_user(
        self,
        param: Param,
        current_args: Dict[str, ParamInfo],
    ) -> None:
        if not param.required:
            return
        info = current_args.get(param.name)
        if info is None or info.value is None:
            raise RequiredError(f"Missing required parameter: --{param.name}")
        if info.from_source not in USER_SOURCES:
            raise RequiredError(
                f"Parameter --{param.name} must come from CLI or an Action, "
                f"got source: {info.from_source}"
            )

    def _resolve_default_value(
        self,
        param: Param,
        current_args: Dict[str, ParamInfo],
    ) -> Any:
        if callable(param.default):
            try:
                return param.default(current_args)
            except Exception as e:
                raise ActionError(f"Default value function for '{param.name}' failed: {e}")
        return param.default

    def _resolve_action(self, param: Param) -> Optional[Callable]:
        if param.action is None:
            return None
        if callable(param.action):
            return param.action
        if self.registry.has(param.action):
            return get_action(param.action, self.registry)
        raise ActionError(f"Action '{param.action}' is not registered (param: {param.name})")

    # ============================================================
    # True cycle detection over the dependency graph
    # ============================================================

    def _find_cycle(self, start: str) -> Optional[List[str]]:
        """DFS from ``start`` following depends_on; return a cycle path if found."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {}
        path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            color[node] = GRAY
            path.append(node)
            param = self._find_param(node)
            deps = param.depends_on if param else None
            for dep in deps or []:
                state = color.get(dep, WHITE)
                if state == GRAY:
                    idx = path.index(dep)
                    return path[idx:] + [dep]
                if state == WHITE:
                    found = dfs(dep)
                    if found:
                        return found
            path.pop()
            color[node] = BLACK
            return None

        return dfs(start)

    # ============================================================
    # Main loop
    # ============================================================

    def run(self, raw_params: Dict[str, ParamInfo]) -> Dict[str, Any]:
        current_args = raw_params.copy()
        self._current_args = current_args
        self._dirty_values = set()
        self._iteration = 0

        # Phase 1: help short-circuit
        help_name = "help"
        has_help = help_name in current_args and current_args[help_name].value is True
        has_other_action = False
        for p in self._get_all_params():
            if p.action and p.name != help_name:
                info = current_args.get(p.name)
                if info is not None and info.value is not None:
                    has_other_action = True
                    break

        if has_help and not has_other_action:
            self._current_args = current_args
            raise HelpRequested()

        # Phase 2: default values
        for p in self._get_all_params():
            if p.name == help_name:
                continue
            info = current_args.get(p.name)
            if info is None or (info.value is None and p.default is not None):
                default_value = self._resolve_default_value(p, current_args)
                if default_value is not None:
                    if info is None:
                        current_args[p.name] = ParamInfo(
                            value=default_value,
                            defined=True,
                            from_source="default",
                        )
                    else:
                        info.value = default_value
                        info.from_source = "default"

        # Phase 3: initial pending queue
        pending = self._build_initial_pending(current_args)

        # Phase 4: help goes last
        if has_help and help_name in pending:
            pending.remove(help_name)
            pending.append(help_name)

        # Phase 5: deferred loop
        while pending:
            self._iteration += 1
            if self._iteration > self.max_iterations:
                raise MaxIterationsExceeded(
                    f"Exceeded max iterations ({self.max_iterations})"
                )

            name = pending.pop(0)

            if name == help_name:
                self._current_args = current_args
                raise HelpRequested()

            param_info = current_args.get(name)
            if param_info is None or param_info.processed:
                continue

            param = self._find_param(name)
            if param is None:
                param_info.processed = True
                continue

            # Step 1: dependencies
            if param.depends_on:
                unsatisfied = self._get_unsatisfied_dependencies(
                    name, param.depends_on, current_args
                )
                if unsatisfied:
                    cycle = self._find_cycle(name)
                    if cycle:
                        raise CycleDetected(
                            f"Dependency cycle detected: {' -> '.join(cycle)}"
                        )
                    self._reorder_pending(name, unsatisfied, pending)
                    continue

            # Step 2: validation
            if param_info.value is not None:
                validated = self._get_validator().validate_one(param, param_info.value)
                if validated != param_info.value:
                    param_info.value = validated

            # Step 3: action
            if param.action:
                if param.required and param_info.value is None:
                    param_info.processed = True
                    continue

                action_func = self._resolve_action(param)
                if action_func:
                    try:
                        result = action_func(param_info.value, current_args)
                    except HelpRequested:
                        raise
                    except Exception as e:
                        raise ActionError(
                            f"Action for parameter '{param.name}' failed: {e}"
                        ) from e

                    if result is not None:
                        if not isinstance(result, ActionResult):
                            if isinstance(result, dict):
                                result = ActionResult(values=result)
                            else:
                                raise ActionError(
                                    f"Action '{param.name}' returned {type(result).__name__}, "
                                    f"expected ActionResult or dict"
                                )
                        self._merge_action_result(current_args, result, pending)

            # Step 4: mark processed
            param_info.processed = True

        # Phase 5.5: unknown CLI parameters
        valid_names = {p.name for p in self._get_all_params()}
        for key, info in current_args.items():
            if info.from_source == "cli" and key not in valid_names and key != "help":
                raise ActionError(f"Unknown parameter: --{key}")

        # Phase 6: re-validate only values touched by actions
        for name in self._dirty_values:
            info = current_args.get(name)
            param = self._find_param(name)
            if info is not None and param is not None and info.value is not None:
                validated = self._get_validator().validate_one(param, info.value)
                if validated != info.value:
                    info.value = validated

        # Phase 7: constraints (explicit CLI args only)
        check_constraints(self.constraints, current_args)

        # Phase 8: required parameters
        for p in self._get_all_params():
            self._check_required_from_user(p, current_args)

        # Phase 9: return
        self._current_args = current_args
        return {key: info.value for key, info in current_args.items()}

    # ============================================================
    # Helpers
    # ============================================================

    def _build_initial_pending(self, current_args: Dict[str, ParamInfo]) -> List[str]:
        pending: List[str] = []
        for p in self._get_all_params():
            if p.name == "help":
                continue
            if p.name not in current_args:
                current_args[p.name] = ParamInfo(value=None, defined=True, from_source="default")
            pending.append(p.name)

        help_info = current_args.get("help")
        if help_info is not None and help_info.value is True:
            pending.append("help")
        return pending

    def _get_unsatisfied_dependencies(
        self,
        name: str,
        depends_on: List[str],
        current_args: Dict[str, ParamInfo],
    ) -> List[str]:
        unsatisfied: List[str] = []
        for dep in depends_on:
            info = current_args.get(dep)
            if info is None:
                unsatisfied.append(dep)
                continue
            if info.processed:
                continue
            if info.value is not None:
                unsatisfied.append(dep)
                continue
            if info.value is None and self._is_required(dep):
                unsatisfied.append(dep)
                continue
            if info.from_source == "default" and self._has_action(dep):
                unsatisfied.append(dep)
                continue
            if info.value is None and self._has_action(dep):
                unsatisfied.append(dep)
        return unsatisfied

    def _reorder_pending(self, name, unsatisfied, pending):
        if name in pending:
            pending.remove(name)
        for dep in unsatisfied:
            if dep in pending:
                pending.remove(dep)
        for dep in reversed(unsatisfied):
            pending.insert(0, dep)

        help_index = next((i for i, p in enumerate(pending) if p == "help"), -1)
        if help_index >= 0:
            pending.insert(help_index, name)
        else:
            pending.insert(len(unsatisfied), name)

    def _merge_action_result(
        self,
        current_args: Dict[str, ParamInfo],
        result: ActionResult,
        pending: List[str],
    ) -> None:
        for key, value in result.values.items():
            if key in current_args:
                existing = current_args[key]
                if existing.value is not None and existing.from_source in ("cli", "action"):
                    continue
                if existing.from_source != "cli":
                    existing.from_source = "action"
                existing.value = value
                existing.processed = False
                self._dirty_values.add(key)
                if key not in pending:
                    pending.append(key)
            else:
                current_args[key] = ParamInfo(
                    value=value,
                    defined=False,
                    from_source="action",
                )
                self._dirty_values.add(key)
                if key not in pending:
                    pending.append(key)

        for new_param in result.params:
            self._dynamic_params[new_param.name] = new_param
            if new_param.name not in current_args:
                default_value = new_param.default
                if callable(default_value):
                    try:
                        default_value = default_value(current_args)
                    except Exception:
                        default_value = None
                current_args[new_param.name] = ParamInfo(
                    value=default_value,
                    defined=True,
                    from_source="default",
                )
            else:
                current_args[new_param.name].defined = True

            # A dynamically discovered parameter may already hold a CLI-provided
            # value (captured as an unknown arg). It must be processed so that
            # validation and actions are applied to it.
            info = current_args[new_param.name]
            if not info.processed:
                self._dirty_values.add(new_param.name)
                if new_param.name not in pending:
                    pending.append(new_param.name)

            if new_param.action:
                if "help" in pending:
                    pending.remove("help")
                if new_param.name not in pending:
                    pending.append(new_param.name)
                help_info = current_args.get("help")
                if help_info is not None and help_info.value is True:
                    pending.append("help")

        self._current_args = current_args
