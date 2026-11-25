# tests/conftest.py

"""Shared fixtures for the darwin-cli test suite."""

from typing import Any, Dict, List

import pytest

from darwin_cli.actions import ACTION_REGISTRY, clear_actions, register_action
from darwin_cli.base import Param, ParamInfo, ValidationRule

# ============================================================
# Test configuration data (defined inline in conftest.py)
# ============================================================

SIMPLE_CONFIG: Dict[str, Dict[str, Any]] = {
    "type": {
        "type": "str",
        "required": True,
        "help": "Data type",
        "validation": {"choices": ["stock_daily", "stock_hist"]},
    },
    "source": {
        "type": "str",
        "required": False,
        "help": "Data source",
    },
    "date": {
        "type": "str",
        "required": False,
        "help": "Date",
    },
    "help": {
        "type": "bool",
        "required": False,
        "help": "Show help",
    },
}

COMPLEX_CONFIG: Dict[str, Dict[str, Any]] = {
    "type": {
        "type": "str",
        "required": True,
        "action": "load_dynamic",
        "depends_on": ["source"],
        "help": "Data type",
        "validation": {"choices": ["stock_daily", "stock_minute", "index_daily", "forex_daily"]},
    },
    "source": {
        "type": "str",
        "required": False,
        "action": "infer_source",
        "help": "Data source (inferred by default)",
    },
    "date": {
        "type": "str",
        "required": False,
        "action": "get_last_trading_date",
        "help": "Date (defaults to last trading day)",
    },
    "year": {
        "type": "str",
        "required": False,
        "action": "expand_year",
        "help": "Year (expands to start_date and end_date)",
    },
    "symbol": {
        "type": {"pattern": r"^\d{6}\.(SH|SZ|BJ)$"},
        "required": True,
        "help": "Stock code (e.g. 600000.SH)",
    },
    "fields": {
        "type": "str",
        "default": "open,high,low,close,volume",
        "help": "Field list",
    },
    "overwrite": {
        "type": "bool",
        "required": False,
        "help": "Overwrite existing files",
    },
    "help": {
        "type": "bool",
        "required": False,
        "action": "print_help",
        "help": "Show help",
    },
}


# ============================================================
# Param definition fixtures
# ============================================================


@pytest.fixture
def sample_params() -> List[Param]:
    """Basic parameter list."""
    return [
        Param(name="type", type="str", required=True, help="Data type"),
        Param(name="source", type="str", required=False, help="Data source"),
        Param(name="date", type="str", required=False, help="Date"),
        Param(name="help", type="bool", action="print_help", help="Show help"),
    ]


@pytest.fixture
def sample_params_with_action() -> List[Param]:
    """Parameter list with actions."""
    return [
        Param(
            name="type",
            type="str",
            required=True,
            action="load_dynamic",
            depends_on=["source"],
            help="Data type",
        ),
        Param(
            name="source",
            type="str",
            required=False,
            action="infer_source",
            help="Data source",
        ),
        Param(
            name="date",
            type="str",
            required=False,
            action="get_last_date",
            help="Date",
        ),
        Param(
            name="help",
            type="bool",
            action="print_help",
            help="Show help",
        ),
    ]


@pytest.fixture
def sample_config() -> Dict[str, Dict[str, Any]]:
    """Simple config dict."""
    return SIMPLE_CONFIG


@pytest.fixture
def sample_config_with_validation() -> Dict[str, Dict[str, Any]]:
    """Config dict with validation rules."""
    return {
        "symbol": {
            "type": "str",
            "required": True,
            "help": "Stock code",
            "validation": {"pattern": r"^\d{6}\.(SH|SZ|BJ)$"},
        },
        "count": {
            "type": "int",
            "required": False,
            "help": "Count",
            "validation": {"min": 1, "max": 100},
        },
        "name": {
            "type": "str",
            "required": False,
            "help": "Name",
            "validation": {"min_length": 2, "max_length": 20},
        },
        "status": {
            "type": "str",
            "required": False,
            "help": "Status",
            "validation": {"choices": ["active", "inactive", "pending"]},
        },
    }


# ============================================================
# Action registration fixtures
# ============================================================


@pytest.fixture
def clear_action_registry():
    """Clear the Action registry before and after each test."""
    clear_actions()
    yield
    clear_actions()


@pytest.fixture
def registered_actions(clear_action_registry):
    """Register the action functions used by the tests."""

    @register_action("infer_source")
    def infer_source(value: str, current_args: Dict[str, ParamInfo]) -> Dict[str, Any]:
        """Infer the data source."""
        if value is not None:
            return {}
        type_info = current_args.get("type")
        if type_info and type_info.value == "stock_daily":
            return {"source": "tushare"}
        return {"source": "yahoo"}

    @register_action("load_dynamic")
    def load_dynamic(value: str, current_args: Dict[str, ParamInfo]) -> Dict[str, Any]:
        """Load dynamic params."""
        source_info = current_args.get("source")
        if not source_info or source_info.value is None:
            return {}

        return {
            "params": [
                Param(
                    name="symbol",
                    type="str",
                    required=True,
                    help="Stock code",
                    validation=ValidationRule(pattern=r"^\d{6}\.(SH|SZ)$"),
                ),
                Param(
                    name="fields",
                    type="str",
                    required=False,
                    default="open,high,low,close,volume",
                    help="Field list",
                ),
            ]
        }

    @register_action("get_last_date")
    def get_last_date(value: str, current_args: Dict[str, ParamInfo]) -> Dict[str, Any]:
        """Get the last trading day."""
        if value is not None:
            return {}
        return {"date": "2026-01-20"}

    @register_action("expand_year")
    def expand_year(value: str, current_args: Dict[str, ParamInfo]) -> Dict[str, Any]:
        """Expand a year into a date range."""
        if value is None:
            return {}
        year = str(value)

        return {
            "values": {
                "start_date": f"{year}-01-01",
                "end_date": f"{year}-12-31",
            },
            "params": [
                Param(name="start_date", type="str", help="Start date"),
                Param(name="end_date", type="str", help="End date"),
            ],
        }

    return ACTION_REGISTRY


# ============================================================
# Help function fixtures
# ============================================================


@pytest.fixture
def dynamic_help_func():
    """Dynamic help callable."""

    def type_help(current_args: Dict[str, ParamInfo]) -> str:
        types = ["stock_daily", "stock_hist", "index_daily"]
        return f"Available types: {', '.join(types)}"

    return type_help


@pytest.fixture
def dynamic_default_func():
    """Dynamic default callable."""

    def default_source(current_args: Dict[str, ParamInfo]) -> str:
        type_info = current_args.get("type")
        if type_info and type_info.value == "stock_daily":
            return "tushare"
        return "yahoo"

    return default_source
