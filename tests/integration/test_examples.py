# tests/integration/test_examples.py

"""Integration tests: every sample under examples/ behaves as documented.

These tests make the configs executable documentation. If a sample or the
README index drifts out of sync with the library, this file fails.
"""

import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from darwin_cli import ActionRegistry, CliApp, Constraint
from darwin_cli.loader import KNOWN_RULES

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
CONFIGS = EXAMPLES / "configs"

SAMPLE_NAMES = [
    "01-basic.json",
    "02-inference.json",
    "03-dynamic.json",
    "04-constraints.json",
    "05-validation.json",
    "06-depends.json",
    "07-help.json",
    "08-mount.json",
    "09-groups.json",
]


# ============================================================
# Helpers
# ============================================================


def _load_action_module():
    spec = importlib.util.spec_from_file_location(
        "_darwin_cli_example_actions", EXAMPLES / "actions.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registry():
    """An isolated registry so these tests never depend on global state."""
    reg = ActionRegistry()
    _load_action_module().register_all(reg)
    return reg


def make_app(name, registry, **kwargs):
    return CliApp.from_config(str(CONFIGS / name), registry=registry, **kwargs)


def run(app, argv):
    """Run quietly; return (CliResult, printed text)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = app.run(argv)
    return result, buffer.getvalue()


# ============================================================
# Sample integrity
# ============================================================


class TestSampleIntegrity:
    @pytest.mark.parametrize("name", SAMPLE_NAMES)
    def test_config_is_valid_json(self, name):
        data = json.loads((CONFIGS / name).read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    @pytest.mark.parametrize("name", SAMPLE_NAMES)
    def test_every_action_name_is_registered(self, name, registry):
        data = json.loads((CONFIGS / name).read_text(encoding="utf-8"))
        section = data.get("cli_args", data.get("params", {}))
        for definition in section.values():
            action = definition.get("action")
            if isinstance(action, str) and action != "print_help":
                assert registry.has(action), f"{name}: action '{action}' is missing"

    @pytest.mark.parametrize("name", SAMPLE_NAMES)
    def test_constraint_rules_are_known(self, name):
        data = json.loads((CONFIGS / name).read_text(encoding="utf-8"))
        for item in data.get("constraints", []):
            assert item["rule"] in KNOWN_RULES

    @pytest.mark.parametrize("readme", ["README.md", "README.cn.md"])
    def test_readme_index_matches_files(self, readme):
        text = (EXAMPLES / readme).read_text(encoding="utf-8")
        referenced = set(re.findall(r"configs/([\w-]+\.json)", text))
        assert referenced == set(SAMPLE_NAMES)

    def test_demo_script_runs(self):
        completed = subprocess.run(
            [sys.executable, str(EXAMPLES / "demo.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        assert "Done." in completed.stdout


# ============================================================
# 01 Basics
# ============================================================


class Test01Basic:
    def test_success(self, registry):
        result, _ = run(make_app("01-basic.json", registry), ["--name", "World", "--count", "3"])
        assert result.outcome == "ok"
        assert result.data == {"name": "World", "count": 3}

    def test_default_applied(self, registry):
        result, _ = run(make_app("01-basic.json", registry), ["--name", "World"])
        assert result.data["count"] == 1

    def test_missing_required(self, registry):
        result, _ = run(make_app("01-basic.json", registry), [])
        assert result.outcome == "error"
        assert "Missing required parameter: --name" in result.error
        assert result.exit_code == 1


# ============================================================
# 02 Inference
# ============================================================


class Test02Inference:
    def test_source_inferred(self, registry):
        result, _ = run(make_app("02-inference.json", registry), ["--type", "stock_daily"])
        assert result.outcome == "ok"
        assert result.data == {"type": "stock_daily", "source": "tushare"}

    def test_explicit_value_wins(self, registry):
        result, _ = run(
            make_app("02-inference.json", registry),
            ["--type", "stock_hist", "--source", "yahoo"],
        )
        assert result.data["source"] == "yahoo"

    def test_choices_validation(self, registry):
        result, _ = run(make_app("02-inference.json", registry), ["--type", "unknown"])
        assert result.outcome == "error"
        assert "not in choices" in result.error


# ============================================================
# 03 Dynamic params
# ============================================================


class Test03Dynamic:
    def test_tushare_branch(self, registry):
        app = make_app("03-dynamic.json", registry)
        result, _ = run(app, ["--type", "stock_daily", "--symbol", "600000.SH"])
        assert result.outcome == "ok"
        assert result.data["source"] == "tushare"
        assert result.data["symbol"] == "600000.SH"
        assert result.data["fields"] == "close"
        assert {p.name for p in app.dynamic_params} == {"symbol", "fields"}

    def test_yahoo_branch(self, registry):
        app = make_app("03-dynamic.json", registry)
        result, _ = run(
            app, ["--type", "stock_hist", "--source", "yahoo", "--symbol", "AAPL"]
        )
        assert result.data["interval"] == "1d"
        assert "fields" not in result.data
        assert {p.name for p in app.dynamic_params} == {"symbol", "interval"}

    def test_dynamic_param_from_cli_is_validated(self, registry):
        """A CLI value for a not-yet-declared param must be validated once defined."""
        result, _ = run(make_app("03-dynamic.json", registry), ["--type", "stock_daily", "--symbol", "bad"])
        assert result.outcome == "error"
        assert "does not match pattern" in result.error

    def test_unknown_argument_rejected(self, registry):
        result, _ = run(make_app("03-dynamic.json", registry), ["--type", "stock_daily", "--nope", "x"])
        assert result.outcome == "error"
        assert "Unknown parameter: --nope" in result.error


# ============================================================
# 04 Constraints
# ============================================================


class Test04Constraints:
    def test_all_rules_satisfied(self, registry):
        result, _ = run(make_app("04-constraints.json", registry), ["--source", "tushare"])
        assert result.outcome == "ok"

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["--date", "d", "--year", "2026", "--source", "tushare"], "mutually exclusive"),
            (["--user", "bob", "--source", "tushare"], "must be provided together"),
            (["--type", "stock_daily", "--file", "local.csv"], "requires --source"),
            (["--window", "5d", "--start_date", "s", "--source", "tushare"], "exclusive with"),
            (["--date", "d"], "At least one"),
        ],
    )
    def test_each_rule_violation(self, registry, argv, expected):
        result, _ = run(make_app("04-constraints.json", registry), argv)
        assert result.outcome == "error"
        assert expected in result.error

    def test_action_generated_value_does_not_count(self, registry):
        """start_date produced elsewhere must not trigger exclusive_with by default."""
        from darwin_cli import Param, register_action

        @register_action("_gen_start", registry=registry)
        def gen(value, ctx):
            return {"start_date": "generated"}

        app = CliApp(
            params=[Param(name="window"), Param(name="start_date", action="_gen_start")],
            constraints=[
                {"rule": "exclusive_with", "param": "window", "group": ["start_date"]}
            ],
            registry=registry,
        )
        result, _ = run(app, ["--window", "5d"])
        assert result.outcome == "ok"


# ============================================================
# 05 Validation
# ============================================================


class Test05Validation:
    def test_all_valid(self, registry):
        result, _ = run(
            make_app("05-validation.json", registry),
            [
                "--count", "5",
                "--status", "active",
                "--name", "demo",
                "--symbol", "600000.SH",
                "--overwrite",
            ],
        )
        assert result.outcome == "ok"
        assert result.data["count"] == 5 and isinstance(result.data["count"], int)
        assert result.data["overwrite"] is True

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["--count", "200"], "above maximum"),
            (["--count", "0"], "below minimum"),
            (["--status", "unknown"], "not in choices"),
            (["--name", "x"], "below minimum"),
            (["--symbol", "invalid"], "does not match pattern"),
        ],
    )
    def test_rule_violations(self, registry, argv, expected):
        result, _ = run(make_app("05-validation.json", registry), argv)
        assert result.outcome == "error"
        assert expected in result.error


# ============================================================
# 06 depends_on
# ============================================================


class Test06Depends:
    def test_expansion_and_downstream_action(self, registry):
        result, _ = run(make_app("06-depends.json", registry), ["--year", "2026"])
        assert result.outcome == "ok"
        assert result.data["start_date"] == "2026-01-01"
        assert result.data["end_date"] == "2026-12-31"
        assert result.data["report"] == "2026-01-01..2026-12-31"

    def test_without_year_no_expansion(self, registry):
        result, _ = run(make_app("06-depends.json", registry), [])
        assert result.outcome == "ok"
        assert result.data.get("start_date") is None
        assert result.data.get("end_date") is None


# ============================================================
# 07 Context-aware help
# ============================================================


class Test07Help:
    def test_global_help(self, registry):
        result, text = run(make_app("07-help.json", registry), ["--help"])
        assert result.outcome == "help"
        assert result.success is False
        assert result.exit_code == 0
        assert "Global options:" in text
        assert "Usage: 07-help.py" in text

    def test_scenario_help_after_inference(self, registry):
        result, text = run(make_app("07-help.json", registry), ["--type", "stock_daily", "--help"])
        assert result.outcome == "help"
        assert "Source: tushare" in text
        assert "(dynamic)" in text
        assert "--symbol" in text


# ============================================================
# 08 mount
# ============================================================


class Test08Mount:
    def test_mount_selects_subtree(self, registry):
        app = make_app("08-mount.json", registry, mount="fetcher.cli")
        result, _ = run(app, ["--type", "stock_daily"])
        assert result.outcome == "ok"
        assert result.data["output"] == "out.csv"
        assert [p.name for p in app.static_params] == ["type", "output", "stdout"]

    def test_default_does_not_trigger_constraint(self, registry):
        app = make_app("08-mount.json", registry, mount="fetcher.cli")
        result, _ = run(app, ["--type", "stock_daily", "--stdout"])
        assert result.outcome == "ok"

    def test_two_explicit_args_conflict(self, registry):
        app = make_app("08-mount.json", registry, mount="fetcher.cli")
        result, _ = run(app, ["--type", "stock_daily", "--output", "a.csv", "--stdout"])
        assert result.outcome == "error"
        assert "mutually exclusive" in result.error


# ============================================================
# 09 Groups (declarative relations)
# ============================================================


class Test09Groups:
    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["--date", "d"], "ok"),
            (["--start_date", "s", "--end_date", "e"], "ok"),
            (["--date", "d", "--start_date", "s", "--end_date", "e"], "error"),
            (["--year", "2026"], "ok"),
            (["--year", "2026", "--date", "d"], "error"),
            (["--year", "2026", "--start_date", "s", "--end_date", "e"], "ok"),
            (["--start_date", "s"], "error"),
            (["--window", "7", "--date", "d"], "ok"),
            (["--window", "7", "--start_date", "s", "--end_date", "e"], "error"),
            ([], "error"),
        ],
    )
    def test_scenarios(self, registry, argv, expected):
        result, _ = run(make_app("09-groups.json", registry), argv)
        assert result.outcome == expected

    def test_compilation_is_flat(self, registry):
        """Groups are a load-time macro: runtime sees only plain Constraints."""
        app = make_app("09-groups.json", registry)
        constraints = app._initial_constraints
        assert len(constraints) == 5
        assert all(isinstance(c, Constraint) for c in constraints)
        assert all("@" not in str(c.params) + str(c.group) for c in constraints)
        assert constraints[-1].rule == "at_least_one"

    def test_exclusive_with_message_has_no_self(self, registry):
        result, _ = run(
            make_app("09-groups.json", registry),
            ["--window", "7", "--start_date", "s", "--end_date", "e"],
        )
        assert result.outcome == "error"
        assert "is exclusive with ['window']" in result.error
        assert "['start_date'" not in result.error
