# tests/unit/test_constraints.py

"""Tests for the cross-parameter constraint engine."""

import pytest

from darwin_cli import (
    ActionError,
    CliApp,
    ConstraintError,
    Param,
    check_constraint,
    check_constraints,
    parse_constraints,
)
from darwin_cli.base import Constraint, ParamInfo


def args(**values):
    """Build a current_args dict; keys with None are treated as absent."""
    return {k: ParamInfo(value=v, defined=True, from_source="cli") for k, v in values.items()}


class TestConstraintParsing:
    def test_parse_from_dicts(self):
        result = parse_constraints(
            [
                {"rule": "mutually_exclusive", "params": ["a", "b"]},
                {"rule": "requires", "param": "x", "requires": "y", "message": "custom"},
            ]
        )
        assert len(result) == 2
        assert result[0].rule == "mutually_exclusive"
        assert result[0].params == ["a", "b"]
        assert result[1].message == "custom"

    def test_parse_keeps_constraint_objects(self):
        c = Constraint(rule="at_least_one", params=["a", "b"])
        assert parse_constraints([c]) == [c]

    def test_unknown_rule_raises(self):
        with pytest.raises(ValueError, match="Unknown constraint rule"):
            parse_constraints([{"rule": "nonsense"}])


class TestMutuallyExclusive:
    def test_one_present_ok(self):
        check_constraint(Constraint("mutually_exclusive", params=["date", "year"]), args(date="d"))

    def test_none_present_ok(self):
        check_constraint(Constraint("mutually_exclusive", params=["date", "year"]), args())

    def test_two_present_raises(self):
        with pytest.raises(ConstraintError, match="mutually exclusive"):
            check_constraint(
                Constraint("mutually_exclusive", params=["date", "year"]),
                args(date="d", year="2026"),
            )

    def test_error_carries_violations(self):
        with pytest.raises(ConstraintError) as exc:
            check_constraint(
                Constraint("mutually_exclusive", params=["a", "b", "c"]),
                args(a=1, b=2),
            )
        assert exc.value.violations[0]["rule"] == "mutually_exclusive"
        assert exc.value.violations[0]["given"] == ["a", "b"]

    def test_custom_message(self):
        with pytest.raises(ConstraintError, match="pick one only"):
            check_constraint(
                Constraint("mutually_exclusive", params=["a", "b"], message="pick one only"),
                args(a=1, b=2),
            )


class TestTogether:
    def test_both_present_ok(self):
        check_constraint(Constraint("together", params=["user", "token"]), args(user="u", token="t"))

    def test_none_present_ok(self):
        check_constraint(Constraint("together", params=["user", "token"]), args())

    def test_partial_raises(self):
        with pytest.raises(ConstraintError, match="together"):
            check_constraint(Constraint("together", params=["user", "token"]), args(user="u"))


class TestRequires:
    def test_satisfied(self):
        check_constraint(
            Constraint("requires", param="type", requires="source"),
            args(type="stock_daily", source="tushare"),
        )

    def test_predicate_absent_ok(self):
        check_constraint(
            Constraint("requires", param="type", requires="source"), args(source=None)
        )

    def test_missing_dependency_raises(self):
        with pytest.raises(ConstraintError, match="requires --source"):
            check_constraint(
                Constraint("requires", param="type", requires="source"),
                args(type="stock_daily"),
            )


class TestExclusiveWith:
    def test_no_conflict(self):
        check_constraint(
            Constraint("exclusive_with", param="date", group=["start_date", "end_date"]),
            args(date="d"),
        )

    def test_group_member_present_raises(self):
        with pytest.raises(ConstraintError, match="exclusive"):
            check_constraint(
                Constraint("exclusive_with", param="date", group=["start_date", "end_date"]),
                args(date="d", start_date="s"),
            )


class TestAtLeastOne:
    def test_one_ok(self):
        check_constraint(Constraint("at_least_one", params=["source", "file"]), args(file="f"))

    def test_none_raises(self):
        with pytest.raises(ConstraintError, match="At least one"):
            check_constraint(Constraint("at_least_one", params=["source", "file"]), args())


