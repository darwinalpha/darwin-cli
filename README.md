# darwin-cli

[English](README.md) · [简体中文](README.cn.md)

A **declaration-driven CLI engine**: parameters are not passive slots waiting
for a value. They can compute values, infer other parameters, declare new
parameters at runtime, and enforce relationships with each other — all from a
config file if you want.

- **Zero third-party dependencies in the core** — only the Python standard library
- One DSL for everything: static params, Actions, dynamic params, dependency
  ordering, validation, and cross-parameter constraints
- **Config-file driven**: `CliApp.from_config()` reads `cli_args` / `constraints`
  from JSON, a dict, or any loader callback
- **Optional darwin-config adapter** for keeping params in a layered config file
  (see section 6)
- A **small, stable API**: `CliApp`, `Param`, `ActionResult`, `CliResult`,
  `register_action`, plus a handful of helpers

```bash
pip install darwin-cli
```

Python >= 3.10.

---

## 1. At a glance: what an app looks like

The same parameter declaration in three equivalent forms.

**`fetch.json`** — everything in a config file:

```json
{
  "prog": "fetch.py",
  "help": "Fetch market data",
  "cli_args": {
    "type": {
      "type": "str",
      "required": true,
      "action": "load_dynamic_params",
      "depends_on": ["source"],
      "help": "Data type"
    },
    "source": { "type": "str", "action": "guess_source" },
    "date": { "type": "str" },
    "year": { "type": "str" }
  },
  "constraints": [
    { "rule": "mutually_exclusive", "params": ["date", "year"] }
  ]
}
```

**Python dict** — callables allowed:

```python
from darwin_cli import CliApp

app = CliApp.from_config({
    "cli_args": {
        "type": {"required": True, "action": load_dynamic_params, "depends_on": ["source"]},
        "source": {"action": guess_source},
        "date": {},
        "year": {},
    },
    "constraints": [{"rule": "mutually_exclusive", "params": ["date", "year"]}],
})
```

**Param objects** — full control:

```python
from darwin_cli import CliApp, Param

app = CliApp(
    params=[
        Param(name="type", required=True, action=load_dynamic_params, depends_on=["source"]),
        Param(name="source", action=guess_source),
        Param(name="date"),
        Param(name="year"),
    ],
    constraints=[{"rule": "mutually_exclusive", "params": ["date", "year"]}],
    prog="fetch.py",
)
```

What the engine does for you:

```python
@register_action("guess_source")
def guess_source(value, ctx):
    if value is not None:            # user supplied --source: do not interfere
        return {}
    return {"source": "tushare"}     # otherwise infer it

@register_action("load_dynamic_params")
def load_dynamic_params(value, ctx):
    return ActionResult(params=[     # declare params that did not exist at startup
        Param(name="symbol", type=ValidationRule(pattern=r"^\d{6}\.(SH|SZ)$"), required=True),
        Param(name="fields", default="close"),
    ])

result = app.run(["--type", "stock_daily", "--symbol", "600000.SH"])
print(result.outcome, result.data)
# ok {'type': 'stock_daily', 'source': 'tushare', 'symbol': '600000.SH', 'fields': 'close'}
```

`--source` was inferred, `symbol` / `fields` did not exist when parsing started,
and `--date` / `--year` cannot both be used — none of that required an
`if/else` in `main()`.

> `examples/` contains 8 runnable scenarios with a demo script. Run
> `python examples/demo.py` from the repository root.

---

## 2. Syntax quick reference

### `Param` fields

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | `str` | CLI name (`--name`); also the key in `cli_args` |
| `type` | `"str" \| "int" \| "float" \| "bool"` or `ValidationRule` | A rule object implies `str` |
| `required` | `bool` | Must come from the CLI or an Action — **not** from a default |
| `default` | value or `Callable(ctx)` | Static value, or a function evaluated during execution |
| `help` | `str` or `Callable(ctx)` | Static text, or help generated from the current context |
| `action` | name or `Callable(value, ctx)` | Registered Action name, or a function directly |
| `validation` | `ValidationRule` | Extra rules when `type` is a string |
| `depends_on` | `list[str]` | Parameters that must be processed before this one |

### `ValidationRule` fields

| Field | Applies to | Check |
| --- | --- | --- |
| `choices` | any | value must be in the list |
| `min` / `max` | numbers | inclusive numeric bounds |
| `min_length` / `max_length` | strings | inclusive length bounds |
| `pattern` | strings | `re.match` (prefix match — anchor with `$` for exact match) |
| `custom` | any | name of a validator registered via `custom_validators=...` |

