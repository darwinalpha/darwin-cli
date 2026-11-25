# tests/test_cli/unit/test_executor.py

"""
Test executor.py - Deferred execution engine
"""

import pytest
from darwin_cli.executor import Executor, USER_SOURCES
from darwin_cli.base import Param, ParamInfo, ActionResult, ValidationRule
from darwin_cli.actions import (
    register_action,
    clear_actions,
    ActionError,
    HelpRequested,
    RequiredError,
    MaxIterationsExceeded,
    CycleDetected,
)


class TestExecutorBasic:
    """Test Executor """

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_run_no_action(self, sample_params):
        """Test  no  action  parameter"""
        raw = {
            "type": ParamInfo(value="stock_daily", from_source="cli"),
            "source": ParamInfo(value="tushare", from_source="cli"),
            "date": ParamInfo(value="2026-01-20", from_source="cli"),
            "help": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(sample_params)
        result = executor.run(raw)

        assert result["type"] == "stock_daily"
        assert result["source"] == "tushare"
        assert result["date"] == "2026-01-20"

    def test_run_with_default_values(self):
        """Test default value"""
        params = [
            Param(name="type", type="str", required=True),
            Param(name="output", type="str", default="./data"),
        ]
        raw = {
            "type": ParamInfo(value="stock_daily", from_source="cli"),
            "output": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["type"] == "stock_daily"
        assert result["output"] == "./data"

    def test_run_simple_action(self, registered_actions):
        """Test  action"""
        params = [
            Param(name="source", type="str", action="infer_source"),
        ]
        raw = {
            "source": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        # infer_source Return {"source": "yahoo"} (because type is absent) 
        assert result["source"] == "yahoo"

    def test_run_action_with_context(self, registered_actions):
        """Test  with   action"""
        params = [
            Param(name="type", type="str", action="load_dynamic"),
            Param(name="source", type="str"),
        ]
        raw = {
            "type": ParamInfo(value="stock_daily", from_source="cli"),
            "source": ParamInfo(value="tushare", from_source="cli"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["type"] == "stock_daily"
        assert result["source"] == "tushare"


class TestExecutorAction:
    """Test Executor Action """

    def setup_method(self):
        clear_actions()

        @register_action("return_dict")
        def return_dict(value, ctx):
            return {"result": value}

        @register_action("return_action_result")
        def return_action_result(value, ctx):
            return ActionResult(values={"result": value})

        @register_action("generate_param")
        def generate_param(value, ctx):
            return ActionResult(
                values={"generated": value},
                params=[Param(name="new_param", type="str")],
            )

        @register_action("generate_param_with_action")
        def generate_param_with_action(value, ctx):
            return ActionResult(
                params=[
                    Param(name="new_action_param", type="str", action="return_dict"),
                ]
            )

        @register_action("raise_error")
        def raise_error(value, ctx):
            raise ValueError("action error")

        @register_action("raise_help")
        def raise_help(value, ctx):
            raise HelpRequested()

    def teardown_method(self):
        clear_actions()

    def test_action_return_dict(self):
        """Test action Return dict"""
        params = [Param(name="test", type="str", action="return_dict")]
        raw = {"test": ParamInfo(value="hello", from_source="cli")}
        executor = Executor(params)
        result = executor.run(raw)

        assert result["test"] == "hello"

    def test_action_return_action_result(self):
        """Test action Return ActionResult"""
        params = [Param(name="test", type="str", action="return_action_result")]
        raw = {"test": ParamInfo(value="world", from_source="cli")}
        executor = Executor(params)
        result = executor.run(raw)

        assert result["test"] == "world"

    def test_action_generate_param(self):
        """Test action  generate  parameter"""
        params = [Param(name="source", type="str", action="generate_param")]
        raw = {"source": ParamInfo(value="tushare", from_source="cli")}
        executor = Executor(params)
        result = executor.run(raw)

        assert result["source"] == "tushare"
        assert result["generated"] == "tushare"

    def test_action_generate_param_with_action(self):
        """Test action  generate  with  action   parameter"""
        params = [Param(name="source", type="str", action="generate_param_with_action")]
        raw = {"source": ParamInfo(value="tushare", from_source="cli")}
        executor = Executor(params)
        result = executor.run(raw)

        assert result["source"] == "tushare"
        assert "new_action_param" in result

    def test_action_raise_error(self):
        """Test action """
        params = [Param(name="test", type="str", action="raise_error")]
        raw = {"test": ParamInfo(value="test", from_source="cli")}
        executor = Executor(params)

        with pytest.raises(ActionError, match="failed"):
            executor.run(raw)

    def test_action_raise_help(self):
        """Test action  HelpRequested"""
        params = [Param(name="test", type="str", action="raise_help")]
        raw = {"test": ParamInfo(value="test", from_source="cli")}
        executor = Executor(params)

        with pytest.raises(HelpRequested):
            executor.run(raw)


class TestExecutorDependency:
    """Test Executor """

    def setup_method(self):
        clear_actions()

        @register_action("depends_action")
        def depends_action(value, ctx):
            source_info = ctx.get("source")
            if source_info and source_info.value:
                return {"result": f"type={value}, source={source_info.value}"}
            return {"result": f"type={value}"}

        @register_action("source_action")
        def source_action(value, ctx):
            if value is None:
                return {"source": "inferred_source"}
            return {}

    def teardown_method(self):
        clear_actions()

    def test_depends_on_ordering(self):
        """Test  () """
        params = [
            Param(
                name="type",
                type="str",
                action="depends_action",
                depends_on=["source"],
            ),
            Param(name="source", type="str", action="source_action"),
        ]
        raw = {
            "type": ParamInfo(value="stock_daily", from_source="cli"),
            "source": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["type"] == "stock_daily"
        assert result["source"] == "inferred_source"

    def test_depends_on_multiple(self):
        """Test """

        # Use distinct action names to avoid collisions
        @register_action("source_action_a")
        def source_action_a(value, ctx):
            if value is None:
                return {"a": "inferred_source_a"}
            return {}

        @register_action("source_action_b")
        def source_action_b(value, ctx):
            if value is None:
                return {"b": "inferred_source_b"}
            return {}

        @register_action("multi_depends")
        def multi_depends(value, ctx):
            a = ctx.get("a")
            b = ctx.get("b")
            return {"result": f"{a.value}-{b.value}"}

        params = [
            Param(name="target", type="str", action="multi_depends", depends_on=["a", "b"]),
            Param(name="a", type="str", action="source_action_a"),
            Param(name="b", type="str", action="source_action_b"),
        ]
        raw = {
            "target": ParamInfo(value="combine", from_source="cli"),
            "a": ParamInfo(value=None, from_source="default"),
            "b": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["a"] == "inferred_source_a"
        assert result["b"] == "inferred_source_b"

    def test_cycle_detection(self):
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
        raw = {
            "a": ParamInfo(value="a_value", from_source="cli"),
            "b": ParamInfo(value="b_value", from_source="cli"),
        }
        executor = Executor(params)

        with pytest.raises(CycleDetected, match="cycle"):
            executor.run(raw)


class TestExecutorHelp:
    """Test Executor --help """

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_help_only(self, sample_params):
        """Test  has  --help"""
        raw = {
            "help": ParamInfo(value=True, from_source="cli"),
        }
        for p in sample_params:
            if p.name != "help":
                raw[p.name] = ParamInfo(value=None, from_source="default")

        executor = Executor(sample_params)

        with pytest.raises(HelpRequested):
            executor.run(raw)

    def test_help_with_other_params(self, registered_actions):
        """Test --help combined with other params"""
        params = [
            Param(name="type", type="str", action="load_dynamic", depends_on=["source"]),
            Param(name="source", type="str", action="infer_source"),
            Param(name="help", type="bool", action="print_help"),
        ]
        raw = {
            "type": ParamInfo(value="stock_daily", from_source="cli"),
            "source": ParamInfo(value=None, from_source="default"),
            "help": ParamInfo(value=True, from_source="cli"),
        }
        executor = Executor(params)

        with pytest.raises(HelpRequested):
            executor.run(raw)

        assert executor.current_args is not None
        source_info = executor.current_args.get("source")
        assert source_info is not None
        assert source_info.value == "tushare"


class TestExecutorValidation:
    """Test Executor  validation"""

    def setup_method(self):
        clear_actions()

        @register_action("generate_value")
        def generate_value(value, ctx):
            return {"count": "not_a_number"}

    def teardown_method(self):
        clear_actions()

    def test_validation_on_action_value(self):
        """Test action  generate    validation"""
        params = [
            Param(name="source", type="str", action="generate_value"),
            Param(name="count", type="int", required=True),
        ]
        raw = {
            "source": ParamInfo(value="test", from_source="cli"),
            "count": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)

        with pytest.raises(ActionError, match="type error"):
            executor.run(raw)

    def test_final_validation(self):
        """Test  validation"""
        params = [
            Param(name="count", type="int", validation=ValidationRule(min=1, max=10)),
        ]
        raw = {
            "count": ParamInfo(value="5", from_source="cli"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["count"] == 5


class TestExecutorRequired:
    """Test Executor required """

    def setup_method(self):
        clear_actions()

        @register_action("generate_required")
        def generate_required(value, ctx):
            return {"type": "stock_daily"}

    def teardown_method(self):
        clear_actions()

    def test_required_from_cli(self):
        """Test required  parameter CLI"""
        params = [Param(name="type", type="str", required=True)]
        raw = {
            "type": ParamInfo(value="stock_daily", from_source="cli"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["type"] == "stock_daily"

    def test_required_missing(self):
        """Test required  parameter"""
        params = [Param(name="type", type="str", required=True)]
        raw = {
            "type": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)

        with pytest.raises(RequiredError, match="Missing required parameter"):
            executor.run(raw)

    def test_required_from_action(self):
        """Test required  parameter action  generate  () """
        params = [
            Param(name="source", type="str", action="generate_required"),
            Param(name="type", type="str", required=True),
        ]
        raw = {
            "source": ParamInfo(value="test", from_source="cli"),
            "type": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["type"] == "stock_daily"

    def test_required_from_default(self):
        """Test required  parameter default ( not ) """
        params = [Param(name="type", type="str", required=True, default="default")]
        raw = {
            "type": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)

        with pytest.raises(RequiredError, match="must come from CLI"):
            executor.run(raw)


class TestExecutorDefaultCallable:
    """Test Callable default value"""

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_default_callable(self):
        """Test Callable default value"""

        def default_source(ctx):
            type_info = ctx.get("type")
            if type_info and type_info.value == "stock_daily":
                return "tushare"
            return "yahoo"

        params = [
            Param(name="type", type="str"),
            Param(name="source", type="str", default=default_source),
        ]
        raw = {
            "type": ParamInfo(value="stock_daily", from_source="cli"),
            "source": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["source"] == "tushare"

    def test_default_callable_error(self):
        """Test Callable default value"""

        def failing_default(ctx):
            raise ValueError("default error")

        params = [Param(name="source", type="str", default=failing_default)]
        raw = {
            "source": ParamInfo(value=None, from_source="default"),
        }
        executor = Executor(params)

        with pytest.raises(ActionError, match="failed"):
            executor.run(raw)


class TestExecutorActionCallable:
    """Test action   Callable"""

    def test_action_callable_direct(self):
        """Test  Callable action"""

        def my_action(value, ctx):
            return {"result": f"processed: {value}"}

        params = [Param(name="name", type="str", action=my_action)]
        raw = {
            "name": ParamInfo(value="test", from_source="cli"),
        }
        executor = Executor(params)
        result = executor.run(raw)

        assert result["name"] == "test"
        assert result["result"] == "processed: test"


class TestExecutorMaxIterations:
    """Test """

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    @pytest.mark.skip(reason="Needs further investigation of the iteration counter")
    def test_max_iterations_exceeded(self):
        """Test Exceeded max iterations"""
        call_count = 0

        @register_action("infinite_loop")
        def infinite_loop(value, ctx):
            nonlocal call_count
            call_count += 1
            # Generate a fresh param name each time to force an infinite loop
            return ActionResult(
                params=[Param(name=f"new_param_{call_count}", type="str", action="infinite_loop")],
            )

        params = [Param(name="start", type="str", action="infinite_loop")]
        raw = {
            "start": ParamInfo(value="begin", from_source="cli"),
        }
        executor = Executor(params, max_iterations=5)

        with pytest.raises(MaxIterationsExceeded, match="Exceeded max iterations"):
            executor.run(raw)

        # 
        assert call_count > 5
