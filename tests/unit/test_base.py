# tests/test_cli/unit/test_base.py

"""
Test base.py - Core data types
"""

import pytest
from darwin_cli.base import (
    Param,
    ParamInfo,
    ValidationRule,
    ActionResult,
    CliResult,
)


class TestValidationRule:
    """Test ValidationRule """

    def test_all_fields(self):
        """Test   has """
        rule = ValidationRule(
            choices=["a", "b"],
            min=1,
            max=10,
            min_length=2,
            max_length=20,
            pattern=r"^\d+$",
            custom="validate_custom",
        )
        assert rule.choices == ["a", "b"]
        assert rule.min == 1
        assert rule.max == 10
        assert rule.min_length == 2
        assert rule.max_length == 20
        assert rule.pattern == r"^\d+$"
        assert rule.custom == "validate_custom"

    def test_default_values(self):
        """Test default value"""
        rule = ValidationRule()
        assert rule.choices is None
        assert rule.min is None
        assert rule.max is None
        assert rule.min_length is None
        assert rule.max_length is None
        assert rule.pattern is None
        assert rule.custom is None

    def test_partial_fields(self):
        """Test """
        rule = ValidationRule(choices=["x", "y"], min=5)
        assert rule.choices == ["x", "y"]
        assert rule.min == 5
        assert rule.max is None


class TestParam:
    """Test Param """

    def test_minimal_param(self):
        """Test """
        param = Param(name="test")
        assert param.name == "test"
        assert param.type == "str"
        assert param.required is False
        assert param.default is None
        assert param.help == ""
        assert param.action is None
        assert param.validation is None
        assert param.depends_on is None

    def test_full_param(self):
        """Test """
        rule = ValidationRule(min=1, max=100)
        param = Param(
            name="count",
            type="int",
            required=True,
            default=10,
            help="Count",
            action="validate_count",
            validation=rule,
            depends_on=["source"],
        )
        assert param.name == "count"
        assert param.type == "int"
        assert param.required is True
        assert param.default == 10
        assert param.help == "Count"
        assert param.action == "validate_count"
        assert param.validation == rule
        assert param.depends_on == ["source"]

    def test_type_validation_rule(self):
        """Test type   ValidationRule"""
        rule = ValidationRule(pattern=r"^\d+$")
        param = Param(name="code", type=rule)
        assert param.type == rule
        assert param.name == "code"

    def test_help_callable(self):
        """Test help   Callable"""

        def help_func(ctx):
            return "Dynamic help"

        param = Param(name="dynamic", help=help_func)
        assert callable(param.help)
        assert param.help(None) == "Dynamic help"

    def test_action_callable(self):
        """Test action   Callable"""

        def action_func(value, ctx):
            return {"result": value}

        param = Param(name="dynamic", action=action_func)
        assert callable(param.action)
        assert param.action("test", {}) == {"result": "test"}


class TestParamInfo:
    """Test ParamInfo """

    def test_all_fields(self):
        """Test   has """
        info = ParamInfo(
            value="test",
            defined=True,
            from_source="cli",
            processed=True,
        )
        assert info.value == "test"
        assert info.defined is True
        assert info.from_source == "cli"
        assert info.processed is True

    def test_default_values(self):
        """Test default value"""
        info = ParamInfo(value=None)
        assert info.value is None
        assert info.defined is False
        assert info.from_source == "cli"
        assert info.processed is False


class TestActionResult:
    """Test ActionResult """

    def test_empty(self):
        """Test """
        result = ActionResult()
        assert result.values == {}
        assert result.params == []

    def test_with_values(self):
        """Test  with  values"""
        result = ActionResult(values={"source": "tushare", "date": "2026-01-20"})
        assert result.values["source"] == "tushare"
        assert result.values["date"] == "2026-01-20"
        assert result.params == []

    def test_with_params(self):
        """Test  with  params"""
        param = Param(name="symbol", type="str", required=True)
        result = ActionResult(params=[param])
        assert result.params == [param]
        assert result.values == {}

    def test_with_both(self):
        """Test  with  values  params"""
        param = Param(name="symbol", type="str")
        result = ActionResult(
            values={"source": "tushare"},
            params=[param],
        )
        assert result.values["source"] == "tushare"
        assert result.params == [param]


class TestCliResult:
    """Test CliResult """

    def test_ok(self):
        """Test ok """
        result = CliResult.ok({"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None
        assert result.exit_code == 0

    def test_fail(self):
        """Test fail """
        result = CliResult.fail("Error message")
        assert result.success is False
        assert result.data is None
        assert result.error == "Error message"
        assert result.exit_code == 1

    def test_fail_with_code(self):
        """Test fail  with """
        result = CliResult.fail("Error message", exit_code=2)
        assert result.success is False
        assert result.error == "Error message"
        assert result.exit_code == 2

    def test_custom_creation(self):
        """Test """
        result = CliResult(
            success=True,
            data={"key": "value"},
            error=None,
            exit_code=0,
        )
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None
        assert result.exit_code == 0
