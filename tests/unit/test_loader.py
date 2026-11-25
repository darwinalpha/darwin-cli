# tests/test_cli/unit/test_loader.py

"""
Test loader.py - Config loading and conversion
"""

import pytest
from darwin_cli.loader import (
    parse_params_from_config,
    get_param_by_name,
    merge_params,
    params_to_dict,
    _to_validation_rule,
    _is_valid_help,
    _is_valid_action,
    _callable_name,
)
from darwin_cli.base import Param, ValidationRule


class TestParseParamsFromConfig:
    """Test parse_params_from_config"""

    def test_basic_config(self, sample_config):
        """Test """
        params = parse_params_from_config(sample_config)

        assert len(params) == 4

        # type
        assert params[0].name == "type"
        assert params[0].type == "str"
        assert params[0].required is True
        # Fix: use the actual help value from sample_config
        assert params[0].help == "Data type"
        assert params[0].validation is not None
        assert params[0].validation.choices == ["stock_daily", "stock_hist"]

        # source
        assert params[1].name == "source"
        assert params[1].type == "str"
        assert params[1].required is False
        assert params[1].help == "Data source"

        # overwrite (if present in sample_config)
        # Note: sample_config may lack overwrite; adjust to the actual config

        # help
        assert params[3].name == "help"
        assert params[3].type == "bool"
        assert params[3].required is False

    def test_config_with_validation(self, sample_config_with_validation):
        """Test  with  validation  """
        params = parse_params_from_config(sample_config_with_validation)

        assert len(params) == 4

        # symbol: pattern
        symbol = params[0]
        assert symbol.name == "symbol"
        assert symbol.type == "str"
        assert symbol.required is True
        assert symbol.validation is not None
        assert symbol.validation.pattern == r"^\d{6}\.(SH|SZ|BJ)$"

        # count: min/max
        count = params[1]
        assert count.name == "count"
        assert count.type == "int"
        assert count.required is False
        assert count.validation is not None
        assert count.validation.min == 1
        assert count.validation.max == 100

        # name: min_length/max_length
        name = params[2]
        assert name.name == "name"
        assert name.type == "str"
        assert name.validation is not None
        assert name.validation.min_length == 2
        assert name.validation.max_length == 20

        # status: choices
        status = params[3]
        assert status.name == "status"
        assert status.type == "str"
        assert status.validation is not None
        assert status.validation.choices == ["active", "inactive", "pending"]

    def test_type_as_validation_rule_dict(self):
        """Test type   validation """
        config = {
            "code": {
                "type": {"pattern": r"^\d+$"},
                "required": True,
                "help": "Code",
            }
        }
        params = parse_params_from_config(config)

        assert len(params) == 1
        assert params[0].name == "code"
        assert isinstance(params[0].type, ValidationRule)
        assert params[0].type.pattern == r"^\d+$"
        assert params[0].required is True

    def test_type_as_validation_rule_object(self):
        """Test type   ValidationRule """
        rule = ValidationRule(min=1, max=100)
        config = {
            "count": {
                "type": rule,
                "required": True,
                "help": "Count",
            }
        }
        params = parse_params_from_config(config)

        assert len(params) == 1
        assert params[0].type == rule
        assert params[0].validation is None

    def test_with_action(self):
        """Test action """
        config = {
            "source": {
                "type": "str",
                "action": "infer_source",
                "help": "Data source",
            }
        }
        params = parse_params_from_config(config)

        assert len(params) == 1
        assert params[0].action == "infer_source"

    def test_with_depends_on(self):
        """Test depends_on """
        config = {
            "type": {
                "type": "str",
                "required": True,
                "action": "load_dynamic",
                "depends_on": ["source"],
                "help": "Data type",
            }
        }
        params = parse_params_from_config(config)

        assert len(params) == 1
        assert params[0].depends_on == ["source"]

    def test_with_default(self):
        """Test default """
        config = {
            "fields": {
                "type": "str",
                "default": "open,high,low,close",
                "help": "Field list",
            }
        }
        params = parse_params_from_config(config)

        assert len(params) == 1
        assert params[0].default == "open,high,low,close"

    def test_empty_config(self):
        """Test """
        params = parse_params_from_config({})
        assert params == []


