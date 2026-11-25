# src/darwin_cli/integrations/darwin_config.py

"""
Optional adapter for darwin-config.

This module is not imported by ``darwin_cli.__init__``; import it explicitly
when you want parameter declarations to live in a darwin-config file::

    from darwin_cli.integrations.darwin_config import from_config

    app = from_config("config/fetch.json", mount="fetcher", prog="fetch.py")

Requires ``darwin-config`` to be installed. The core library has no dependency
on it.
"""

from typing import Any, Dict, Optional

from darwin_cli.app import CliApp


def get_loader(*path: str):
    """Return a loader callable bound to darwin-config's ``get_config``.

    ``path`` is an optional dotted prefix prepended to the key passed to the
    loader. If omitted, keys are used as-is.
    """
    from darwin_config import get_config as _get_config

    prefix = ".".join(path)

    def loader(key: str) -> Dict[str, Any]:
        full = f"{prefix}.{key}" if prefix else key
        return _get_config(full, {}) or {}

    return loader


def from_config(
    config: str,
    mount: Optional[str] = None,
    prog: Optional[str] = None,
    help: Optional[str] = None,
    **kwargs: Any,
) -> CliApp:
    """Build a CliApp from a darwin-config key.

    Args:
        config: dotted config key, e.g. ``"fetcher"`` or ``"fetcher.cli"``.
        mount: optional additional mount prefix (rarely needed when the key
            already includes the mount).
        prog / help / **kwargs: forwarded to :class:`CliApp`.
    """
    from darwin_config import get_config as _get_config

    data = _get_config(config, {})
    if not data:
        raise ValueError(f"Config key '{config}' is empty or missing")

    return CliApp.from_config(
        data,
        prog=prog,
        help=help,
        mount=mount,
        **kwargs,
    )


def from_file(
    path: str,
    mount: Optional[str] = None,
    prog: Optional[str] = None,
    help: Optional[str] = None,
    **kwargs: Any,
) -> CliApp:
    """Build a CliApp by first loading a config file into darwin-config.

    Args:
        path: filesystem path to a JSON/YAML/TOML file.
        mount: mount point passed to ``init_config``.
    """
    from darwin_config import get_config as _get_config, init_config

    init_config(files=[path], mount=mount or "")
    data = _get_config(mount or "", {}) if mount else _get_config("", {})
    return CliApp.from_config(data, prog=prog, help=help, **kwargs)


__all__ = ["get_loader", "from_config", "from_file"]
