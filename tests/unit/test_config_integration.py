# tests/unit/test_config_integration.py

"""Tests for CliApp.from_config and the optional darwin-config adapter."""

import json

import pytest

from darwin_cli import CliApp


CONFIG = {
    "help": "fetch tool",
    "cli_args": {
        "type": {"type": "str", "required": True, "help": "data type"},
        "source": {"type": "str", "help": "data source"},
        "date": {"type": "str"},
        "year": {"type": "str"},
    },
    "constraints": [
        {"rule": "mutually_exclusive", "params": ["date", "year"]},
    ],
}


class TestFromDict:
    def test_basic(self):
        app = CliApp.from_config(CONFIG, prog="fetch.py")
        result = app.run(["--type", "stock_daily"])
        assert result.outcome == "ok"
        assert result.data["type"] == "stock_daily"
        assert len(app.static_params) == 4

    def test_description_from_config(self):
        app = CliApp.from_config(CONFIG)
        assert app.description == "fetch tool"

    def test_explicit_help_overrides_config(self):
        app = CliApp.from_config(CONFIG, help="override")
        assert app.description == "override"

    def test_constraints_active(self):
        app = CliApp.from_config(CONFIG, prog="fetch.py")
        result = app.run(["--type", "stock_daily", "--date", "d", "--year", "2026"])
        assert result.outcome == "error"
        assert "mutually exclusive" in result.error

    def test_custom_params_key(self):
        config = {
            "params": {"name": {"type": "str", "required": True}},
        }
        app = CliApp.from_config(config)
        result = app.run(["--name", "Alice"])
        assert result.data["name"] == "Alice"


class TestMount:
    def test_dotted_mount(self):
        config = {"fetcher": CONFIG}
        app = CliApp.from_config(config, mount="fetcher", prog="fetch.py")
        result = app.run(["--type", "stock_daily"])
        assert result.outcome == "ok"

    def test_missing_mount_yields_empty_params(self):
        app = CliApp.from_config({"other": {}}, mount="missing")
        assert app.static_params == []


class TestFromFile:
    def test_json_file(self, tmp_path):
        path = tmp_path / "params.json"
        path.write_text(json.dumps(CONFIG), encoding="utf-8")
        app = CliApp.from_config(str(path), prog="fetch.py")
        result = app.run(["--type", "stock_daily"])
        assert result.outcome == "ok"

    def test_loader_callback_overrides_file_read(self):
        def loader(key):
            return CONFIG

        app = CliApp.from_config("any-key", loader=loader, prog="fetch.py")
        result = app.run(["--type", "stock_daily"])
        assert result.outcome == "ok"


class TestDarwinConfigAdapter:
    def test_adapter_works_with_fake_get_config(self, monkeypatch):
        """The adapter imports darwin_config lazily; simulate it here."""
        import sys
        import types

        fake_module = types.ModuleType("darwin_config")

        def fake_get_config(key, default=None):
            return CONFIG if key == "fetcher" else default

        fake_module.get_config = fake_get_config
        monkeypatch.setitem(sys.modules, "darwin_config", fake_module)

        from darwin_cli.integrations.darwin_config import from_config

        app = from_config("fetcher", prog="fetch.py")
        result = app.run(["--type", "stock_daily"])
        assert result.outcome == "ok"

    def test_adapter_raises_on_missing_key(self, monkeypatch):
        import sys
        import types

        fake_module = types.ModuleType("darwin_config")
        fake_module.get_config = lambda key, default=None: default
        monkeypatch.setitem(sys.modules, "darwin_config", fake_module)

        from darwin_cli.integrations.darwin_config import from_config

        with pytest.raises(ValueError, match="empty or missing"):
            from_config("missing")
