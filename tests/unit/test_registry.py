# tests/unit/test_registry.py

"""Tests for per-app ActionRegistry isolation and CliResult.outcome."""

import pytest

from darwin_cli import (
    ActionError,
    ActionRegistry,
    CliApp,
    CliResult,
    Param,
    register_action,
)


class TestActionRegistry:
    def test_isolated_registration(self):
        reg_a = ActionRegistry()
        reg_b = ActionRegistry()

        @register_action("greet", registry=reg_a)
        def greet_a(value, ctx):
            return {"result": "A"}

        @register_action("greet", registry=reg_b)
        def greet_b(value, ctx):
            return {"result": "B"}

        assert reg_a.get("greet")(None, {}) == {"result": "A"}
        assert reg_b.get("greet")(None, {}) == {"result": "B"}
        assert "greet" not in __import__("darwin_cli").GLOBAL_ACTIONS

    def test_duplicate_in_same_registry_raises(self):
        reg = ActionRegistry()

        @register_action("dup", registry=reg)
        def one(value, ctx):
            return {}

        with pytest.raises(ValueError, match="already registered"):

            @register_action("dup", registry=reg)
            def two(value, ctx):
                return {}

    def test_app_uses_injected_registry(self):
        reg = ActionRegistry()

        @register_action("infer", registry=reg)
        def infer(value, ctx):
            return {"source": "tushare"}

        app = CliApp(
            params=[
                Param(name="type", type="str", required=True, action="infer"),
                Param(name="source", type="str"),
            ],
            registry=reg,
        )
        result = app.run(["--type", "stock_daily"])
        assert result.outcome == "ok"
        assert result.data["source"] == "tushare"

    def test_unregistered_action_in_isolated_registry_fails(self):
        reg = ActionRegistry()
        app = CliApp(
            params=[Param(name="type", action="not_here")],
            registry=reg,
        )
        result = app.run(["--type", "x"])
        assert result.outcome == "error"
        assert "not registered" in result.error


class TestCliResultOutcome:
    def test_factories(self):
        ok = CliResult.ok({"a": 1})
        assert ok.outcome == "ok"
        assert ok.success is True
        assert ok.exit_code == 0

        help_result = CliResult.help()
        assert help_result.outcome == "help"
        assert help_result.success is False
        assert help_result.exit_code == 0

        fail = CliResult.fail("bad")
        assert fail.outcome == "error"
        assert fail.success is False
        assert fail.exit_code == 1

    def test_help_run_outcome(self, capsys):
        app = CliApp(params=[Param(name="x")], prog="t.py")
        result = app.run(["--help"])
        assert result.outcome == "help"
        assert result.success is False
        assert result.exit_code == 0
        assert "Usage:" in capsys.readouterr().out