class TestSourceSemantics:
    def test_action_generated_values_ignored_by_default(self):
        current = {
            "date": ParamInfo(value="d", from_source="cli"),
            "start_date": ParamInfo(value="s", from_source="action"),
        }
        check_constraint(
            Constraint("exclusive_with", param="date", group=["start_date"]), current
        )

    def test_include_generated_flag(self):
        constraint = Constraint("exclusive_with", param="date", group=["start_date"])
        constraint.include_generated = True
        current = {
            "date": ParamInfo(value="d", from_source="cli"),
            "start_date": ParamInfo(value="s", from_source="action"),
        }
        with pytest.raises(ConstraintError):
            check_constraint(constraint, current)


class TestAppIntegration:
    def test_constraint_via_app_config(self, capsys):
        app = CliApp(
            params=[Param(name="date"), Param(name="year")],
            constraints=[{"rule": "mutually_exclusive", "params": ["date", "year"]}],
            prog="t.py",
        )
        result = app.run(["--date", "d", "--year", "2026"])
        assert result.outcome == "error"
        assert "mutually exclusive" in result.error
        assert result.exit_code == 1

    def test_constraint_passes(self):
        app = CliApp(
            params=[Param(name="date"), Param(name="year"), Param(name="source")],
            constraints=[{"rule": "mutually_exclusive", "params": ["date", "year"]}],
        )
        result = app.run(["--date", "d", "--source", "x"])
        assert result.outcome == "ok"
        assert result.data["date"] == "d"

    def test_action_expansion_does_not_trigger_constraint(self):
        """date -> start_date/end_date expansion must not be flagged as a conflict."""
        from darwin_cli import ActionResult, clear_actions, register_action

        clear_actions()

        @register_action("expand_date")
        def expand_date(value, ctx):
            if value is None:
                return {}
            return {"start_date": "s", "end_date": "e"}

        app = CliApp(
            params=[
                Param(name="date", action="expand_date"),
                Param(name="start_date"),
                Param(name="end_date"),
            ],
            constraints=[
                {"rule": "exclusive_with", "param": "date", "group": ["start_date", "end_date"]}
            ],
        )
        result = app.run(["--date", "2026-01-01"])
        assert result.outcome == "ok"
        assert result.data["start_date"] == "s"
        clear_actions()


class TestIncludeGeneratedFromConfig:
    """The config key must actually reach the engine (regression guard)."""

    def test_parse_constraints_reads_the_flag(self):
        parsed = parse_constraints(
            [
                {
                    "rule": "exclusive_with",
                    "param": "date",
                    "group": ["start_date"],
                    "include_generated": True,
                }
            ]
        )
        assert parsed[0].include_generated is True

    def test_default_is_false(self):
        parsed = parse_constraints([{"rule": "at_least_one", "params": ["a"]}])
        assert parsed[0].include_generated is False

    def test_direct_constraint_object_defaults_to_false(self):
        assert Constraint("at_least_one", params=["a"]).include_generated is False

    def test_generated_value_counts_when_enabled_via_app(self):
        """With the flag on, an Action-produced start_date conflicts with date."""
        from darwin_cli import ActionResult, clear_actions, register_action

        clear_actions()

        @register_action("expand_for_include_generated")
        def expand(value, ctx):
            if value is None:
                return {}
            return ActionResult(values={"start_date": "generated"})

        app = CliApp(
            params=[Param(name="date", action="expand_for_include_generated"), Param(name="start_date")],
            constraints=[
                {
                    "rule": "exclusive_with",
                    "param": "date",
                    "group": ["start_date"],
                    "include_generated": True,
                }
            ],
        )
        result = app.run(["--date", "2026-01-01"])
        assert result.outcome == "error"
        assert "exclusive with" in result.error
        clear_actions()

    def test_same_scenario_without_flag_passes(self):
        from darwin_cli import clear_actions, register_action

        clear_actions()

        @register_action("expand_for_include_generated_off")
        def expand(value, ctx):
            return {"start_date": "generated"} if value is not None else {}

        app = CliApp(
            params=[Param(name="date", action="expand_for_include_generated_off"), Param(name="start_date")],
            constraints=[
                {"rule": "exclusive_with", "param": "date", "group": ["start_date"]}
            ],
        )
        result = app.run(["--date", "2026-01-01"])
        assert result.outcome == "ok"
        clear_actions()
