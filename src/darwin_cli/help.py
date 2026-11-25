# src/darwin_cli/help.py

"""
Context-aware help text builder.
"""

from typing import Dict, List, Optional

from darwin_cli.base import Param, ParamInfo, ValidationRule


class HelpBuilder:
    def __init__(self, prog: Optional[str] = None, description: Optional[str] = None):
        self.prog = prog or "main.py"
        self.description = description or "CLI tool"

    def build_global_help(
        self,
        static_params: List[Param],
        available_sources: Optional[List[str]] = None,
        current_args: Optional[Dict[str, ParamInfo]] = None,
        error: Optional[str] = None,
    ) -> str:
        current_args = current_args or {}
        lines: List[str] = []

        if error:
            lines.append(f"Error: {error}")
            lines.append("")

        lines.append(f"Usage: {self.prog} [global options]")
        lines.append("")

        if self.description:
            lines.append(self.description)
            lines.append("")

        lines.append("Global options:")
        for p in static_params:
            if p.name == "help":
                continue
            lines.append(f"  --{p.name} {self._format_param(p, current_args)}")

        if available_sources:
            lines.append("")
            lines.append("Sources:")
            lines.append(f"  {', '.join(available_sources)}")

        lines.append("  --help            Show this help message")
        lines.append("")
        return "\n".join(lines)

    def build_scenario_help(
        self,
        static_params: List[Param],
        dynamic_params: List[Param],
        source: Optional[str] = None,
        current_args: Optional[Dict[str, ParamInfo]] = None,
        error: Optional[str] = None,
    ) -> str:
        current_args = current_args or {}
        lines: List[str] = []

        if error:
            lines.append(f"Error: {error}")
            lines.append("")

        source_info = f" --source {source}" if source else ""
        lines.append(f"Usage: {self.prog}{source_info} [options]")
        lines.append("")

        if source:
            lines.append(f"Source: {source}")
            lines.append("")

        all_params = static_params + dynamic_params
        dynamic_names = {dp.name for dp in dynamic_params}

        lines.append("Options:")
        for p in all_params:
            if p.name in ("help", "source"):
                continue
            prefix = "  " + ("(dynamic) " if p.name in dynamic_names else "")
            lines.append(f"{prefix}--{p.name} {self._format_param(p, current_args)}")

        lines.append("")
        lines.append("  --help            Show this help message")
        return "\n".join(lines)

    def build_error_help(
        self,
        static_params: List[Param],
        dynamic_params: List[Param],
        source: Optional[str] = None,
        error: str = "",
        available_sources: Optional[List[str]] = None,
        current_args: Optional[Dict[str, ParamInfo]] = None,
    ) -> str:
        current_args = current_args or {}
        if source is not None:
            return self.build_scenario_help(
                static_params=static_params,
                dynamic_params=dynamic_params,
                source=source,
                current_args=current_args,
                error=error,
            )
        return self.build_global_help(
            static_params=static_params,
            available_sources=available_sources,
            current_args=current_args,
            error=error,
        )

    def _get_help_text(self, param: Param, current_args: Dict[str, ParamInfo]) -> str:
        help_value = param.help
        if callable(help_value):
            try:
                result = help_value(current_args)
                return str(result) if result is not None else ""
            except Exception as e:
                return f"(help generation failed: {e})"
        return str(help_value) if help_value else ""

    def _format_param(self, param: Param, current_args: Dict[str, ParamInfo]) -> str:
        parts: List[str] = []

        if isinstance(param.type, str):
            parts.append("(flag)" if param.type == "bool" else f"<{param.type}>")
        else:
            parts.append("<str>")

        if param.required:
            parts.append("[required]")

        if param.default is not None and not callable(param.default):
            parts.append(f"(default: {param.default})")

        validation = self._get_validation(param)
        if validation:
            if validation.choices:
                parts.append(f"choices: {', '.join(str(c) for c in validation.choices)}")
            if validation.min is not None and validation.max is not None:
                parts.append(f"range: {validation.min}-{validation.max}")
            elif validation.min is not None:
                parts.append(f"min: {validation.min}")
            elif validation.max is not None:
                parts.append(f"max: {validation.max}")
            if validation.pattern:
                parts.append(f"pattern: {validation.pattern}")
            if validation.min_length is not None:
                parts.append(f"min length: {validation.min_length}")
            if validation.max_length is not None:
                parts.append(f"max length: {validation.max_length}")

        help_text = self._get_help_text(param, current_args)
        if help_text:
            if "\n" in help_text:
                indented = "\n    ".join(help_text.splitlines())
                parts.append(f"\n    {indented}")
            else:
                parts.append(f"({help_text})")

        return " ".join(parts)

    def _get_validation(self, param: Param) -> Optional[ValidationRule]:
        if isinstance(param.type, str):
            return param.validation
        return param.type
