# darwin-cli by example

[English](by-example.md) · [简体中文](by-example.cn.md)

> An introductory guide. Source details live in `src/darwin_cli/`; the API list
> is in the [README](../README.md). Runnable samples are in
> [examples/](../examples/README.md).
>
> In one sentence: **this is not an ordinary argument parser, but a small
> workflow engine whose parameters do the work themselves.**

---

## The pain point first

A market-data script written with plain `argparse`:

```python
parser.add_argument("--type", required=True)   # stock_daily / index_daily
parser.add_argument("--source")                # tushare / yahoo
parser.add_argument("--symbol")                # tushare wants 600000.SH, yahoo wants AAPL
parser.add_argument("--interval")              # only yahoo needs it
```

The problems: users must memorise the `type → source` mapping; `--help` lists
every option without saying which ones apply right now; `main()` fills up with
`if/else`.

darwin-cli's idea: **a parameter is not a passive slot but an active unit that
carries logic and can generate other parameters.**

---

## Example 1: smallest possible use

```python
from darwin_cli import CliApp, Param

app = CliApp(
    params=[
        Param(name="name", type="str", required=True, help="Name to greet"),
        Param(name="count", type="int", default=1, help="Repetitions"),
    ],
    prog="hello.py",
)

result = app.run(["--name", "World", "--count", "3"])
print(result.success, result.outcome, result.data)
# True ok {'name': 'World', 'count': 3}
```

`run()` does not exit the process; it returns a `CliResult`. `outcome`
distinguishes `ok` / `help` / `error`. Use `run_or_exit()` at a script entry point.

**Is this optimal?** For two fixed options, no — `argparse` is shorter. The
benefit here is testability: you can call `run()` with an argv list and assert on
the result instead of spawning a process.

---

## Example 2: a parameter computes another one

```python
from darwin_cli import CliApp, Param, register_action

@register_action("guess_source")
def guess_source(value, ctx):
    if value is not None:            # user explicitly gave --source: respect it
        return {}
    t = ctx["type"].value
    return {"source": "tushare" if t == "stock_daily" else "yahoo"}

app = CliApp(
    params=[
        Param(name="type", type="str", required=True),
        Param(name="source", type="str", action="guess_source"),
    ],
    prog="fetch.py",
)

print(app.run(["--type", "stock_daily"]).data)
# {'type': 'stock_daily', 'source': 'tushare'}
```

An Action receives `(value, current_args)`; `current_args` is the full context,
so it can read `type` to derive `source`. The returned dict means "add these
values to the parameter table".

**When to use it**: keep mapping rules in code instead of in the user's head.
With only one rule, a hand-written `if` is simpler; once rules multiply, each
Action owns one decision and can be tested in isolation.

---

## Example 3: parameters grow at runtime

Different sources need different parameters:

```python
from darwin_cli import ActionResult, CliApp, Param, ValidationRule, register_action

@register_action("load_params")
def load_params(data_type, ctx):
    source = ctx["source"].value
    if source == "tushare":
        return ActionResult(params=[
            Param(name="symbol", type=ValidationRule(pattern=r"^\d{6}\.(SH|SZ|BJ)$"),
                  required=True, help="A-share code"),
            Param(name="fields", type="str", default="close", help="Fields"),
        ])
    return ActionResult(params=[
        Param(name="symbol", type="str", required=True, help="Ticker"),
        Param(name="interval", type="str", default="1d",
              validation=ValidationRule(choices=["1d", "1wk", "1mo"]), help="Interval"),
    ])

app = CliApp(
    params=[
        Param(name="type", type="str", required=True, action="load_params"),
        Param(name="source", type="str"),
    ],
    prog="fetch.py",
)

r1 = app.run(["--type", "stock_daily", "--source", "tushare", "--symbol", "600000.SH"])
print(r1.data["symbol"], r1.data["fields"])     # 600000.SH close
r2 = app.run(["--type", "stock_daily", "--source", "yahoo", "--symbol", "AAPL"])
print(r2.data["symbol"], r2.data["interval"])   # AAPL 1d
```

`symbol` was never declared statically, yet the user can pass it: the engine
first accepts it as an unknown argument, then validates it properly once an
Action declares it. `argparse` cannot do this — its parameter set is frozen
before parsing starts.

**Is this optimal?** This is the library's least replaceable capability. If your
parameter set changes with context, nothing in `argparse`/`click` covers it
without hand-rolling a two-phase parser.

---

## Example 4: who runs first

`type`'s Action needs `source`, but `type` is declared first. `depends_on` fixes it:

```python
Param(name="type", type="str", required=True,
      action="load_params",
      depends_on=["source"],      # process source first
      help="Data type"),
Param(name="source", type="str", action="guess_source"),
```

