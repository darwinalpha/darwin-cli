# src/darwin_cli/parser.py

"""
argparse builder + argument parsing with reliable source tracking.

Source tracking is done by custom argparse.Action subclasses instead of
scanning raw argv. This correctly handles ``--key value``, ``--key=value``
and boolean flags without the O(n^2) argv scan of earlier versions.
"""

import argparse
from typing import Any, Dict, List, Optional

from darwin_cli.base import Param, ParamInfo

# ============================================================
# Tracking actions
# ============================================================


class _TrackingStore(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        setattr(namespace, f"_{self.dest}_source", "cli")


class _TrackingStoreTrue(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)
        setattr(namespace, f"_{self.dest}_source", "cli")


class _TrackingStoreFalse(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, False)
        setattr(namespace, f"_{self.dest}_source", "cli")


# ============================================================
# Parser builder
# ============================================================


class ParserBuilder:
    def __init__(
        self,
        params: List[Param],
        prog: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.params = params
        self.prog = prog
        self.description = description

    def build(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=self.prog,
            description=self.description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            add_help=False,
        )
        for param in self.params:
            if param.name != "help":
                self._add_argument(parser, param)
        return parser

    def _add_argument(self, parser: argparse.ArgumentParser, param: Param) -> None:
        kwargs = self._build_kwargs(param)
        parser.add_argument(f"--{param.name}", **kwargs)

    def _build_kwargs(self, param: Param) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "help": self._get_help_text(param),
            "dest": param.name,
        }

        param_type = param.type if isinstance(param.type, str) else "str"
        default = None if callable(param.default) else param.default

        if param_type == "bool":
            action_cls = _TrackingStoreFalse if default is True else _TrackingStoreTrue
            kwargs["action"] = action_cls
            # argparse's default for a flag with nargs=0 is False/True accordingly.
            kwargs["default"] = default if default is not None else False
        else:
            kwargs["action"] = _TrackingStore
            if param_type == "int":
                kwargs["type"] = int
            elif param_type == "float":
                kwargs["type"] = float
            if default is not None:
                kwargs["default"] = default

        return kwargs

    def _get_help_text(self, param: Param) -> str:
        if isinstance(param.help, str):
            return param.help
        if callable(param.help):
            func_name = getattr(param.help, "__name__", "dynamic")
            return f"[dynamic help: {func_name}]"
        return ""


# ============================================================
# Parsing with metadata
# ============================================================


def _track_unknown(
    unknown: List[str],
    result: Dict[str, ParamInfo],
    param_names: set,
) -> None:
    """Collect unknown ``--key value`` pairs (dynamic params defined later)."""
    i = 0
    while i < len(unknown):
        arg = unknown[i]
        if arg in ("-h", "--help"):
            result["help"] = ParamInfo(value=True, defined=False, processed=False)
            i += 1
            continue
        if arg.startswith("--"):
            key = arg[2:]
            if "=" in key:
                key, value = key.split("=", 1)
                i += 1
            elif i + 1 < len(unknown) and not unknown[i + 1].startswith("--"):
                value = unknown[i + 1]
                i += 2
            else:
                value = True
                i += 1
            if key not in result:
                result[key] = ParamInfo(value=value, defined=key in param_names, processed=False)
        else:
            i += 1


def parse_args_with_meta(
    params: List[Param],
    args: Optional[List[str]] = None,
    prog: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, ParamInfo]:
    """Parse arguments and return a dict of ParamInfo with reliable sources.

    ``from_source`` is "cli" only when argparse's tracking action fired,
    otherwise "default" when a static default exists, or "cli" for unknown
    dynamic arguments that were explicitly supplied on the command line.
    """
    builder = ParserBuilder(params, prog=prog, description=description)
    parser = builder.build()
    parsed, unknown = parser.parse_known_args(args)

    param_names = {p.name for p in params}
    result: Dict[str, ParamInfo] = {}

    namespace = vars(parsed)
    for key, value in namespace.items():
        if key.startswith("_"):
            continue
        source = namespace.get(f"_{key}_source")
        if source is None:
            source = "default"
        result[key] = ParamInfo(
            value=value,
            defined=key in param_names,
            from_source=source,
            processed=False,
        )

    _track_unknown(unknown, result, param_names)

    for p in params:
        if p.name not in result:
            result[p.name] = ParamInfo(
                value=None,
                defined=True,
                from_source="default",
                processed=False,
            )

    return result


def build_parser(
    params: List[Param],
    prog: Optional[str] = None,
    description: Optional[str] = None,
) -> argparse.ArgumentParser:
    return ParserBuilder(params, prog=prog, description=description).build()
