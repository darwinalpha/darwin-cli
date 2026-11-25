# tests/test_cli/unit/test_actions.py

"""
Test actions.py - Action Registration and management
"""

import pytest
from darwin_cli.actions import (
    ACTION_REGISTRY,
    register_action,
    get_action,
    has_action,
    list_actions,
    clear_actions,
    print_help,
    set_overwrite,
    set_fake,
    load_actions_from_module,
    load_actions_from_file,
    HelpRequested,
    ActionError,
    ConflictError,
    RequiredError,
    MaxIterationsExceeded,
    CycleDetected,
)


class TestActionRegistry:
    """Test Action registry"""

    def setup_method(self):
        """ each Test  before registry"""
        clear_actions()

    def teardown_method(self):
        """ each Test  after registry"""
        clear_actions()

    def test_register_action(self):
        """Test  action"""

        @register_action("test_action")
        def test_func(value, ctx):
            return {"result": value}

        assert "test_action" in ACTION_REGISTRY
        assert ACTION_REGISTRY["test_action"] is test_func

    def test_register_duplicate(self):
        """Test """

        @register_action("duplicate")
        def func1(value, ctx):
            return {}

        with pytest.raises(ValueError, match="Action 'duplicate' already registered"):

            @register_action("duplicate")
            def func2(value, ctx):
                return {}

    def test_get_action(self):
        """Test  action"""

        @register_action("get_test")
        def test_func(value, ctx):
            return {"result": value}

        func = get_action("get_test")
        assert func is test_func

    def test_get_action_not_found(self):
        """Test  not   action"""
        with pytest.raises(KeyError, match="Action 'not_exist' not registered"):
            get_action("not_exist")

    def test_has_action(self):
        """Test  action """
        assert has_action("not_exist") is False

        @register_action("exists")
        def test_func(value, ctx):
            return {}

        assert has_action("exists") is True

    def test_list_actions(self):
        """Test   has  action"""

        @register_action("func1")
        def func1(value, ctx):
            return {}

        @register_action("func2")
        def func2(value, ctx):
            return {}

        actions = list_actions()
        assert "func1" in actions
        assert "func2" in actions
        assert len(actions) == 2

        # returns a copy
        actions["func3"] = lambda: None
        assert "func3" not in ACTION_REGISTRY

    def test_clear_actions(self):
        """Test registry"""

        @register_action("to_clear")
        def test_func(value, ctx):
            return {}

        assert "to_clear" in ACTION_REGISTRY

        clear_actions()
        assert "to_clear" not in ACTION_REGISTRY
        assert len(ACTION_REGISTRY) == 0


class TestBuiltinActions:
    """Test  Action"""

    def setup_method(self):
        """Clear the registry before each test, then re-register built-in actions"""
        clear_actions()

        #  action
        @register_action("print_help")
        def _print_help(value, ctx):
            raise HelpRequested()

        @register_action("set_overwrite")
        def _set_overwrite(value, ctx):
            return {"overwrite": True} if value else {}

        @register_action("set_fake")
        def _set_fake(value, ctx):
            return {"fake": True} if value else {}

    def teardown_method(self):
        """ each Test  after registry"""
        clear_actions()

    def test_print_help(self):
        """Test print_help  HelpRequested"""
        with pytest.raises(HelpRequested):
            print_help(True, {})

    def test_set_overwrite_true(self):
        """Test set_overwrite True"""
        result = set_overwrite(True, {})
        assert result == {"overwrite": True}

    def test_set_overwrite_false(self):
        """Test set_overwrite False"""
        result = set_overwrite(False, {})
        assert result == {}

    def test_set_fake_true(self):
        """Test set_fake True"""
        result = set_fake(True, {})
        assert result == {"fake": True}

    def test_set_fake_false(self):
        """Test set_fake False"""
        result = set_fake(False, {})
        assert result == {}

    def test_print_help_registered(self):
        """Test print_help """
        assert has_action("print_help") is True

    def test_set_overwrite_registered(self):
        """Test set_overwrite """
        assert has_action("set_overwrite") is True

    def test_set_fake_registered(self):
        """Test set_fake """
        assert has_action("set_fake") is True


class TestLoadActions:
    """Test  Action """

    def setup_method(self):
        clear_actions()

    def teardown_method(self):
        clear_actions()

    def test_load_actions_from_module(self, tmp_path):
        """Test  action"""
        #  
        module_dir = tmp_path / "test_actions_module"
        module_dir.mkdir()
        module_file = module_dir / "__init__.py"
        module_file.write_text("""
from darwin_cli.actions import register_action

@register_action("from_module")
def from_module(value, ctx):
    return {"from": "module"}
""")

        import sys

        sys.path.insert(0, str(tmp_path))

        try:
            load_actions_from_module("test_actions_module")
            assert has_action("from_module") is True

            func = get_action("from_module")
            result = func(None, {})
            assert result == {"from": "module"}
        finally:
            sys.path.pop(0)

    def test_load_actions_from_module_not_found(self):
        """Test  not  """
        with pytest.raises(ImportError, match="Cannot load action module"):
            load_actions_from_module("non_existent_module")


class TestExceptions:
    """Test """

    def test_help_requested(self):
        """Test HelpRequested"""
        with pytest.raises(HelpRequested):
            raise HelpRequested()

    def test_action_error(self):
        """Test ActionError"""
        with pytest.raises(ActionError):
            raise ActionError("action failed")

    def test_conflict_error(self):
        """Test ConflictError"""
        with pytest.raises(ConflictError):
            raise ConflictError("conflict")

    def test_required_error(self):
        """Test RequiredError"""
        with pytest.raises(RequiredError):
            raise RequiredError("required")

    def test_max_iterations_exceeded(self):
        """Test MaxIterationsExceeded"""
        with pytest.raises(MaxIterationsExceeded):
            raise MaxIterationsExceeded("max exceeded")

    def test_cycle_detected(self):
        """Test CycleDetected"""
        with pytest.raises(CycleDetected):
            raise CycleDetected("cycle detected")
