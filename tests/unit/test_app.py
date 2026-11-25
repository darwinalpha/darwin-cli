# tests/test_cli/unit/test_app.py

"""
Test app.py - CLI Application facade
"""

import sys
import pytest
from darwin_cli.app import CliApp
from darwin_cli.base import Param, CliResult, ActionResult
from darwin_cli.actions import (
    register_action,
    clear_actions,
    HelpRequested,
    ActionError,
    RequiredError,
)


class TestCliAppInit:
    """Test CliApp """

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_init_with_params_list(self, sample_params):
        """Test  List[Param] """
        app = CliApp(params=sample_params, prog="test")
        assert app._initial_params == sample_params
        assert app.prog == "test"

    def test_init_with_config_dict(self, sample_config):
        """Test  Dict """
        app = CliApp(params=sample_config, prog="test")
        assert len(app._initial_params) == 4
        assert app._initial_params[0].name == "type"
        assert app._initial_params[0].type == "str"
        assert app._initial_params[1].name == "source"

    def test_init_with_action_modules(self, tmp_path):
        """Test  action """
        #  
        module_dir = tmp_path / "test_app_actions"
        module_dir.mkdir()
        module_file = module_dir / "__init__.py"
        module_file.write_text("""
from darwin_cli.actions import register_action

@register_action("app_test_action")
def app_test_action(value, ctx):
    return {"result": "from module"}
""")

        import sys

        sys.path.insert(0, str(tmp_path))

        try:
            app = CliApp(
                params=[],
                action_modules=["test_app_actions"],
            )
            from darwin_cli.actions import has_action

            assert has_action("app_test_action") is True
        finally:
            sys.path.pop(0)

    def test_init_with_custom_validators(self):
        """Test  validation"""

        def validate(value):
            return value

        app = CliApp(
            params=[],
            custom_validators={"custom": validate},
        )
        assert "custom" in app.custom_validators
        assert app.custom_validators["custom"] is validate


class TestCliAppRun:
    """Test CliApp.run"""

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_run_success(self, sample_params):
        """Test """
        app = CliApp(params=sample_params, prog="test")
        result = app.run(["--type", "stock_daily", "--source", "tushare"])

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "stock_daily"
        assert result.data["source"] == "tushare"

    def test_run_with_config(self, sample_config):
        """Test  after """
        app = CliApp(params=sample_config, prog="test")
        result = app.run(["--type", "stock_daily"])

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "stock_daily"

    def test_run_help_only(self, sample_params):
        """Test  has  --help"""
        app = CliApp(params=sample_params, prog="test")
        result = app.run(["--help"])

        assert result.success is False
        assert result.exit_code == 0

    def test_run_required_error(self):
        """Test Missing required parameter"""
        params = [Param(name="type", type="str", required=True)]
        app = CliApp(params=params)
        result = app.run([])

        assert result.success is False
        assert result.exit_code == 1
        assert result.error is not None
        assert "Missing required parameter" in result.error

    def test_run_action_error(self):
        """Test failed"""

        @register_action("fail_action")
        def fail_action(value, ctx):
            raise ValueError("action failed")

        params = [Param(name="test", type="str", action="fail_action")]
        app = CliApp(params=params)
        result = app.run(["--test", "value"])

        assert result.success is False
        assert result.exit_code == 1
        assert result.error is not None
        assert "failed" in result.error

    def test_run_unknown_exception(self):
        """Test """
        params = [Param(name="test", type="invalid_type")]
        app = CliApp(params=params)

        result = app.run(["--test", "value"])

        # An unknown type does not raise; it is returned as-is
        assert result.success is True
        assert result.data is not None
        assert result.data["test"] == "value"


class TestCliAppRunOrExit:
    """Test CliApp.run_or_exit"""

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_run_or_exit_success(self, sample_params):
        """Test Return"""
        app = CliApp(params=sample_params)
        result = app.run_or_exit(["--type", "stock_daily"])

        assert result["type"] == "stock_daily"

    def test_run_or_exit_failure(self, sample_params):
        """Test """
        app = CliApp(params=sample_params)

        with pytest.raises(SystemExit) as exc_info:
            app.run_or_exit([])

        assert exc_info.value.code == 1


class TestCliAppProperties:
    """Test CliApp """

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_params_property(self, sample_params):
        """Test params """
        app = CliApp(params=sample_params)
        app.run(["--type", "stock_daily"])

        assert app.params is not None
        assert len(app.params) >= len(sample_params)

    def test_static_params_property(self, sample_params):
        """Test static_params """
        app = CliApp(params=sample_params)
        app.run(["--type", "stock_daily"])

        assert app.static_params == sample_params

    def test_dynamic_params_property(self, sample_params):
        """Test dynamic_params """

        @register_action("generate_dynamic")
        def generate_dynamic(value, ctx):
            return ActionResult(
                params=[Param(name="dynamic_param", type="str")],
            )

        params = sample_params + [
            Param(name="generate", type="str", action="generate_dynamic"),
        ]
        app = CliApp(params=params)
        app.run(["--type", "stock_daily", "--generate", "test"])

        #  parameter 
        dynamic_names = [p.name for p in app.dynamic_params]
        assert "dynamic_param" in dynamic_names

    def test_get_param(self, sample_params):
        """Test get_param """
        app = CliApp(params=sample_params)
        app.run(["--type", "stock_daily"])

        param = app.get_param("type")
        assert param is not None
        assert param.name == "type"

        param = app.get_param("not_exist")
        assert param is None