Type coercion happens before rules: `str` casts with `str()`, `int` / `float`
with their constructors, and `bool` accepts `true/1/yes/on/t` and
`false/0/no/off/f` (lowercase strings only). `None` is returned unchanged for
optional params — required checks live in the executor, not the validator.

### `Constraint` rules (config top-level `constraints`)

| Rule | Config | Meaning |
| --- | --- | --- |
| `mutually_exclusive` | `{"rule":"mutually_exclusive","params":["date","year"]}` | at most one |
| `together` | `{"rule":"together","params":["user","token"]}` | all or none |
| `requires` | `{"rule":"requires","param":"type","requires":"source"}` | A present implies B present |
| `exclusive_with` | `{"rule":"exclusive_with","param":"date","group":["start_date","end_date"]}` | A excludes a whole group |
| `at_least_one` | `{"rule":"at_least_one","params":["source","file"]}` | at least one must be present |

Optional keys on any rule: `"message"` (override the default English error) and
`"include_generated": true` (also count Action-produced values, not just CLI
args). By default **only explicitly supplied CLI arguments are checked**, so an
Action expanding `date → start_date/end_date` never triggers a false conflict.

### `ActionResult` and `CliResult`

| Type | Fields | Purpose |
| --- | --- | --- |
| `ActionResult` | `values: dict`, `params: list[Param]` | backfill values and/or declare new parameters |
| `CliResult` | `success`, `data`, `error`, `exit_code`, `outcome` | result of `run()`; `outcome` is `ok` / `help` / `error` |

`ParamInfo.from_source` is the decision key throughout: `"cli"` (explicit user
argument), `"default"` (static/callable default), or `"action"` (produced by an
Action).

---

## 3. Core APIs in practice

### `CliApp(params, ..., constraints=..., registry=...)`

The facade. `params` accepts `list[Param]` or a dict of declarations.
Other constructor arguments:

```python
app = CliApp(
    params=[...],
    prog="fetch.py",                       # program name in help
    help="Fetch market data",             # also accepts description=
    max_iterations=100,                   # safety net for the deferred loop
    action_modules=["myapp.actions"],     # import modules that register Actions
    custom_validators={"even": lambda v: ...},
    available_sources=["tushare", "yahoo"],  # listed in global help
    constraints=[...],
    registry=ActionRegistry(),            # omit for the global registry
)
```

Useful attributes after a run: `app.params` (static + dynamic),
`app.static_params`, `app.dynamic_params`, `app.get_param(name)`.

### `CliApp.from_config(config, prog=None, help=None, loader=None, mount=None, **kwargs)`

```python
app = CliApp.from_config("config/fetch.json")                 # JSON, stdlib only
app = CliApp.from_config({"cli_args": {...}})                  # dict
app = CliApp.from_config("fetcher.cli", loader=my_loader)     # custom source
app = CliApp.from_config("settings.json", mount="fetcher.cli")  # nested section
```

`mount` walks a dotted path into the loaded dict before extracting `cli_args`
(or `params`), `constraints`, `prog` and `help`. `loader` is any callable that
turns the string into a dict; without one, the string is treated as a JSON path.

### `run(args=None)` and `run_or_exit(args=None)`

```python
result = app.run(["--type", "stock_daily"])
if result.outcome == "ok":
    handle(result.data)
elif result.outcome == "help":
    pass                    # help text already printed; exit_code == 0
else:
    log(result.error)       # exit_code == 1

data = app.run_or_exit()    # reads sys.argv[1:]; exits on any non-ok outcome
```

`run()` **never exits the process** — it returns a `CliResult`, which makes the
app easy to embed and test. `CliResult.ok(data)`, `CliResult.help()` and
`CliResult.fail(error, exit_code=1)` are the factory helpers.

### `register_action(name, *, registry=None)` and `ActionRegistry`

```python
from darwin_cli import ActionRegistry, register_action

@register_action("guess_source")        # global registry
def guess_source(value, ctx): ...

reg = ActionRegistry()                  # isolated registry for one app
@register_action("guess_source", registry=reg)
def isolated(value, ctx): ...

app = CliApp(params=[...], registry=reg)
```

`has_action` / `get_action` / `list_actions` / `clear_actions` all accept the
same optional `registry`. `ACTION_REGISTRY` and `GLOBAL_ACTIONS` both point to
the process-wide registry. `load_actions_from_module(path)` imports a module so
its decorators run; `validate_before(fn)` wraps an Action with a pre-check.

### `ActionResult` — the return value of an Action

