# examples/ sample index

[English](README.md) · [简体中文](README.cn.md)

Every scenario is a **JSON config file** in `configs/` plus a runnable demo.
No third-party packages are needed: `from_config()` reads JSON with the standard
library and `demo.py` inserts `src/` into `sys.path` itself.

```bash
# From the repository root (works without installing the package)
python examples/demo.py
PYTHONPATH=src python examples/demo.py

# After installing
python examples/demo.py
```

| # | Config | Features demonstrated | Try it with |
| --- | --- | --- | --- |
| 01 | `configs/01-basic.json` | Static params, `run()` returns a `CliResult`, required + default | `--name World --count 3` |
| 02 | `configs/02-inference.json` | An Action infers `--source` from `--type`; explicit user value wins | `--type stock_daily` |
| 03 | `configs/03-dynamic.json` | `ActionResult(params=...)` grows the parameter set per source; `depends_on` | `--type stock_daily --symbol 600000.SH` |
| 04 | `configs/04-constraints.json` | All five built-in constraint rules, written only in config | `--source tushare` |
| 05 | `configs/05-validation.json` | `int` coercion, `min/max`, `choices`, `min_length/max_length`, regex, bool flag | `--count 5 --status active --overwrite` |
| 06 | `configs/06-depends.json` | `depends_on` reorders processing; `ActionResult(values=...)` expands one input | `--year 2026` |
| 07 | `configs/07-help.json` | Context-aware help: bare `--help` vs scenario help after inference | `--type stock_daily --help` |
| 08 | `configs/08-mount.json` | `mount` selects a sub-tree; defaults do not trigger constraints | `--type stock_daily --output a.csv --stdout` |
| 09 | `configs/09-groups.json` | Nested groups, one-to-one inline relations, group↔group / group↔param rules | `--date d` |

`actions.py` holds the four Action functions used by configs 02/03/06/07.
Call `actions.register_all()` (or `register_all(registry)`) before building an
app; it is idempotent, so it is safe to call after `clear_actions()`.

## Config file shape

```json
{
  "prog": "fetch.py",
  "help": "Description shown above the help text",
  "cli_args": {
    "type": {
      "type": "str",
      "required": true,
      "help": "Data type",
      "action": "load_dynamic_params",
      "depends_on": ["source"],
      "validation": { "choices": ["stock_daily", "stock_hist"] }
    },
    "source": { "type": "str", "action": "guess_source" }
  },
  "constraints": [
    { "rule": "mutually_exclusive", "params": ["date", "year"] }
  ]
}
```

- `cli_args` (or `params`) holds parameter declarations; each key becomes `--key`.
- `type` accepts `"str" | "int" | "float" | "bool"`, or a rule object such as
  `{"pattern": "..."}` (which implies `str`).
- `action` is a **name** registered in the Action registry, or a callable when
  building from a Python dict. JSON cannot express callables, so use names.
- `validation` / a dict-valued `type` becomes a `ValidationRule`.
- `constraints` is optional; see the five rules in the main README.
- `groups` is optional; it declares nested parameter groups and their relations
  (see section 4.9 of the main README, and `configs/09-groups.json`).
- Param inline relations are one-to-one: a single parameter name, never a list
  and never an `@group` reference.
- `prog` / `help` are optional and feed the generated help text.

## Three equivalent ways to declare params

```python
from darwin_cli import CliApp, Param

# 1) JSON file (zero dependencies)
app = CliApp.from_config("examples/configs/01-basic.json")

# 2) Python dict — callables allowed
app = CliApp.from_config({
    "cli_args": {
        "type": {"required": True, "action": guess_source},
        "count": {"type": "int", "default": 1},
    }
})

# 3) Param objects — full control
app = CliApp(params=[
    Param(name="type", required=True, action=guess_source),
    Param(name="count", type="int", default=1),
])
```

`CliApp.from_config(path, loader=my_loader)` accepts any callable that turns a
path/key into a dict. To read params from a darwin-config file, use the optional
adapter (the core library does **not** depend on darwin-config):

```python
from darwin_cli.integrations.darwin_config import from_config, from_file

app = from_config("fetcher.cli", prog="fetch.py")   # dotted config key
app = from_file("config/settings.yaml", mount="fetcher", prog="fetch.py")
```

## Notes

1. `--key=value`, `--key value` and bare `--flag` are all supported; source
   tracking is exact, so constraints never mistake a default for a user value.
2. Regex validation uses `re.match` (prefix match). Anchor with `$` when an
   exact match is required, as in `05-validation.json`.
3. `required=True` with a static `default` still fails: a required value must
   come from the CLI or an Action, not from a default.
4. Constraints only inspect explicitly supplied CLI arguments by default.
   Add `"include_generated": true` to a rule to also count Action-produced values.
5. Integration tests in `tests/integration/test_examples.py` run every config in
   this directory, so the samples are executable documentation.
