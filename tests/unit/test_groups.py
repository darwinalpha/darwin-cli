# tests/unit/test_groups.py

"""Tests for the load-time groups compiler and the layered relation contract.

Layer contract
--------------
* param definitions: one-to-one relations (a single parameter name, a string),
  and no '@group' reference anywhere.
* groups section: membership (nestable) plus (a) relations among several params
  via ``true`` and (b) a group's relation to a third party via a list.
* top-level constraints: unchanged, with '@group' references expanded.
"""

import contextlib
import io

import pytest

from darwin_cli import (
    CliApp,
    ConstraintError,
    Param,
    compile_constraints,
    resolve_groups,
    validate_param_definitions,
)
from darwin_cli.base import Constraint, ParamInfo
from darwin_cli.constraints import check_constraint
from darwin_cli.loader import (
    KNOWN_PARAM_KEYS,
    RELATION_RULES,
    expand,
    param_definitions_from_objects,
    split_groups_section,
)


def run(app, argv):
    """Run quietly; return the CliResult."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        return app.run(argv)


# ============================================================
# Param layer validation
# ============================================================


class TestValidateParamDefinitions:
    def test_one_to_one_str_is_valid(self):
        validate_param_definitions({"a": {"type": "str", "together": "b"}, "b": {}})

    def test_all_relation_rules_are_known_keys(self):
        assert set(RELATION_RULES) <= KNOWN_PARAM_KEYS
        assert "depends_on" in KNOWN_PARAM_KEYS

    @pytest.mark.parametrize("rule", RELATION_RULES)
    def test_list_value_rejected(self, rule):
        with pytest.raises(ValueError, match="one-to-one"):
            validate_param_definitions({"a": {rule: ["b"]}})

    @pytest.mark.parametrize("rule", RELATION_RULES)
    def test_group_reference_rejected(self, rule):
        with pytest.raises(ValueError, match="cannot reference groups"):
            validate_param_definitions({"a": {rule: "@g"}})

    def test_group_tag_rejected(self):
        with pytest.raises(ValueError, match="'a.group' is not supported"):
            validate_param_definitions({"a": {"group": "@g"}})

    def test_unknown_key_rejected(self):
        """A typo must not silently drop a relation."""
        with pytest.raises(ValueError, match="Unknown key 'a.mutualy_exclusive'"):
            validate_param_definitions({"a": {"mutualy_exclusive": "b"}})

    def test_depends_on_group_reference_rejected(self):
        with pytest.raises(ValueError, match="cannot reference groups"):
            validate_param_definitions({"a": {"depends_on": ["@g"]}})

    def test_self_reference_rejected(self):
        with pytest.raises(ValueError, match="cannot reference itself"):
            validate_param_definitions({"a": {"together": "a"}})

    def test_non_string_value_rejected(self):
        with pytest.raises(ValueError, match="must be a single parameter name"):
            validate_param_definitions({"a": {"together": 3}})

    def test_non_dict_definition_rejected(self):
        with pytest.raises(ValueError, match="must be a dict"):
            validate_param_definitions({"a": "str"})


class TestParamDefinitionsFromObjects:
    def test_only_relations_and_depends_on_are_extracted(self):
        defs = param_definitions_from_objects(
            [
                Param(name="a", together="b", depends_on=["c"]),
                Param(name="b"),
            ]
        )
        assert defs == {"a": {"together": "b", "depends_on": ["c"]}, "b": {}}

    def test_plain_params_produce_empty_definitions(self):
        assert param_definitions_from_objects([Param(name="a")]) == {"a": {}}


# ============================================================
# Group section parsing
# ============================================================


class TestSplitGroupsSection:
    def test_list_form_is_pure_members(self):
        explicit, rules = split_groups_section({"@g": ["a", "b"]})
        assert explicit["@g"] == ["a", "b"]
        assert rules["@g"] == {}

    def test_dict_form_separates_members_and_rules(self):
        explicit, rules = split_groups_section(
            {"@g": {"members": ["a"], "mutually_exclusive": True}}
        )
        assert explicit["@g"] == ["a"]
        assert rules["@g"] == {"mutually_exclusive": True}

    def test_group_key_must_start_with_at(self):
        with pytest.raises(ValueError, match="must start with '@'"):
            split_groups_section({"g": ["a"]})

    def test_dict_without_members_rejected(self):
        with pytest.raises(ValueError, match="has no 'members'"):
            split_groups_section({"@g": {"mutually_exclusive": True}})

    def test_members_must_be_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            split_groups_section({"@g": {"members": "a"}})

    def test_unknown_group_rule_rejected(self):
        with pytest.raises(ValueError, match="Unknown group rule"):
            split_groups_section({"@g": {"members": ["a"], "conflicts": ["b"]}})

    def test_bad_value_type_rejected(self):
        with pytest.raises(ValueError, match="must be a list or dict"):
            split_groups_section({"@g": True})


class TestResolveGroups:
    def test_nested_expansion(self):
        resolved = resolve_groups(
            {
                "@sedate": ["start_date", "end_date"],
                "@range": ["@sedate", "year"],
                "@dates": ["date", "@range"],
            }
        )
        assert resolved["@sedate"] == ["start_date", "end_date"]
        assert resolved["@range"] == ["start_date", "end_date", "year"]
        assert resolved["@dates"] == ["date", "start_date", "end_date", "year"]

    def test_duplicate_members_deduplicated_in_order(self):
        assert resolve_groups({"@g": ["a", "b", "a", "c"]})["@g"] == ["a", "b", "c"]

    def test_param_in_multiple_groups(self):
        resolved = resolve_groups({"@left": ["a", "b"], "@right": ["b", "c"]})
        assert resolved["@left"] == ["a", "b"]
        assert resolved["@right"] == ["b", "c"]

    def test_cycle_reports_path(self):
        with pytest.raises(ValueError, match=r"@a -> @b -> @a"):
            resolve_groups({"@a": ["@b"], "@b": ["@a"]})

    def test_self_cycle(self):
        with pytest.raises(ValueError, match=r"@a -> @a"):
            resolve_groups({"@a": ["@a"]})

    def test_undefined_nested_group(self):
        with pytest.raises(ValueError, match="Undefined group '@nope'"):
            resolve_groups({"@a": ["@nope"]})

    def test_empty_group_rejected(self):
        with pytest.raises(ValueError, match="has no members"):
            resolve_groups({"@g": []})

    def test_non_string_member_rejected(self):
        with pytest.raises(ValueError, match="must be strings"):
            resolve_groups({"@g": [1]})


class TestExpand:
    def test_group_and_param_names_mix(self):
        assert expand(["x", "@g", "y"], {"@g": ["a", "b"]}) == ["x", "a", "b", "y"]

    def test_drop_removes_subject(self):
        assert expand(["@g"], {"@g": ["a", "b", "c"]}, drop="b") == ["a", "c"]

    def test_deduplication(self):
        assert expand(["@g", "a"], {"@g": ["a", "b"]}) == ["a", "b"]

    def test_undefined_group_rejected(self):
        with pytest.raises(ValueError, match="Undefined group '@nope'"):
            expand(["@nope"], {})


# ============================================================
# Compilation
# ============================================================


class TestCompileConstraints:
    def test_inline_one_to_one(self):
        rules = compile_constraints({"a": {"together": "b"}, "b": {}})
        assert len(rules) == 1
        assert rules[0].rule == "together"
        assert rules[0].params == ["a", "b"]

    def test_inline_requires_is_directed(self):
        rules = compile_constraints({"a": {"requires": "b"}, "b": {}})
        assert len(rules) == 1
        assert rules[0].rule == "requires"
        assert rules[0].param == "a"
        assert rules[0].requires == "b"

    def test_inline_exclusive_with(self):
        rules = compile_constraints({"a": {"exclusive_with": "b"}, "b": {}})
        assert rules[0].rule == "exclusive_with"
        assert rules[0].param == "a"
        assert rules[0].group == ["b"]

    def test_group_true_is_single_n_ary_rule(self):
        rules = compile_constraints(
            {"a": {}, "b": {}, "c": {}},
            {"@g": {"members": ["a", "b", "c"], "mutually_exclusive": True}},
        )
        assert len(rules) == 1
        assert rules[0].rule == "mutually_exclusive"
        assert rules[0].params == ["a", "b", "c"]

    def test_group_list_is_per_member(self):
        rules = compile_constraints(
            {"a": {}, "z": {}, "x": {}, "y": {}},
            {"@right": {"members": ["x", "y"], "exclusive_with": ["a", "z"]}},
        )
        assert len(rules) == 2
        assert [r.param for r in rules] == ["x", "y"]
        assert all(r.group == ["a", "z"] for r in rules)

    def test_group_to_group_via_at_reference(self):
        rules = compile_constraints(
            {"a": {}, "b": {}, "x": {}, "y": {}},
            {
                "@left": ["a", "b"],
                "@right": {"members": ["x", "y"], "exclusive_with": ["@left"]},
            },
        )
        assert [r.param for r in rules] == ["x", "y"]
        assert all(r.group == ["a", "b"] for r in rules)

    def test_mixed_group_and_param_targets(self):
        rules = compile_constraints(
            {"a": {}, "b": {}, "z": {}, "x": {}, "y": {}},
            {
                "@left": ["a", "b"],
                "@right": {"members": ["x", "y"], "exclusive_with": ["@left", "z"]},
            },
        )
        assert all(r.group == ["a", "b", "z"] for r in rules)

    def test_self_is_dropped_from_targets(self):
        """A member shared by subject and target group must not exclude itself."""
        rules = compile_constraints(
            {"a": {}, "b": {}},
            {"@g": {"members": ["a", "b"], "exclusive_with": ["@g"]}},
        )
        assert [r.param for r in rules] == ["a", "b"]
        assert rules[0].group == ["b"]
        assert rules[1].group == ["a"]

    def test_duplicate_declarations_deduplicated(self):
        rules = compile_constraints(
            {"a": {"mutually_exclusive": "b"}, "b": {"mutually_exclusive": "a"}}
        )
        assert len(rules) == 1

    def test_at_least_one_sorted_last(self):
        rules = compile_constraints(
            {"a": {}},
            {
                "@g": {"members": ["a"], "at_least_one": True},
                "@h": {"members": ["a"], "together": True},
            },
        )
        assert rules[-1].rule == "at_least_one"

    def test_top_level_constraints_expand_at_in_params_and_group(self):
        rules = compile_constraints(
            {"a": {}, "b": {}, "c": {}, "d": {}},
            {"@g": ["a", "b"]},
            [
                {"rule": "at_least_one", "params": ["@g", "c"]},
                {"rule": "exclusive_with", "param": "d", "group": ["@g"]},
            ],
        )
        by_rule = {c.rule: c for c in rules}
        assert by_rule["at_least_one"].params == ["a", "b", "c"]
        assert by_rule["exclusive_with"].group == ["a", "b"]

    def test_top_level_custom_message_and_flag_preserved(self):
        rules = compile_constraints(
            {"a": {}, "b": {}},
            {},
            [
                {
                    "rule": "mutually_exclusive",
                    "params": ["a", "b"],
                    "message": "pick one",
                    "include_generated": True,
                }
            ],
        )
        assert rules[0].message == "pick one"
        assert rules[0].include_generated is True

    def test_constraint_objects_pass_through(self):
        c = Constraint(rule="together", params=["a", "b"])
        assert compile_constraints({"a": {}, "b": {}}, {}, [c]) == [c]

    def test_undefined_group_in_target_rejected(self):
        with pytest.raises(ValueError, match="Undefined group '@nope'"):
            compile_constraints(
                {"a": {}},
                {"@g": {"members": ["a"], "exclusive_with": ["@nope"]}},
            )

    def test_bad_group_rule_value_rejected(self):
        with pytest.raises(ValueError, match="must be true or a list"):
            compile_constraints(
                {"a": {}},
                {"@g": {"members": ["a"], "together": "yes"}},
            )


# ============================================================
# CliApp wiring
# ============================================================


class TestAppWiring:
    def test_from_config_reads_groups(self):
        app = CliApp.from_config(
            {
                "cli_args": {"a": {}, "b": {}, "c": {}},
                "groups": {
                    "@g": {"members": ["a", "b", "c"], "mutually_exclusive": True}
                },
            }
        )
        assert run(app, ["--a", "1"]).outcome == "ok"
        assert run(app, ["--a", "1", "--b", "2"]).outcome == "error"

    def test_inline_relation_via_param_objects(self):
        app = CliApp(params=[Param(name="a", together="b"), Param(name="b")])
        assert run(app, ["--a", "1"]).outcome == "error"
        assert run(app, ["--a", "1", "--b", "2"]).outcome == "ok"

    def test_inline_relation_via_dict(self):
        app = CliApp(params={"a": {"together": "b"}, "b": {}})
        assert run(app, ["--a", "1"]).outcome == "error"

    def test_groups_kwarg_on_constructor(self):
        app = CliApp(
            params=[Param(name="a"), Param(name="b")],
            groups={"@g": {"members": ["a", "b"], "together": True}},
        )
        assert run(app, ["--a", "1"]).outcome == "error"
        assert run(app, ["--a", "1", "--b", "2"]).outcome == "ok"

    def test_bad_inline_relation_raises_at_construction(self):
        with pytest.raises(ValueError, match="one-to-one"):
            CliApp.from_config({"cli_args": {"a": {"together": ["b"]}, "b": {}}})

    def test_group_cycle_raises_at_construction(self):
        with pytest.raises(ValueError, match="Group cycle"):
            CliApp.from_config(
                {"cli_args": {"a": {}}, "groups": {"@a": ["@b"], "@b": ["@a"]}}
            )

    def test_existing_top_level_constraints_still_work(self):
        app = CliApp.from_config(
            {
                "cli_args": {"a": {}, "b": {}},
                "constraints": [{"rule": "mutually_exclusive", "params": ["a", "b"]}],
            }
        )
        assert run(app, ["--a", "1", "--b", "2"]).outcome == "error"

    def test_groups_are_invisible_at_runtime(self):
        """Compiled output is a flat Constraint list; the engine needs no group concept."""
        app = CliApp.from_config(
            {
                "cli_args": {"a": {}, "b": {}, "x": {}, "y": {}},
                "groups": {
                    "@left": ["a", "b"],
                    "@right": {"members": ["x", "y"], "exclusive_with": ["@left"]},
                },
            }
        )
        assert all(isinstance(c, Constraint) for c in app._initial_constraints)
        assert all("@" not in str(c.params) + str(c.group) for c in app._initial_constraints)


# ============================================================
# Message regression
# ============================================================


class TestExclusiveWithMessage:
    def test_default_message_excludes_subject(self):
        c = Constraint("exclusive_with", param="window", group=["date", "year"])
        current = {
            "window": ParamInfo(value="7", from_source="cli"),
            "date": ParamInfo(value="d", from_source="cli"),
        }
        with pytest.raises(ConstraintError) as exc:
            check_constraint(c, current)
        assert "['window'" not in str(exc.value)
        assert "['date']" in str(exc.value)

    def test_custom_message_unchanged(self):
        c = Constraint(
            "exclusive_with", param="window", group=["date"], message="no mixing"
        )
        current = {
            "window": ParamInfo(value="7", from_source="cli"),
            "date": ParamInfo(value="d", from_source="cli"),
        }
        with pytest.raises(ConstraintError, match="no mixing"):
            check_constraint(c, current)
