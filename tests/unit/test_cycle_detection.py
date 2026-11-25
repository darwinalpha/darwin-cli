# tests/unit/test_cycle_detection.py

"""Tests for true dependency-graph cycle detection."""

import pytest

from darwin_cli import (
    ActionError,
    ActionResult,
    CycleDetected,
    Param,
    clear_actions,
    register_action,
)
from darwin_cli.executor import Executor
from darwin_cli.base import ParamInfo


class TestTrueCycleDetection:
    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_two_node_cycle(self):
        @register_action("a_action")
        def a_action(value, ctx):
            return {}

        @register_action("b_action")
        def b_action(value, ctx):
            return {}

        params = [
            Param(name="a", action="a_action", depends_on=["b"]),
            Param(name="b", action="b_action", depends_on=["a"]),
        ]
        raw = {
            "a": ParamInfo(value="va", from_source="cli"),
            "b": ParamInfo(value="vb", from_source="cli"),
        }
        executor = Executor(params, max_iterations=50)
        with pytest.raises(CycleDetected, match="Dependency cycle detected"):
            executor.run(raw)

    def test_three_node_cycle(self):
        params = [
            Param(name="a", depends_on=["b"]),
            Param(name="b", depends_on=["c"]),
            Param(name="c", depends_on=["a"]),
        ]
        raw = {name: ParamInfo(value="v", from_source="cli") for name in ("a", "b", "c")}
        executor = Executor(params, max_iterations=50)
        with pytest.raises(CycleDetected):
            executor.run(raw)

    def test_acyclic_chain_ok(self):
        params = [
            Param(name="a", depends_on=["b"]),
            Param(name="b", depends_on=["c"]),
            Param(name="c"),
        ]
        raw = {name: ParamInfo(value="v", from_source="cli") for name in ("a", "b", "c")}
        executor = Executor(params)
        result = executor.run(raw)
        assert result["a"] == "v"

    def test_self_cycle(self):
        params = [Param(name="a", depends_on=["a"])]
        raw = {"a": ParamInfo(value="v", from_source="cli")}
        executor = Executor(params)
        with pytest.raises(CycleDetected):
            executor.run(raw)
