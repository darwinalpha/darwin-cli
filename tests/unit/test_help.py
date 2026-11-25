# tests/test_cli/unit/test_help.py

"""
Test help.py - Help text builder
"""

import pytest
from darwin_cli.help import HelpBuilder
from darwin_cli.base import Param, ParamInfo, ValidationRule


class TestHelpBuilder:
    """Test HelpBuilder """

    def test_init_defaults(self):
        """Test """
        builder = HelpBuilder()
        assert builder.prog == "main.py"
        assert builder.description == "CLI tool"

    def test_init_custom(self):
        """Test """
        builder = HelpBuilder(prog="myapp", description="My application")
        assert builder.prog == "myapp"
        assert builder.description == "My application"

    def test_build_global_help(self, sample_params):
        """Test help"""
        builder = HelpBuilder(prog="fetch.py", description="Data fetching tool")
        help_text = builder.build_global_help(
            static_params=sample_params,
            available_sources=["tushare", "yahoo"],
        )

        assert "Usage: fetch.py [global options]" in help_text
        assert "Data fetching tool" in help_text
        assert "--type" in help_text
        assert "--source" in help_text
        assert "--date" in help_text
        assert "--help" in help_text
        assert "Sources:" in help_text
        assert "tushare, yahoo" in help_text

    def test_build_global_help_with_error(self, sample_params):
        """Test  with  help"""
        builder = HelpBuilder(prog="fetch.py")
        help_text = builder.build_global_help(
            static_params=sample_params,
            error="Missing required parameter: --type",
        )

        assert "Error: Missing required parameter: --type" in help_text

    def test_build_global_help_without_sources(self, sample_params):
        """Test  no Data source help"""
        builder = HelpBuilder()
        help_text = builder.build_global_help(
            static_params=sample_params,
            available_sources=None,
        )

        assert "Sources:" not in help_text

    def test_build_scenario_help(self, sample_params):
        """Test Scenariohelp"""
        dynamic_params = [
            Param(name="symbol", type="str", required=True, help="Stock code"),
            Param(name="fields", type="str", default="*", help="Field list"),
        ]
        builder = HelpBuilder(prog="fetch.py")
        help_text = builder.build_scenario_help(
            static_params=sample_params,
            dynamic_params=dynamic_params,
            source="tushare",
        )

        assert "Usage: fetch.py --source tushare [options]" in help_text
        assert "Source: tushare" in help_text
        assert "Options:" in help_text
        assert "--symbol" in help_text
        assert "--fields" in help_text
        assert "(dynamic)" in help_text

    def test_build_scenario_help_without_source(self, sample_params):
        """Test  no  source  Scenariohelp"""
        dynamic_params = [Param(name="symbol", type="str")]
        builder = HelpBuilder(prog="fetch.py")
        help_text = builder.build_scenario_help(
            static_params=sample_params,
            dynamic_params=dynamic_params,
            source=None,
        )

        assert "Usage: fetch.py [options]" in help_text
        assert "Sources:" not in help_text

    def test_build_scenario_help_with_error(self, sample_params):
        """Test  with  Scenariohelp"""
        dynamic_params = [Param(name="symbol", type="str")]
        builder = HelpBuilder()
        help_text = builder.build_scenario_help(
            static_params=sample_params,
            dynamic_params=dynamic_params,
            source="tushare",
            error="Parameter --symbol has an invalid format",
        )

        assert "Error: Parameter --symbol has an invalid format" in help_text

    def test_build_error_help_with_source(self, sample_params):
        """Test  with  source  help (Scenariohelp) """
        dynamic_params = [Param(name="symbol", type="str")]
        # Fix: use fetch.py as prog
        builder = HelpBuilder(prog="fetch.py")
        help_text = builder.build_error_help(
            static_params=sample_params,
            dynamic_params=dynamic_params,
            source="tushare",
            error="Error message",
        )

        assert "Usage: fetch.py --source tushare [options]" in help_text
        assert "Error: Error message" in help_text

    def test_build_error_help_without_source(self, sample_params):
        """Test  no  source  help (help) """
        dynamic_params = [Param(name="symbol", type="str")]
        # Fix: use fetch.py as prog
        builder = HelpBuilder(prog="fetch.py")
        help_text = builder.build_error_help(
            static_params=sample_params,
            dynamic_params=dynamic_params,
            source=None,
            error="Error message",
            available_sources=["tushare", "yahoo"],
        )

        assert "Usage: fetch.py [global options]" in help_text
        assert "Error: Error message" in help_text
        assert "tushare, yahoo" in help_text


