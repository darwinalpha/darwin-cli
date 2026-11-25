# examples/actions.py

"""Shared Actions for the examples.

Importing this module registers nothing. Call :func:`register_all` explicitly
so the examples stay deterministic when tests clear a registry between cases.
The same functions work with the global registry or an injected
``ActionRegistry`` instance.
"""

from typing import Any, Dict, Optional

from darwin_cli import (
    GLOBAL_ACTIONS,
    ActionRegistry,
    ActionResult,
    Param,
    ValidationRule,
    has_action,
    register_action,
)


# ============================================================
# Action functions
# ============================================================


def guess_source(value: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Infer --source from --type, but never override an explicit user value."""
    if value is not None:
        return {}
    type_info = ctx.get("type")
    data_type = type_info.value if type_info is not None else None
    if data_type in ("stock_daily", "stock_hist"):
        return {"source": "tushare"}
    return {"source": "yahoo"}


def load_dynamic_params(value: Any, ctx: Dict[str, Any]) -> ActionResult:
    """Declare source-specific parameters at runtime.

    tushare expects an A-share code; yahoo expects a ticker and a bar interval.
    Neither ``symbol`` nor ``interval`` is declared statically.
    """
    source_info = ctx.get("source")
    source = source_info.value if source_info is not None else None
    if source == "tushare":
        return ActionResult(
            params=[
                Param(
                    name="symbol",
                    type=ValidationRule(pattern=r"^\d{6}\.(SH|SZ|BJ)$"),
                    required=True,
                    help="A-share code, e.g. 600000.SH",
                ),
                Param(
                    name="fields",
                    type="str",
                    default="close",
                    help="Comma-separated fields",
                ),
            ]
        )
    return ActionResult(
        params=[
            Param(name="symbol", type="str", required=True, help="Ticker, e.g. AAPL"),
            Param(
                name="interval",
                type="str",
                default="1d",
                validation=ValidationRule(choices=["1d", "1wk", "1mo"]),
                help="Bar interval",
            ),
        ]
    )


def expand_year(value: Any, ctx: Dict[str, Any]) -> ActionResult:
    """Expand one --year into start_date / end_date values."""
    if value is None:
        return {}
    year = str(value)
    return ActionResult(
        values={
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
        },
        params=[
            Param(name="start_date", type="str", help="Range start"),
            Param(name="end_date", type="str", help="Range end"),
        ],
    )


def build_report(value: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Consume values produced by another action (demonstrates depends_on)."""
    start = ctx.get("start_date")
    end = ctx.get("end_date")
    if start is None or end is None or start.value is None or end.value is None:
        return {}
    return {"report": f"{start.value}..{end.value}"}


ACTIONS = {
    "guess_source": guess_source,
    "load_dynamic_params": load_dynamic_params,
    "expand_year": expand_year,
    "build_report": build_report,
}


# ============================================================
# Registration
# ============================================================


def register_all(registry: Optional[ActionRegistry] = None) -> ActionRegistry:
    """Idempotently register every example Action into ``registry``.

    Defaults to the process-wide global registry. Safe to call repeatedly,
    which matters because tests may call ``clear_actions()`` between cases.
    """
    target = registry if registry is not None else GLOBAL_ACTIONS
    for name, func in ACTIONS.items():
        if not has_action(name, registry=target):
            register_action(name, registry=target)(func)
    return target