The engine notices `source` is not processed yet and moves `type` to the back of
the queue. Cycles are caught by a **real dependency-graph DFS** with the actual
path reported (`CycleDetected`), not by "retry five times" heuristics.

---

## Example 5: one input becomes two

```python
@register_action("expand_year")
def expand_year(value, ctx):
    if value is None:
        return {}
    return ActionResult(
        values={"start_date": f"{value}-01-01", "end_date": f"{value}-12-31"},
        params=[Param(name="start_date", type="str"), Param(name="end_date", type="str")],
    )

app = CliApp(params=[Param(name="year", action="expand_year")], prog="fetch.py")
r = app.run(["--year", "2026"])
print(r.data["start_date"], r.data["end_date"])   # 2026-01-01 2026-12-31
```

`values` fills in values; `params` gives the new names a formal definition so
they take part in validation and help.

---

## Example 6: chained reactions

A parameter written by an Action is re-queued, so chains converge automatically:

```python
@register_action("chain_a")
def chain_a(value, ctx):
    return ActionResult(values={"b": "from_a"},
                        params=[Param(name="b", type="str", action="chain_b")])

@register_action("chain_b")
def chain_b(value, ctx):
    return ActionResult(values={"c": "from_b"},
                        params=[Param(name="c", type="str", action="chain_c")])

@register_action("chain_c")
def chain_c(value, ctx):
    return {"result": "done"}

app = CliApp(params=[Param(name="start", required=True, action="chain_a")])
print(app.run(["--start", "go"]).data)
# {'start': 'go', 'b': 'from_a', 'c': 'from_b', 'result': 'done'}
```

Write Actions to be idempotent (`if value is not None: return {}`), because a
parameter may be revisited several times.

**Is this optimal?** Chains are powerful but harder to debug than plain
functions. Prefer a single Action that returns all values when the steps are
fixed; use chaining only when the set of steps itself is discovered at runtime.

---

## Example 7: relationships without writing an Action

Mutual exclusion, co-occurrence and friends no longer need a hand-written
validator attached to every Action:

```python
app = CliApp(
    params=[
        Param(name="date"), Param(name="year"),
        Param(name="user"), Param(name="token"),
        Param(name="source"), Param(name="file"),
    ],
    constraints=[
        {"rule": "mutually_exclusive", "params": ["date", "year"]},
        {"rule": "together", "params": ["user", "token"]},
        {"rule": "at_least_one", "params": ["source", "file"]},
    ],
)

r = app.run(["--date", "2026-01-01", "--year", "2026", "--source", "x"])
print(r.outcome, r.error)
# error Parameters ['date', 'year'] are mutually exclusive; provide at most one
```

Five built-in rules:

| Rule | Config | Meaning |
| --- | --- | --- |
| `mutually_exclusive` | `params: [a, b]` | at most one |
| `together` | `params: [user, token]` | all or none |
| `requires` | `param: type, requires: source` | A implies B |
| `exclusive_with` | `param: date, group: [start_date, end_date]` | A excludes a group |
| `at_least_one` | `params: [source, file]` | at least one |

**Key semantics**: constraints inspect only explicitly supplied CLI arguments,
not Action-produced values. So a `date → start_date/end_date` expansion does not
falsely report "`date` conflicts with `start_date`". Add
`"include_generated": true` to a rule when generated values must count.

Complex conditional logic (config lookups, database queries) still belongs in
Actions; both mechanisms coexist.

**Is this optimal?** For these five shapes, yes — one line of config beats a
validator function. For anything requiring external state, an Action is clearer
than trying to encode it as rules.

---

## Example 8: config-file driven

Both parameter declarations and relationships can live in a file:

```json
{
  "help": "fetch data",
  "cli_args": {
    "type": {
      "type": "str", "required": true,
      "action": "load_dynamic_params", "depends_on": ["source"]
    },
    "source": {"type": "str", "action": "guess_source"},
    "date": {"type": "str"},
    "year": {"type": "str"}
  },
  "constraints": [
    {"rule": "mutually_exclusive", "params": ["date", "year"]}
  ]
}
```

```python
app = CliApp.from_config("params.json", prog="fetch.py")
result = app.run()   # reads sys.argv[1:]
```

To integrate with darwin-config (optional module, core stays dependency-free):

```python
from darwin_cli.integrations.darwin_config import from_config
app = from_config("fetcher.cli", prog="fetch.py")
```

JSON cannot express callables, so `action` is a name looked up in the registry;
dynamic defaults/help still require code.

---

## Example 9: help that adapts to context

