# examples/demo.py

"""Run every scenario under examples/configs/ with darwin-cli.

Usage (from the repository root):

    python examples/demo.py
    PYTHONPATH=src python examples/demo.py

No third-party packages are required. The script inserts ``src/`` into
``sys.path`` itself, so it works from a source checkout without installing.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for path in (str(ROOT / "src"), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from darwin_cli import CliApp  # noqa: E402

import actions  # noqa: E402

CONFIGS = HERE / "configs"


# ============================================================
# Helpers
# ============================================================


def make(name: str, **kwargs) -> CliApp:
    return CliApp.from_config(str(CONFIGS / name), **kwargs)


def quiet(app: CliApp, args: list[str]):
    """Run an app while capturing the help text it prints."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = app.run(args)
    return result, buffer.getvalue()


def show(label: str, result, help_text: str = "") -> None:
    print(f"\n  {label}")
    print(f"    outcome : {result.outcome}")
    if result.data is not None:
        print(f"    data    : {result.data}")
    if result.error is not None:
        print(f"    error   : {result.error}")
    if help_text:
        indented = "\n".join(f"    | {line}" for line in help_text.strip().splitlines())
        print(indented)


# ============================================================
# Scenarios
# ============================================================


def demo_basic() -> None:
    print("\n=== 01 Basics: run() returns a CliResult ===")
    app = make("01-basic.json")
    ok, _ = quiet(app, ["--name", "World", "--count", "3"])
    show("--name World --count 3", ok)
    bad, _ = quiet(app, [])
    show("(no arguments)", bad)


def demo_inference() -> None:
    print("\n=== 02 Inference: an Action fills --source ===")
    app = make("02-inference.json")
    inferred, _ = quiet(app, ["--type", "stock_daily"])
    show("--type stock_daily", inferred)
    explicit, _ = quiet(app, ["--type", "stock_hist", "--source", "yahoo"])
    show("--type stock_hist --source yahoo", explicit)


def demo_dynamic() -> None:
    print("\n=== 03 Dynamic params: the parameter set grows at runtime ===")
    app = make("03-dynamic.json")
    tushare, _ = quiet(app, ["--type", "stock_daily", "--symbol", "600000.SH"])
    show("--type stock_daily --symbol 600000.SH", tushare)
    yahoo, _ = quiet(
        app, ["--type", "stock_hist", "--source", "yahoo", "--symbol", "AAPL"]
    )
    show("--type stock_hist --source yahoo --symbol AAPL", yahoo)


def demo_constraints() -> None:
    print("\n=== 04 Constraints: five rules written in config ===")
    app = make("04-constraints.json")
    ok, _ = quiet(app, ["--source", "tushare"])
    show("--source tushare (satisfies all rules)", ok)
    clash, _ = quiet(app, ["--date", "2026-01-01", "--year", "2026", "--source", "tushare"])
    show("--date ... --year ... (mutual exclusion)", clash)
    together, _ = quiet(app, ["--user", "bob", "--source", "tushare"])
    show("--user bob (token missing)", together)
    requires, _ = quiet(app, ["--type", "stock_daily", "--file", "local.csv"])
    show("--type ... --file ... (source missing)", requires)


def demo_validation() -> None:
    print("\n=== 05 Validation: coercion, ranges, choices, regex, flags ===")
    app = make("05-validation.json")
    ok, _ = quiet(
        app,
        [
            "--count", "5",
            "--status", "active",
            "--name", "demo",
            "--symbol", "600000.SH",
            "--overwrite",
        ],
    )
    show("all valid", ok)
    bad, _ = quiet(app, ["--count", "200"])
    show("--count 200 (above maximum)", bad)


def demo_depends() -> None:
    print("\n=== 06 depends_on: ordering and value expansion ===")
    app = make("06-depends.json")
    result, _ = quiet(app, ["--year", "2026"])
    show("--year 2026", result)


def demo_help() -> None:
    print("\n=== 07 Context-aware help: --help runs last ===")
    app = make("07-help.json")
    global_result, global_text = quiet(app, ["--help"])
    show("--help alone", global_result, global_text)
    scenario_result, scenario_text = quiet(app, ["--type", "stock_daily", "--help"])
    show("--type stock_daily --help", scenario_result, scenario_text)


def demo_mount() -> None:
    print("\n=== 08 mount: select a sub-tree (also used by darwin-config) ===")
    app = make("08-mount.json", mount="fetcher.cli")
    ok, _ = quiet(app, ["--type", "stock_daily"])
    show("--type stock_daily (output default does not trigger exclusion)", ok)
    flag, _ = quiet(app, ["--type", "stock_daily", "--stdout"])
    show("--type ... --stdout (still fine: default is not an explicit arg)", flag)
    clash, _ = quiet(app, ["--type", "stock_daily", "--output", "a.csv", "--stdout"])
    show("--output a.csv --stdout (two explicit args conflict)", clash)


def main() -> None:
    actions.register_all()
    print("darwin-cli examples")
    print("Every scenario below is driven by a JSON file in examples/configs/.")
    demo_basic()
    demo_inference()
    demo_dynamic()
    demo_constraints()
    demo_validation()
    demo_depends()
    demo_help()
    demo_mount()
    print("\nDone.")


if __name__ == "__main__":
    main()