```python
@register_action("expand_year")
def expand_year(value, ctx):
    if value is None:
        return {}
    return ActionResult(
        values={"start_date": f"{value}-01-01", "end_date": f"{value}-12-31"},
        params=[Param(name="start_date"), Param(name="end_date")],
    )
```

Returning a plain dict is shorthand for `ActionResult(values=that_dict)`.
`values` fills or overwrites values; `params` gives the new names a formal
definition so they take part in validation, help, and further processing.

### Validation helpers

```python
from darwin_cli import Validator, create_validator, parse_args_with_meta, build_parser

validator = create_validator(custom_validators={"even": lambda v: v if v % 2 == 0 else None})
validator.validate_one(Param(name="n", type="int"), "4")   # -> 4

meta = parse_args_with_meta(params, ["--type=stock_daily", "--count", "3"])
meta["type"].from_source        # 'cli'
meta["count"].from_source       # 'cli'
parser = build_parser(params, prog="fetch.py")
```

`parse_params_from_config`, `parse_constraints`, `merge_params`,
`params_to_dict`, `get_param_by_name`, `check_constraint` and
`check_constraints` are also exported for building custom front-ends.

### Exceptions

`ActionError`, `ConflictError` (subclass), `ConstraintError` (subclass, with
`.violations`), `CycleDetected` (subclass), `HelpRequested`,
`MaxIterationsExceeded`, `RequiredError`. All error messages are English;
`CliApp.run()` converts them into a `CliResult` and prints contextual help.

---

## 4. Features in detail

### 4.1 Exact source tracking

`--key value`, `--key=value` and bare `--flag` are all recorded by custom
`argparse.Action` subclasses, not by scanning raw `argv`. So
`from_source == "cli"` is reliable — the earlier O(n²) argv scan used to
mislabel `--key=value`. This matters for three decisions: required checks,
constraint checks, and whether an Action may overwrite a value.

### 4.2 Dynamic parameters

An Action can return `ActionResult(params=[...])`. The executor registers the
new definitions in the middle of a run. A value supplied on the command line for
a not-yet-declared name is captured as an unknown argument, then formally
validated once the definition appears. This is the capability `argparse` cannot
offer: its parameter set is frozen before parsing starts.

```python
r = app.run(["--type", "stock_daily", "--symbol", "600000.SH"])
# tushare branch declares symbol+fields; yahoo branch declares symbol+interval
```

### 4.3 `depends_on` and real cycle detection

When a parameter's dependencies are not yet processed, it is put back into the
queue behind them. Declaration order does not matter. Cycles are found by a DFS
over the `depends_on` graph (three-color marking) and reported with the actual
path, e.g. `Dependency cycle detected: a -> b -> c -> a` → `CycleDetected`.
`max_iterations` remains as a safety net for runaway chains.

### 4.4 Value expansion and chaining

Values written by an Action are marked dirty and re-queued, so `A` producing `B`
producing `C` converges automatically. Write Actions idempotently
(`if value is not None: return {}`) because a parameter may be revisited.

### 4.5 Validation

Coercion → `ValidationRule` checks → custom validator, in that order. A rule
object used as `type` implies `str` coercion first. `pattern` uses `re.match`,
so `"^\\d{6}\\.SH$"` matches exactly while `"^\\d{6}\\.SH"` also allows a
suffix. Custom validators are registered with
`CliApp(custom_validators={...})` and referenced by name from `ValidationRule.custom`.

### 4.6 Cross-parameter constraints

Relationships between parameters are declared in config rather than written as
Actions. Constraints run **after** the deferred loop (so all generated values
exist) but **before** required checks, and by default inspect only `cli`-sourced
values:

```python
r = app.run(["--date", "2026-01-01", "--year", "2026"])
# CliResult(outcome='error', error="Parameters ['date', 'year'] are mutually exclusive; ...")
```

Use `"include_generated": true` on a rule when Action-produced values must
count. Complex, business-specific conditions (lookups, multi-step computation)
still belong in Actions; the two mechanisms coexist.

### 4.7 Context-aware help

`--help` is moved to the **end** of the queue. With `--help` alone the engine
shows global help immediately; combined with other arguments it first runs
inference and dynamic-param discovery, then shows scenario help:

```text
$ python fetch.py --help
Usage: fetch.py [global options]
Global options:
  --type <str> [required]
  --source <str>
  --help            Show this help message

$ python fetch.py --type stock_daily --help
Usage: fetch.py --source tushare [options]
Source: tushare
Options:
  --type <str> [required]
  (dynamic) --symbol <str> [required] pattern: ^\d{6}\.(SH|SZ)$
  --help            Show this help message
```

