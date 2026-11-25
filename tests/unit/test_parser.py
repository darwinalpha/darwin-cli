# tests/test_cli/unit/test_parser.py

"""
Test parser.py - Command-line parser
"""

import pytest
from darwin_cli.parser import (
    ParserBuilder,
    build_parser,
    parse_args_with_meta,
)
from darwin_cli.base import Param, ParamInfo, ValidationRule


class TestParserBuilder:
    """Test ParserBuilder """

    def test_build_parser(self, sample_params):
        """Test """
        builder = ParserBuilder(sample_params, prog="test", description="Test ")
        parser = builder.build()

        assert parser.prog == "test"
        assert parser.description == "Test "

    def test_build_parser_no_help(self, sample_params):
        """Test  not  help"""
        builder = ParserBuilder(sample_params)
        parser = builder.build()

        # --help ignored (handled by the framework itself)
        actions = parser._actions
        action_dests = [a.dest for a in actions]
        assert "help" not in action_dests

    def test_build_kwargs_str(self):
        """Test str  parameter"""
        param = Param(name="name", type="str")
        builder = ParserBuilder([param])
        kwargs = builder._build_kwargs(param)

        assert kwargs["dest"] == "name"
        assert "type" not in kwargs
        assert "default" not in kwargs

    def test_build_kwargs_int(self):
        """Test int  parameter"""
        param = Param(name="count", type="int", default=10)
        builder = ParserBuilder([param])
        kwargs = builder._build_kwargs(param)

        assert kwargs["dest"] == "count"
        assert kwargs["type"] == int
        assert kwargs["default"] == 10

    def test_build_kwargs_float(self):
        """Test float  parameter"""
        param = Param(name="price", type="float", default=1.23)
        builder = ParserBuilder([param])
        kwargs = builder._build_kwargs(param)

        assert kwargs["dest"] == "price"
        assert kwargs["type"] == float
        assert kwargs["default"] == 1.23

    def test_build_kwargs_bool_store_true(self):
        """Test bool  - store_true"""
        param = Param(name="verbose", type="bool", default=False)
        builder = ParserBuilder([param])
        kwargs = builder._build_kwargs(param)

        assert kwargs["dest"] == "verbose"
        assert kwargs["action"].__name__ == "_TrackingStoreTrue"

    def test_build_kwargs_bool_store_false(self):
        """Test bool  - store_false"""
        param = Param(name="quiet", type="bool", default=True)
        builder = ParserBuilder([param])
        kwargs = builder._build_kwargs(param)

        assert kwargs["dest"] == "quiet"
        assert kwargs["action"].__name__ == "_TrackingStoreFalse"

    def test_build_kwargs_validation_rule_type(self):
        """Test type   ValidationRule"""
        rule = ValidationRule(pattern=r"^\d+$")
        param = Param(name="code", type=rule)
        builder = ParserBuilder([param])
        kwargs = builder._build_kwargs(param)

        # ValidationRule treated as str
        assert kwargs["dest"] == "code"
        assert "type" not in kwargs

    def test_build_kwargs_callable_default(self):
        """Test default   Callable"""

        def default_func(ctx):
            return "default"

        param = Param(name="name", type="str", default=default_func)
        builder = ParserBuilder([param])
        kwargs = builder._build_kwargs(param)

        # Callable The default is not passed to argparse
        assert "default" not in kwargs


class TestParseArgsWithMeta:
    """Test parse_args_with_meta"""

    def test_basic_parse(self, sample_params):
        """Test """
        result = parse_args_with_meta(
            sample_params,
            ["--type", "stock_daily", "--source", "tushare"],
        )

        assert "type" in result
        assert result["type"].value == "stock_daily"
        assert result["type"].from_source == "cli"
        assert result["type"].processed is False

        assert "source" in result
        assert result["source"].value == "tushare"
        assert result["source"].from_source == "cli"

    def test_parse_with_default(self, sample_params):
        """Test  with default value """
        params = [
            Param(name="type", type="str", required=True),
            Param(name="output", type="str", default="./data"),
        ]
        result = parse_args_with_meta(params, ["--type", "stock"])

        assert result["type"].value == "stock"
        assert result["type"].from_source == "cli"

        assert result["output"].value == "./data"
        assert result["output"].from_source == "default"

    def test_parse_with_callable_default(self):
        """Test a Callable default (not invoked yet)"""

        def default_func(ctx):
            return "computed"

        params = [Param(name="source", type="str", default=default_func)]
        result = parse_args_with_meta(params, [])

        assert result["source"].value is None
        assert result["source"].from_source == "default"

    def test_parse_unknown_args(self, sample_params):
        """Test  parameter"""
        result = parse_args_with_meta(
            sample_params,
            ["--type", "stock", "--unknown", "value", "--flag"],
        )

        assert result["type"].value == "stock"

        # Unknown args are recorded
        assert "unknown" in result
        assert result["unknown"].value == "value"
        assert result["unknown"].defined is False

        assert "flag" in result
        assert result["flag"].value is True
        assert result["flag"].defined is False

    def test_parse_help_detection(self, sample_params):
        """Test --help """
        result = parse_args_with_meta(
            sample_params,
            ["--type", "stock", "--help"],
        )

        assert "help" in result
        assert result["help"].value is True
        assert result["help"].from_source == "cli"

    def test_parse_help_with_hyphen(self, sample_params):
        """Test -h """
        result = parse_args_with_meta(
            sample_params,
            ["--type", "stock", "-h"],
        )

        assert "help" in result
        assert result["help"].value is True

    def test_parse_help_no_other_args(self, sample_params):
        """Test  has  --help"""
        result = parse_args_with_meta(sample_params, ["--help"])

        assert "help" in result
        assert result["help"].value is True

        # Other params keep their defaults
        for p in sample_params:
            if p.name != "help":
                assert p.name in result

    def test_parse_bool_store_true(self):
        """Test bool store_true  parameter"""
        params = [Param(name="verbose", type="bool")]
        result = parse_args_with_meta(params, ["--verbose"])

        assert result["verbose"].value is True
        assert result["verbose"].from_source == "cli"

    def test_parse_bool_store_false(self):
        """Test bool store_false  parameter"""
        params = [Param(name="quiet", type="bool", default=True)]
        result = parse_args_with_meta(params, ["--quiet"])

        assert result["quiet"].value is False
        assert result["quiet"].from_source == "cli"

    def test_parse_positional_args_ignored(self):
        """Test  parameter """
        params = [Param(name="type", type="str")]
        result = parse_args_with_meta(params, ["--type", "stock", "positional"])

        assert result["type"].value == "stock"
        # Positional args are not recorded
        assert len(result) == 1  #  has  type


class TestBuildParser:
    """Test build_parser """

    def test_build_parser(self, sample_params):
        """Test build_parser"""
        parser = build_parser(sample_params, prog="test", description="Test ")

        assert parser.prog == "test"
        assert parser.description == "Test "