```bash
$ python fetch.py --help
Usage: fetch.py [global options]

Global options:
  --type <str> [required]
  --source <str>
  --help            Show this help message

$ python fetch.py --type stock_daily --source tushare --help
Usage: fetch.py --source tushare [options]

Source: tushare

Options:
  --type <str> [required]
  (dynamic) --symbol <str> [required]
  (dynamic) --fields <str> (default: close)
  --help            Show this help message
```

`--help` is placed at the end of the queue: alone it shows global help
immediately; with other arguments it first runs inference and dynamic-parameter
discovery, then shows scenario help.

---

## Example 10: isolating multiple apps

The new library supports instance-level Action registries to avoid global name
collisions:

```python
from darwin_cli import ActionRegistry, CliApp, Param, register_action

reg = ActionRegistry()

@register_action("infer", registry=reg)
def infer(value, ctx):
    return {"source": "tushare"}

app = CliApp(
    params=[Param(name="type", action="infer"), Param(name="source")],
    registry=reg,
)
```

Without `registry`, the global registry is used and the classic
`@register_action("name")` style remains fully compatible.

---

## Example 11: groups — relations among many parameters

Five rules are enough for a handful of params, but writing a top-level
`constraints` entry for every pair gets noisy. `groups` lets you name a set of
parameters once and relate sets to each other:

```json
{
  "cli_args": {
    "date":       { "type": "str" },
    "start_date": { "type": "str", "together": "end_date" },
    "end_date":   { "type": "str" },
    "year":       { "type": "str" },
    "window":     { "type": "str" }
  },
  "groups": {
    "@sedate": ["start_date", "end_date"],
    "@instant": ["date", "window"],
    "@date_range": {
      "members": ["@sedate", "year"],
      "exclusive_with": ["@instant"]
    },
    "@dates": {
      "members": ["@instant", "@date_range"],
      "at_least_one": true
    }
  }
}
```

- `@sedate` / `@instant` are pure member lists; `@date_range` nests `@sedate`,
  and `@dates` nests both — groups are macros for **flat parameter-name lists**.
- `start_date.together: "end_date"` is a **one-to-one** inline relation. Inline
  values are a single parameter name, never a list, never an `@group`.
- `@date_range.exclusive_with: ["@instant"]` is a **group ↔ group** relation: a
  date range cannot be mixed with a single date/window, but the range's own
  members can still appear together.
- `@dates.at_least_one: true` is a **group-internal** rule: at least one date
  input must be given.

Everything compiles to 5 plain `Constraint` objects, so the runtime needs no
notion of a group. `CliApp(..., groups=...)` works with `Param` objects too, and
misspelled keys / group names, cycles and empty groups fail at load time rather
than silently disabling a rule.

**Is this optimal?** Yes for structural relationships: one declaration replaces
a web of pairwise rules. For conditions that depend on *values*
(`source == "file"` implies `path`), an Action is still the right tool.

> **Design mistake to avoid**: relating a parent group to its own child
> (`@dates` excluding `@date_range`) is contradictory after expansion — the
> members end up excluding each other and the group's own `together` rule breaks.
> Place relations where the two sides are disjoint; that is the config author's
> decision, not something the library second-guesses.

---

## What changed compared with the old library

| Item | Old | New |
| --- | --- | --- |
| Dependencies | pulled in dotenv/pandas/pyarrow via `darwin_common` | core has zero dependencies |
| Python | ≥3.11 (in practice ≥3.12) | ≥3.10 |
| Source tracking | scanned argv; `--key=value` mislabeled | custom argparse Action, exact and O(1) |
| Cycle detection | "retry 5 times" heuristic | real dependency-graph DFS with the cycle path |
| Final validation | full repeated pass | only values touched by Actions |
| Relationships | Action + `@validate_before` only | config-driven, 5 built-in rules |
| Config integration | caller manually did `get_config → parse_params` | `CliApp.from_config` + optional adapter |
| Action registry | global singleton | global plus optional per-instance |
| Result state | guessed from `success` + `exit_code` | explicit `outcome` |
| Dead code | several leftovers | removed |

---

## Is it the best solution?

It depends on the scenario:

| Scenario | Better choice |
| --- | --- |
| A small script with a few fixed options | `argparse` / `click` |
| Subcommands, completion, coloured help | `click` / `typer` |
| Parameters vary with source/type | **darwin-cli** |
| Inference, expansion, chained dependencies between params | **darwin-cli** |
| Simple relationships (mutual exclusion / co-occurrence) | **darwin-cli's constraints** (no Action needed) |
| Part of the Darwin toolchain | **darwin-cli** (pairs with darwin-config) |

**Conclusion**: it is not a general-purpose CLI framework, but a micro workflow
engine for configuration-driven data-fetching tools. It fits its target
scenario well; outside it, it is neither nicer than `click` nor simpler than
`argparse`.
