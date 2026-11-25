# tests/test_cli/integration/test_integration_fetch.py

"""
Integration tests: realistic fetch-tool scenarios
"""

import pytest
from darwin_cli.app import CliApp
from darwin_cli.base import Param, ValidationRule, ActionResult
from darwin_cli.actions import (
    register_action,
    clear_actions,
    HelpRequested,
    ActionError,
    RequiredError,
)


class TestIntegrationFetch:
    """ fetch.py Data fetching tool Test """

    @pytest.fixture(autouse=True)
    def setup_actions(self):
        """Test   action"""
        clear_actions()

        # ============================================================
        # Action: Data source
        # ============================================================
        @register_action("infer_source")
        def infer_source(value, ctx):
            """Infer --source from --type"""
            if value is not None:
                return {}

            type_info = ctx.get("type")
            if not type_info or type_info.value is None:
                return {"source": "tushare"}

            data_type = type_info.value
            mapping = {
                "stock_daily": "tushare",
                "stock_minute": "tushare",
                "index_daily": "yahoo",
                "forex_daily": "alphavantage",
            }
            return {"source": mapping.get(data_type, "tushare")}

        # ============================================================
        # Action: Load dynamic params
        # ============================================================
        @register_action("load_dynamic_params")
        def load_dynamic_params(value, ctx):
            """Load dynamic params from --type and --source"""
            source_info = ctx.get("source")
            if not source_info or source_info.value is None:
                return {}

            source = source_info.value
            data_type = value

            # Simulate a config lookup
            adapter_configs = {
                ("tushare", "stock_daily"): [
                    Param(
                        name="symbol",
                        type=ValidationRule(pattern=r"^\d{6}\.(SH|SZ)$"),
                        required=True,
                        help="Stock code (e.g. 600000.SH)",
                    ),
                    Param(
                        name="fields",
                        type="str",
                        default="open,high,low,close,volume",
                        help="Field list",
                    ),
                ],
                ("yahoo", "stock_daily"): [
                    Param(
                        name="symbol",
                        type="str",
                        required=True,
                        help="Ticker (e.g. AAPL)",
                    ),
                    Param(
                        name="interval",
                        type="str",
                        default="1d",
                        validation=ValidationRule(choices=["1d", "1wk", "1mo"]),
                        help="Bar interval",
                    ),
                ],
                ("yahoo", "index_daily"): [
                    Param(
                        name="symbol",
                        type="str",
                        required=True,
                        help="Index code (e.g. ^GSPC) ",
                    ),
                    Param(
                        name="interval",
                        type="str",
                        default="1d",
                        validation=ValidationRule(choices=["1d", "1wk", "1mo"]),
                        help="Bar interval",
                    ),
                ],
                ("tushare", "stock_minute"): [
                    Param(
                        name="symbol",
                        type=ValidationRule(pattern=r"^\d{6}\.(SH|SZ)$"),
                        required=True,
                        help="Stock code (e.g. 600000.SH)",
                    ),
                    Param(
                        name="frequency",
                        type="str",
                        default="1min",
                        validation=ValidationRule(
                            choices=["1min", "5min", "15min", "30min", "60min"]
                        ),
                        help="Minute-level",
                    ),
                ],
            }

            params = adapter_configs.get((source, data_type), [])
            if not params:
                raise ActionError(f"Data source '{source}' Unsupported type '{data_type}'")

            return ActionResult(params=params)

        # ============================================================
        # Action: Get the last trading day
        # ============================================================
        @register_action("get_last_trading_date")
        def get_last_trading_date(value, ctx):
            """Get the last trading day"""
            if value is not None:
                return {}
            return {"date": "2026-01-20"}

        # ============================================================
        # Action: Expand a year
        # ============================================================
        @register_action("expand_year")
        def expand_year(value, ctx):
            """Expand --year into start_date and end_date"""
            if value is None:
                return {}

            year = str(value)
            return ActionResult(
                values={
                    "start_date": f"{year}-01-01",
                    "end_date": f"{year}-12-31",
                },
                params=[
                    Param(name="start_date", type="str", help="Start date"),
                    Param(name="end_date", type="str", help="End date"),
                ],
            )

        yield
        clear_actions()

    @pytest.fixture
    def static_params(self):
        """Static parameter definitions"""
        return [
            Param(
                name="type",
                type="str",
                required=True,
                action="load_dynamic_params",
                depends_on=["source"],
                validation=ValidationRule(
                    choices=["stock_daily", "stock_minute", "index_daily", "forex_daily"]
                ),
                help="Data type",
            ),
            Param(
                name="source",
                type="str",
                required=False,
                action="infer_source",
                help="Data source (inferred by default)",
            ),
            Param(
                name="date",
                type="str",
                required=False,
                action="get_last_trading_date",
                help="Date (defaults to last trading day)",
            ),
            Param(
                name="year",
                type="str",
                required=False,
                action="expand_year",
                help="Year (expands to start_date and end_date)",
            ),
            Param(
                name="overwrite",
                type="bool",
                required=False,
                help="Overwrite existing files",
            ),
            Param(
                name="help",
                type="bool",
                action="print_help",
                help="Show help",
            ),
        ]

    # ============================================================
    # Test Scenario
    # ============================================================

    def test_scenario_basic_fetch(self, static_params):
        """Scenario1: """
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "tushare",
                "--symbol",
                "600000.SH",
                "--date",
                "2026-01-20",
            ]
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "stock_daily"
        assert result.data["source"] == "tushare"
        assert result.data["symbol"] == "600000.SH"
        assert result.data["date"] == "2026-01-20"
        # fields has a default and should be filled
        assert result.data["fields"] == "open,high,low,close,volume"

    def test_scenario_source_inference(self, static_params):
        """Scenario2: Automatic inferenceData source"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--symbol",
                "600000.SH",
            ]
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "stock_daily"
        assert result.data["source"] == "tushare"  # Automatic inference
        assert result.data["symbol"] == "600000.SH"

    def test_scenario_index_daily_source_inference(self, static_params):
        """Scenario3: inferred as yahoo"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "index_daily",
                "--symbol",
                "^GSPC",
            ]
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "index_daily"
        assert result.data["source"] == "yahoo"  # inferred as yahoo
        assert result.data["symbol"] == "^GSPC"
        assert result.data["interval"] == "1d"  # default value

    def test_scenario_dynamic_params(self, static_params):
        """Scenario4:  parameter"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "tushare",
                "--symbol",
                "600000.SH",
                "--fields",
                "open,high,low,close",
            ]
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "stock_daily"
        assert result.data["source"] == "tushare"
        assert result.data["symbol"] == "600000.SH"
        assert result.data["fields"] == "open,high,low,close"

    def test_scenario_validation_failure(self, static_params):
        """Scenario5:  parameter validation"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "tushare",
                "--symbol",
                "invalid",  # Invalid format
            ]
        )

        assert result.success is False
        assert result.exit_code == 1
        assert result.error is not None
        assert "does not match pattern" in result.error

    def test_scenario_unsupported_combination(self, static_params):
        """Scenario6: yahoo + stock_daily combination (should succeed with a different format)"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "yahoo",
                "--symbol",
                "AAPL",  # yahoo uses a US ticker format
            ]
        )

        # yahoo supports stock_daily, so this should succeed
        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "stock_daily"
        assert result.data["source"] == "yahoo"
        assert result.data["symbol"] == "AAPL"
        assert result.data["interval"] == "1d"

    def test_scenario_missing_required(self, static_params):
        """Scenario7: Missing required parameter"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--source",
                "tushare",
            ]
        )

        assert result.success is False
        assert result.exit_code == 1
        assert result.error is not None
        assert "Missing required parameter" in result.error

    def test_scenario_year_expansion(self, static_params):
        """Scenario8:   start_date  end_date"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "tushare",
                "--symbol",
                "600000.SH",
                "--year",
                "2026",
            ]
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "stock_daily"
        assert result.data["source"] == "tushare"
        assert result.data["symbol"] == "600000.SH"
        assert result.data["start_date"] == "2026-01-01"
        assert result.data["end_date"] == "2026-12-31"

    def test_scenario_date_default(self, static_params):
        """Scenario9: Datedefault value"""
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "tushare",
                "--symbol",
                "600000.SH",
            ]
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["date"] == "2026-01-20"  # defaults to the last trading day

    def test_scenario_overwrite_flag(self, static_params):
        """Scenario10: overwrite """
        app = CliApp(params=static_params, prog="fetch.py")
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "tushare",
                "--symbol",
                "600000.SH",
                "--overwrite",
            ]
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["overwrite"] is True

    def test_scenario_help_with_context(self, static_params, capsys):
        """Scenario11:  with  help ( parameter) """
        app = CliApp(
            params=static_params,
            prog="fetch.py",
            available_sources=["tushare", "yahoo", "alphavantage"],
        )
        result = app.run(
            [
                "--type",
                "stock_daily",
                "--source",
                "tushare",
                "--help",
            ]
        )

        assert result.success is False
        assert result.exit_code == 0

        captured = capsys.readouterr()
        assert "Usage: fetch.py --source tushare [options]" in captured.out
        assert "--symbol" in captured.out
        assert "--fields" in captured.out
        assert "(dynamic)" in captured.out

    def test_scenario_help_global(self, static_params, capsys):
        """Scenario12: help ( no ) """
        app = CliApp(
            params=static_params,
            prog="fetch.py",
            available_sources=["tushare", "yahoo", "alphavantage"],
        )
        result = app.run(["--help"])

        assert result.success is False
        assert result.exit_code == 0

        captured = capsys.readouterr()
        assert "Usage: fetch.py [global options]" in captured.out
        assert "--type" in captured.out
        assert "--source" in captured.out
        assert "--date" in captured.out
        assert "Sources:" in captured.out
        assert "tushare, yahoo, alphavantage" in captured.out