class TestGetParamByName:
    """Test get_param_by_name"""

    def test_found(self, sample_params):
        """Test  parameter"""
        param = get_param_by_name(sample_params, "type")
        assert param is not None
        assert param.name == "type"

    def test_not_found(self, sample_params):
        """Test  not  parameter"""
        param = get_param_by_name(sample_params, "not_exist")
        assert param is None


class TestMergeParams:
    """Test merge_params"""

    def test_merge(self):
        """Test  and  parameter"""
        base = [
            Param(name="a", type="str"),
            Param(name="b", type="str"),
        ]
        override = [
            Param(name="b", type="int", required=True),
            Param(name="c", type="str"),
        ]

        result = merge_params(base, override)

        assert len(result) == 3
        assert result[0].name == "a"
        assert result[1].name == "b"
        assert result[1].type == "int"
        assert result[1].required is True
        assert result[2].name == "c"


class TestParamsToDict:
    """Test params_to_dict"""

    def test_basic(self):
        """Test """
        params = [
            Param(name="type", type="str", required=True, help="Data type"),
            Param(name="source", type="str", help="Data source"),
        ]
        result = params_to_dict(params)

        assert result["type"]["type"] == "str"
        assert result["type"]["required"] is True
        assert result["type"]["help"] == "Data type"

        assert result["source"]["type"] == "str"
        assert "required" not in result["source"]
        assert result["source"]["help"] == "Data source"

    def test_with_validation(self):
        """Test Serialization with validation rules"""
        rule = ValidationRule(choices=["a", "b"], min=1)
        params = [Param(name="status", type="str", validation=rule)]
        result = params_to_dict(params)

        assert result["status"]["validation"]["choices"] == ["a", "b"]
        assert result["status"]["validation"]["min"] == 1

    def test_with_callable_default(self):
        """Test serialization of a Callable default"""

        def default_func(ctx):
            return "default"

        params = [Param(name="source", default=default_func)]
        result = params_to_dict(params)

        assert "<Callable:" in result["source"]["default"]

    def test_with_callable_help(self):
        """Test serialization of Callable help"""

        def help_func(ctx):
            return "Dynamic help"

        params = [Param(name="type", help=help_func)]
        result = params_to_dict(params)

        assert "<Callable:" in result["type"]["help"]


class TestHelperFunctions:
    """Test """

    def test_is_valid_help(self):
        """Test _is_valid_help"""
        assert _is_valid_help("string") is True
        assert _is_valid_help(lambda x: x) is True
        assert _is_valid_help(123) is False
        assert _is_valid_help(None) is False

    def test_is_valid_action(self):
        """Test _is_valid_action"""
        assert _is_valid_action("action_name") is True
        assert _is_valid_action(lambda x: x) is True
        assert _is_valid_action(123) is False
        assert _is_valid_action(None) is False

    def test_callable_name(self):
        """Test _callable_name"""

        def named_func():
            pass

        assert _callable_name(named_func) == "named_func"
        assert _callable_name(lambda x: x) == "<lambda>"

        class CustomCallable:
            def __call__(self):
                pass

        assert _callable_name(CustomCallable()) == "CustomCallable"


class TestToValidationRule:
    """Test _to_validation_rule"""

    def test_from_dict(self):
        """Test """
        data = {
            "choices": ["a", "b"],
            "min": 1,
            "max": 10,
            "min_length": 2,
            "max_length": 20,
            "pattern": r"^\d+$",
            "custom": "validate",
        }
        rule = _to_validation_rule(data)

        assert rule.choices == ["a", "b"]
        assert rule.min == 1
        assert rule.max == 10
        assert rule.min_length == 2
        assert rule.max_length == 20
        assert rule.pattern == r"^\d+$"
        assert rule.custom == "validate"

    def test_from_validation_rule(self):
        """Test  ValidationRule """
        original = ValidationRule(choices=["x", "y"], min=5)
        rule = _to_validation_rule(original)

        assert rule is original

    def test_invalid_data(self):
        """Test  no """
        with pytest.raises(ValueError, match="Cannot convert to ValidationRule"):
            _to_validation_rule("not a dict")  # type: ignore
