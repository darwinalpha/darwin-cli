# src/darwin_cli/app.py

"""
CliApp facade: ties all components together.
"""

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from darwin_cli.actions import (
    ActionError,
    ActionRegistry,
    GLOBAL_ACTIONS,
    HelpRequested,
    MaxIterationsExceeded,
    RequiredError,
    load_actions_from_module,
)
from darwin_cli.base import CliResult, Constraint, Param
from darwin_cli.executor import Executor
from darwin_cli.help import HelpBuilder
from darwin_cli.loader import (
    compile_constraints,
    get_param_by_name,
    param_definitions_from_objects,
    parse_params_from_config,
)
from darwin_cli.parser import parse_args_with_meta


class CliApp:
    """Unified CLI application facade.

    Example::

        app = CliApp(params=[Param(name="name", required=True)], prog="demo.py")
        result = app.run(["--name", "Alice"])
    """

    def __init__(
        self,
        params: Union[List[Param], Dict[str, Dict[str, Any]]],
        prog: Optional[str] = None,
        description: Optional[str] = None,
        help: Optional[str] = None,
        max_iterations: int = 100,
        action_modules: Optional[List[str]] = None,
        custom_validators: Optional[Dict[str, Callable]] = None,
        available_sources: Optional[List[str]] = None,
        constraints: Optional[List[Union[Dict[str, Any], Constraint]]] = None,
        groups: Optional[Dict[str, Any]] = None,
        registry: Optional[ActionRegistry] = None,
    ):
        self._initial_params, param_definitions = self._normalize_params(params)
        self._initial_constraints = compile_constraints(
            definitions=param_definitions,
            groups=groups or {},
            constraints=constraints or [],
        )

        self.prog = prog
        self.description = help or description or ""
        self.max_iterations = max_iterations
        self.custom_validators = custom_validators or {}
        self.available_sources = available_sources or []
        self.registry = registry if registry is not None else GLOBAL_ACTIONS

        self._executor: Optional[Executor] = None
        self._static_params: List[Param] = []
        self._dynamic_params: List[Param] = []

        if action_modules:
            for module_path in action_modules:
                load_actions_from_module(module_path, self.registry)

    # ============================================================
    # Alternative constructors
    # ============================================================

    @classmethod
    def from_config(
        cls,
        config: Union[str, Dict[str, Any]],
        prog: Optional[str] = None,
        help: Optional[str] = None,
        loader: Optional[Callable[[str], Dict[str, Any]]] = None,
        mount: Optional[str] = None,
        **kwargs: Any,
    ) -> "CliApp":
        """Build a CliApp from a config dict or a config file path.

        Args:
            config: a config dict, or a path string.
            prog / help: forwarded to the constructor.
            loader: optional callable that resolves a path string to a dict.
                Pass ``darwin_config.get_config`` to integrate with darwin-config.
                When omitted, JSON files are read with the standard library.
            mount: optional dotted key path to select a sub-section of the config.
            **kwargs: all other CliApp constructor arguments.
        """
        if isinstance(config, str):
            if loader is not None:
                data = loader(config)
            else:
                with Path(config).open("r", encoding="utf-8") as f:
                    data = json.load(f)
        elif isinstance(config, dict):
            data = config
        else:
            raise TypeError(f"config must be a dict or path string, got {type(config)}")

        if mount:
            for part in mount.split("."):
                data = data.get(part, {}) if isinstance(data, dict) else {}

        description = help or (data.get("help") if isinstance(data, dict) else None)
        params_section = data.get("cli_args", data.get("params", {})) if isinstance(data, dict) else {}
        constraints_section = data.get("constraints", []) if isinstance(data, dict) else []
        groups_section = data.get("groups", {}) if isinstance(data, dict) else {}

        return cls(
            params=params_section,
            prog=prog or (data.get("prog") if isinstance(data, dict) else None),
            help=description,
            constraints=constraints_section,
            groups=groups_section,
            **kwargs,
        )

    # ============================================================
    # Init helpers
    # ============================================================

    def _normalize_params(
        self,
        params: Union[List[Param], Dict[str, Dict[str, Any]]],
    ) -> Tuple[List[Param], Dict[str, Dict[str, Any]]]:
        """Return the Param list plus a uniform mapping for the compiler."""
        if isinstance(params, list):
            for p in params:
                if not isinstance(p, Param):
                    raise TypeError(f"params elements must be Param, got {type(p)}")
            return params, param_definitions_from_objects(params)
        if isinstance(params, dict):
            return parse_params_from_config(params), params
        raise TypeError(f"params must be List[Param] or dict, got {type(params)}")

    # ============================================================
    # Run
    # ============================================================

    def run(self, args: Optional[List[str]] = None) -> CliResult:
        if args is None:
            args = sys.argv[1:]

        try:
            self._static_params = self._initial_params
            raw_static = parse_args_with_meta(
                params=self._static_params,
                args=args,
                prog=self.prog,
                description=self.description,
            )

            self._executor = Executor(
                params=self._static_params,
                max_iterations=self.max_iterations,
                custom_validators=self.custom_validators,
                constraints=self._initial_constraints,
                registry=self.registry,
            )

            final_args = self._executor.run(raw_static)

            all_params = self._executor._get_all_params()
            static_names = {p.name for p in self._static_params}
            self._dynamic_params = [p for p in all_params if p.name not in static_names]

            return CliResult.ok(final_args)

        except HelpRequested:
            print(self._build_help_text())
            return CliResult.help()

        except RequiredError as e:
            error_msg = str(e)
            print(self._build_error_help_text(error_msg))
            return CliResult.fail(error_msg)

        except (ActionError, MaxIterationsExceeded) as e:
            error_msg = str(e)
            print(self._build_error_help_text(error_msg))
            return CliResult.fail(error_msg)

        except Exception as e:
            error_msg = str(e)
            print(f"Error: {error_msg}", file=sys.stderr)
            return CliResult.fail(error_msg)

    def run_or_exit(self, args: Optional[List[str]] = None) -> Dict[str, Any]:
        result = self.run(args)
        if not result.success:
            if result.error:
                print(f"Error: {result.error}", file=sys.stderr)
            sys.exit(result.exit_code)
        if result.data is None:
            raise RuntimeError("Run succeeded but returned no data")
        return result.data

    # ============================================================
    # Help building
    # ============================================================

    def _get_source_from_current_args(self) -> Optional[str]:
        if self._executor is None or self._executor.current_args is None:
            return None
        info = self._executor.current_args.get("source")
        if info is None:
            return None
        return str(info.value) if info.value is not None else None

    def _build_help_text(self) -> str:
        builder = HelpBuilder(prog=self.prog, description=self.description)
        if self._executor is None:
            return "Executor not initialized"

        all_params = self._executor._get_all_params()
        static_names = {p.name for p in self._static_params}
        dynamic_params = [p for p in all_params if p.name not in static_names]

        source = self._get_source_from_current_args()
        current_args = self._executor.current_args or {}

        if source and dynamic_params:
            return builder.build_scenario_help(
                static_params=self._static_params,
                dynamic_params=dynamic_params,
                source=source,
                current_args=current_args,
            )
        return builder.build_global_help(
            static_params=self._static_params,
            available_sources=self.available_sources,
            current_args=current_args,
        )

    def _build_error_help_text(self, error: str) -> str:
        builder = HelpBuilder(prog=self.prog, description=self.description)
        if self._executor is None:
            return f"Error: {error}"

        all_params = self._executor._get_all_params()
        static_names = {p.name for p in self._static_params}
        dynamic_params = [p for p in all_params if p.name not in static_names]

        return builder.build_error_help(
            static_params=self._static_params,
            dynamic_params=dynamic_params,
            source=self._get_source_from_current_args(),
            error=error,
            available_sources=self.available_sources,
            current_args=self._executor.current_args or {},
        )

    # ============================================================
    # Convenience properties
    # ============================================================

    @property
    def params(self) -> List[Param]:
        if self._executor is None:
            return self._static_params
        return self._executor._get_all_params()

    @property
    def static_params(self) -> List[Param]:
        return self._static_params

    @property
    def dynamic_params(self) -> List[Param]:
        return self._dynamic_params

    def get_param(self, name: str) -> Optional[Param]:
        return get_param_by_name(self.params, name)