class TestHelpBuilderFormatParam:
    """Test HelpBuilder._format_param"""

    def test_format_param_str(self):
        """Test  str  parameter"""
        builder = HelpBuilder()
        param = Param(name="name", type="str", help="Name")
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "<str>" in result
        assert "(Name)" in result

    def test_format_param_int(self):
        """Test  int  parameter"""
        builder = HelpBuilder()
        param = Param(name="count", type="int", help="Count")
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "<int>" in result
        assert "(Count)" in result

    def test_format_param_bool(self):
        """Test  bool  parameter"""
        builder = HelpBuilder()
        param = Param(name="enabled", type="bool", help="Enabled")
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "(flag)" in result
        assert "(Enabled)" in result

    def test_format_param_required(self):
        """Test  parameter"""
        builder = HelpBuilder()
        param = Param(name="name", type="str", required=True, help="Name")
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "[required]" in result

    def test_format_param_default(self):
        """Test  with default value  parameter"""
        builder = HelpBuilder()
        param = Param(name="count", type="int", default=10, help="Count")
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "(default: 10)" in result

    def test_format_param_validation_choices(self):
        """Test  with  choices  validation  parameter"""
        builder = HelpBuilder()
        param = Param(
            name="status",
            type="str",
            validation=ValidationRule(choices=["active", "inactive"]),
            help="Status",
        )
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "choices: active, inactive" in result

    def test_format_param_validation_range(self):
        """Test  with  min/max  validation  parameter"""
        builder = HelpBuilder()
        param = Param(
            name="count",
            type="int",
            validation=ValidationRule(min=1, max=100),
            help="Count",
        )
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "range: 1-100" in result

    def test_format_param_validation_pattern(self):
        """Test  with  pattern  validation  parameter"""
        builder = HelpBuilder()
        param = Param(
            name="code",
            type="str",
            validation=ValidationRule(pattern=r"^\d+$"),
            help="Code",
        )
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "pattern: ^\\d+$" in result

    def test_format_param_type_validation_rule(self):
        """Test type   ValidationRule"""
        builder = HelpBuilder()
        rule = ValidationRule(pattern=r"^\d+$")
        param = Param(name="code", type=rule, help="Code")
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "<str>" in result
        assert "pattern: ^\\d+$" in result

    def test_format_param_dynamic_help(self):
        """Test Dynamic help (Callable) """

        def help_func(ctx):
            return "Dynamically generated help"

        builder = HelpBuilder()
        param = Param(name="type", type="str", help=help_func)
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "(Dynamically generated help)" in result

    def test_format_param_dynamic_help_with_context(self):
        """Test Dynamic help with """

        def help_func(ctx):
            type_value = ctx.get("type")
            if type_value and type_value.value:
                return f"Current type: {type_value.value}"
            return "Please specify a type"

        builder = HelpBuilder()
        param = Param(name="type", type="str", help=help_func)
        current_args = {"type": ParamInfo(value="stock_daily")}
        result = builder._format_param(param, current_args)

        assert "(Current type: stock_daily)" in result

    def test_format_param_dynamic_help_multiline(self):
        """Test Dynamic help"""

        def help_func(ctx):
            return "First line\nSecond line\nThird line"

        builder = HelpBuilder()
        param = Param(name="type", type="str", help=help_func)
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "First line" in result
        assert "Second line" in result
        assert "Third line" in result
        assert "    " in result  # Indented

    def test_format_param_help_error(self):
        """Test Dynamic help"""

        def help_func(ctx):
            raise ValueError("Help generation failed")

        builder = HelpBuilder()
        param = Param(name="type", type="str", help=help_func)
        current_args = {}
        result = builder._format_param(param, current_args)

        assert "(help generation failed: Help generation failed)" in result


class TestHelpBuilderGetValidation:
    """Test HelpBuilder._get_validation"""

    def test_get_validation_from_string_type(self):
        """Test  type  validation"""
        builder = HelpBuilder()
        rule = ValidationRule(choices=["a", "b"])
        param = Param(name="status", type="str", validation=rule)
        result = builder._get_validation(param)

        assert result == rule

    def test_get_validation_from_validation_rule_type(self):
        """Test  ValidationRule type  validation"""
        builder = HelpBuilder()
        rule = ValidationRule(choices=["a", "b"])
        param = Param(name="status", type=rule)
        result = builder._get_validation(param)

        assert result == rule