A `help` value may be a `Callable(ctx)`; if it raises, the line degrades to
`(help generation failed: ...)` instead of breaking the whole run. Note that a
help request returns `success=False` with `exit_code=0` — use `outcome == "help"`
to distinguish it from an error.

### 4.8 Isolated Action registries

The global registry is convenient but process-wide. Pass `registry=ActionRegistry()`
to `CliApp` and `register_action(..., registry=reg)` to keep multiple apps in one
process from colliding on Action names. Omitting it keeps the classic
`@register_action("name")` behaviour.

---

## 5. Execution pipeline and precedence

`Executor.run()` is a deferred loop, not a one-pass parse.

| # | Phase | What happens |
| --- | --- | --- |
| 1 | Help short-circuit | `--help` with no other actionable input → global help immediately |
| 2 | Defaults | apply static / callable defaults; source becomes `default` |
| 3 | Pending queue | every declared parameter is queued |
| 4 | Help goes last | `--help` is moved to the tail so inference runs first |
| 5 | Deferred loop | pop → dependency check (requeue or raise `CycleDetected`) → validate → Action → merge `ActionResult` (new `params` are queued too) → mark processed |
| 6 | Unknown args | CLI args that never received a definition → `ActionError: Unknown parameter: --x` |
| 7 | Re-validation | re-check only values touched by Actions |
| 8 | Constraints | evaluate cross-parameter rules (explicit CLI args by default) |
| 9 | Required | value must exist and come from `cli` or `action` |
| — | Return | `{name: value}` wrapped in `CliResult` |

**Value precedence (high → low)**: an existing CLI or Action-produced value is
never overwritten by a later Action → a new Action value → static / callable
default. When an Action declares a parameter that already holds a CLI value, the
value is kept and the definition is attached.

**Gotchas worth knowing**

1. `required=True` together with a static `default` still fails: defaults are not
   a valid source for required values ("must come from CLI or an Action").
2. A plain dict returned by an Action is treated as `values`; only
   `ActionResult(params=...)` declares new parameters.
3. `pattern` is a prefix match (`re.match`); anchor with `$`.
4. Bool flags: `default=True` makes `--flag` set `False`, otherwise `--flag`
   sets `True`.
5. `CliApp.run()` prints help / error help to stdout; capture it if you embed
   the app in another program.
6. `constraints` are checked before `required`, so a missing required param can
   also surface as an `at_least_one` violation.

---

## 6. Ecosystem integration

### darwin-config (optional adapter)

Keep parameter declarations in a JSON / YAML / TOML config managed by
[darwin-config](https://github.com/darwinalpha/darwin-config). The adapter lives
in `darwin_cli.integrations.darwin_config` and is **not imported by the core**:
importing it is what pulls in darwin-config, so `darwin-cli` itself stays
dependency-free.

```python
from darwin_cli.integrations.darwin_config import from_config, from_file, get_loader

app = from_config("fetcher.cli", prog="fetch.py")                 # dotted key
app = from_file("config/settings.yaml", mount="fetcher", prog="fetch.py")
app = CliApp.from_config("cli", loader=get_loader("fetcher"), prog="fetch.py")
```

`from_config` reads a dotted key via `get_config`, `from_file` initialises
darwin-config from a file first, and `get_loader` returns a loader callback for
`CliApp.from_config`. Any of these can be combined with `mount` to select a
sub-tree.

### Other consumers

`darwin-fetch` consumes this library to build data-fetching CLIs. When
migrating from `darwin_common.cli`, the API names are unchanged — only the
package name differs. New capabilities (`constraints`, `from_config`,
`outcome`, instance registries) require importing `darwin_cli`.

### When not to use it

This is **not** a general-purpose CLI framework competitor. For a script with a
few fixed options, `argparse` or `click` is simpler; for subcommands, shell
completion and coloured help, use `click` / `typer`. darwin-cli targets tools
whose parameter set changes with context: swappable data sources, dynamic
parameter discovery, inference and chained dependencies between parameters.
See `docs/by-example.md` for a scenario-by-scenario comparison.

---

## 7. Tests

```bash
pip install -e '.[test]'
pytest tests -q
# or: uv run --extra test python -m pytest tests -q
```

Tests are split into `tests/unit/` (one file per module: base, actions, loader,
parser, validator, executor, help, app, constraints, registry, source tracking,
cycle detection, config integration) and `tests/integration/` (end-to-end fetch
workflows, complex chains, and `test_examples.py`, which executes every config
under `examples/`). All error-message assertions are in English.

Samples in `examples/` are covered by integration tests, so they stay
executable documentation.

> Publishing a new version: see the [release guide](docs/releasing.md).

## 8. License

MIT
