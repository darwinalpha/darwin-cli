# tests/unit/test_source_tracking.py

"""Tests for reliable CLI-source tracking (--key=value, booleans, etc.)."""

from darwin_cli import CliApp, Param, parse_args_with_meta
from darwin_cli.parser import ParserBuilder


class TestEqualsSyntax:
    def test_key_equals_value_marked_cli(self):
        params = [Param(name="type", type="str")]
        result = parse_args_with_meta(params, ["--type=stock_daily"])
        assert result["type"].value == "stock_daily"
        assert result["type"].from_source == "cli"

    def test_multiple_equals_values(self):
        params = [Param(name="type", type="str"), Param(name="count", type="int", default=1)]
        result = parse_args_with_meta(params, ["--type=stock", "--count=5"])
        assert result["count"].value == 5
        assert result["count"].from_source == "cli"

    def test_space_separated_still_cli(self):
        params = [Param(name="type", type="str")]
        result = parse_args_with_meta(params, ["--type", "stock"])
        assert result["type"].from_source == "cli"


class TestDefaults:
    def test_static_default_source(self):
        params = [Param(name="count", type="int", default=3)]
        result = parse_args_with_meta(params, [])
        assert result["count"].value == 3
        assert result["count"].from_source == "default"

    def test_callable_default_not_resolved_at_parse(self):
        params = [Param(name="x", default=lambda ctx: "computed")]
        result = parse_args_with_meta(params, [])
        assert result["x"].value is None
        assert result["x"].from_source == "default"


class TestBooleanFlags:
    def test_store_true_when_passed(self):
        params = [Param(name="overwrite", type="bool")]
        result = parse_args_with_meta(params, ["--overwrite"])
        assert result["overwrite"].value is True
        assert result["overwrite"].from_source == "cli"

    def test_store_false_when_passed(self):
        params = [Param(name="quiet", type="bool", default=True)]
        result = parse_args_with_meta(params, ["--quiet"])
        assert result["quiet"].value is False
        assert result["quiet"].from_source == "cli"

    def test_unpassed_flag_is_default(self):
        params = [Param(name="overwrite", type="bool")]
        result = parse_args_with_meta(params, [])
        assert result["overwrite"].from_source == "default"


class TestConstraintWithEqualsSyntax:
    def test_exclusive_detected_with_equals(self):
        app = CliApp(
            params=[Param(name="date"), Param(name="year")],
            constraints=[{"rule": "mutually_exclusive", "params": ["date", "year"]}],
        )
        result = app.run(["--date=2026-01-01", "--year=2026"])
        assert result.outcome == "error"
        assert "mutually exclusive" in result.error

    def test_required_satisfied_via_equals(self):
        app = CliApp(params=[Param(name="name", required=True)])
        result = app.run(["--name=Alice"])
        assert result.outcome == "ok"
        assert result.data["name"] == "Alice"
