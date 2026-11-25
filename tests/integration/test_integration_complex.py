# tests/test_cli/integration/test_integration_complex.py

"""
Integration tests: complex scenarios
multi-level dependencies, chained Actions, cycle detection
"""

import pytest
from darwin_cli.app import CliApp
from darwin_cli.base import Param, ValidationRule, ActionResult
from darwin_cli.actions import (
    register_action,
    clear_actions,
    ActionError,
    CycleDetected,
    RequiredError,
    MaxIterationsExceeded,
)


class TestIntegrationComplex:
    """Complex scenario integration tests"""

    @pytest.fixture(autouse=True)
    def setup_actions(self):
        """Test   action"""
        clear_actions()

        # ============================================================
        # Multi-level dependent Actions
        # ============================================================
        @register_action("level1")
        def level1_action(value, ctx):
            """Level 1: choose the source from region"""
            region = ctx.get("region")
            if region and region.value == "china":
                return {"source": "tushare"}
            return {"source": "yahoo"}

        @register_action("level2")
        def level2_action(value, ctx):
            """Level 2: load params from source and set values"""
            source = ctx.get("source")
            if source and source.value == "tushare":
                return ActionResult(
                    values={"token": "tushare_token_123"},
                    params=[
                        Param(name="token", type="str", required=True, help="Tushare Token"),
                    ],
                )
            return ActionResult(
                values={"api_key": "api_key_123"},
                params=[
                    Param(name="api_key", type="str", required=True, help="API Key"),
                ],
            )

        @register_action("level3")
        def level3_action(value, ctx):
            """Level 3: add extra params from type"""
            return ActionResult(
                params=[
                    Param(name="extra_param", type="str", default="extra", help="Extra parameter"),
                ]
            )

        # ============================================================
        # Chained Actions (A → B → C) 
        # ============================================================
        @register_action("chain_a")
        def chain_a(value, ctx):
            """A  generate  B"""
            return ActionResult(
                values={"b": "generated_b"},
                params=[Param(name="b", type="str", action="chain_b")],
            )

        @register_action("chain_b")
        def chain_b(value, ctx):
            """B  generate  C"""
            return ActionResult(
                values={"c": "generated_c"},
                params=[Param(name="c", type="str", action="chain_c")],
            )

        @register_action("chain_c")
        def chain_c(value, ctx):
            """C  generate """
            return {"result": "chain_complete"}

        # ============================================================
        # Conditionally dependent Action
        # ============================================================
        @register_action("conditional")
        def conditional_action(value, ctx):
            """Decide whether to generate params based on a condition"""
            mode = ctx.get("mode")
            if mode and mode.value == "full":
                return ActionResult(
                    values={"full_param": "full_mode_value"},
                    params=[
                        Param(name="full_param", type="str", required=True, help="Full-mode params"),
                    ],
                )
            return {}

        # ============================================================
        # Action for missing-dependency tests
        # ============================================================
        @register_action("needs_source")
        def needs_source(value, ctx):
            source = ctx.get("source")
            if not source or source.value is None:
                raise RequiredError("--source Must be provided")
            return {"result": "ok"}

        # ============================================================
        # Action that generates a required param
        # ============================================================
        @register_action("generate_required")
        def generate_required(value, ctx):
            return ActionResult(
                values={"generated_token": "token_123"},
                params=[
                    Param(name="generated_token", type="str", required=True, help="Generated token"),
                ],
            )

        yield
        clear_actions()

    # ============================================================
    # Test Scenario
    # ============================================================

    def test_multi_level_dependencies(self):
        """Test : region → source → token"""
        params = [
            Param(
                name="region",
                type="str",
                required=True,
                action="level1",
                help="Region",
            ),
            Param(
                name="source",
                type="str",
                action="level2",
                help="Data source",
            ),
        ]

        app = CliApp(params=params, prog="test")
        result = app.run(["--region", "china"])

        assert result.success is True
        assert result.data is not None
        assert result.data["region"] == "china"
        assert result.data["source"] == "tushare"
        assert result.data["token"] == "tushare_token_123"

    def test_chain_reaction(self):
        """Test  should  (A → B → C) """
        params = [
            Param(
                name="start",
                type="str",
                required=True,
                action="chain_a",
                help="Start",
            ),
        ]

        app = CliApp(params=params, prog="test")
        result = app.run(["--start", "begin"])

        assert result.success is True
        assert result.data is not None
        assert result.data["start"] == "begin"
        assert result.data["b"] == "generated_b"
        assert result.data["c"] == "generated_c"
        assert result.data["result"] == "chain_complete"

    def test_conditional_dependency(self):
        """Test conditional deps: simple mode adds none, full mode does"""
        params = [
            Param(
                name="mode",
                type="str",
                required=True,
                validation=ValidationRule(choices=["simple", "full"]),
                help="Mode",
            ),
            Param(
                name="full_param",
                type="str",
                action="conditional",
                help="Full-mode params",
            ),
        ]

        # Scenario1: simple Mode → full_param should be None (key exists, no value)
        app = CliApp(params=params, prog="test")
        result = app.run(["--mode", "simple"])

        assert result.success is True
        assert result.data is not None
        assert result.data["mode"] == "simple"
        # conditional action Return {}, full_param Stay None
        assert result.data["full_param"] is None

        # Scenario2: full Mode → full_param should exist with a value
        app = CliApp(params=params, prog="test")
        result = app.run(["--mode", "full"])

        assert result.success is True
        assert result.data is not None
        assert result.data["mode"] == "full"
        assert result.data["full_param"] == "full_mode_value"

    def test_complex_workflow(self):
        """Test : region → source → token → Final result"""
        params = [
            Param(
                name="region",
                type="str",
                required=True,
                action="level1",
                help="Region",
            ),
            Param(
                name="source",
                type="str",
                action="level2",
                help="Data source",
            ),
            Param(
                name="token",
                type="str",
                required=True,
                help="Token (produced by level2) ",
            ),
        ]

        app = CliApp(params=params, prog="test")
        result = app.run(["--region", "china"])

        assert result.success is True
        assert result.data is not None
        assert result.data["region"] == "china"
        assert result.data["source"] == "tushare"
        assert result.data["token"] == "tushare_token_123"

    def test_cycle_detection_integration(self):
        """Test cycle"""

        @register_action("cycle_a")
        def cycle_a(value, ctx):
            return {}

        @register_action("cycle_b")
        def cycle_b(value, ctx):
            return {}

        params = [
            Param(name="a", type="str", action="cycle_a", depends_on=["b"]),
            Param(name="b", type="str", action="cycle_b", depends_on=["a"]),
        ]

        app = CliApp(params=params, prog="test", max_iterations=10)
        result = app.run(["--a", "value_a", "--b", "value_b"])

        assert result.success is False
        assert result.exit_code == 1
        assert result.error is not None
        # may raise CycleDetected or MaxIterationsExceeded
        assert "cycle" in result.error or "Exceeded max iterations" in result.error

    def test_missing_dependency(self):
        """Test : target  source,  source """
        params = [
            Param(
                name="target",
                type="str",
                action="needs_source",
                depends_on=["source"],
                help="Target",
            ),
            Param(
                name="source",
                type="str",
                required=False,
                help="Data source",
            ),
        ]

        app = CliApp(params=params, prog="test")
        result = app.run(["--target", "test"])

        assert result.success is False
        assert result.exit_code == 1
        assert result.error is not None
        # should report Missing required parameter
        assert "Missing required parameter" in result.error or "failed" in result.error

    def test_action_generated_required(self):
        """Test Action  generate  required  parameter and """
        params = [
            Param(
                name="source",
                type="str",
                action="generate_required",
                help="Data source",
            ),
        ]

        app = CliApp(params=params, prog="test")
        result = app.run(["--source", "tushare"])

        assert result.success is True
        assert result.data is not None
        assert result.data["source"] == "tushare"
        assert result.data["generated_token"] == "token_123"

    def test_config_dict_init(self):
        """Initialize from a config dict and run a complex scenario"""
        config = {
            "type": {
                "type": "str",
                "required": True,
                "action": "level2",
                "depends_on": ["source"],
                "validation": {"choices": ["stock_daily", "index_daily"]},
                "help": "Data type",
            },
            "source": {
                "type": "str",
                "required": False,
                "action": "level1",
                "help": "Data source",
            },
            "region": {
                "type": "str",
                "required": True,
                "help": "Region",
            },
        }

        app = CliApp(params=config, prog="test")
        result = app.run(["--region", "china", "--type", "stock_daily"])

        assert result.success is True
        assert result.data is not None
        assert result.data["region"] == "china"
        assert result.data["type"] == "stock_daily"
        assert result.data["source"] == "tushare"
        # level2 returns token for tushare, not api_key
        assert result.data["token"] == "tushare_token_123"
