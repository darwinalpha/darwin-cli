# darwin-cli

[English](README.md) · 简体中文

**声明驱动的命令行参数引擎**：参数不是"等待填值的空位"。它们可以计算取值、推断别的参数、在运行时声明新参数、彼此之间建立关系约束——而且这些都可以只写在配置文件里。

- **核心零第三方依赖**，只用 Python 标准库
- 一套 DSL 覆盖全部：静态参数、Action、动态参数、依赖排序、校验、跨参数关系约束
- **配置文件驱动**：`CliApp.from_config()` 从 JSON、字典或任意 loader 回调读取 `cli_args` / `constraints`
- **可选的 darwin-config 适配器**，把参数声明放进分层配置文件（见第 6 节）
- **小而稳定的 API**：`CliApp`、`Param`、`ActionResult`、`CliResult`、`register_action` 加少量辅助函数

```bash
pip install darwin-cli
```

Python ≥ 3.10。

---

## 1. 一眼看懂：一个 app 长什么样

同一份参数声明的三种等价写法。

**`fetch.json`** —— 全部写进配置文件：

```json
{
  "prog": "fetch.py",
  "help": "抓取行情数据",
  "cli_args": {
    "type": {
      "type": "str",
      "required": true,
      "action": "load_dynamic_params",
      "depends_on": ["source"],
      "help": "数据类型"
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

**Python 字典** —— 可以直接传函数：

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

**Param 对象** —— 完全掌控：

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

引擎替你做的事：

```python
@register_action("guess_source")
def guess_source(value, ctx):
    if value is not None:            # 用户显式传了 --source，不要干预
        return {}
    return {"source": "tushare"}     # 否则推断出来

@register_action("load_dynamic_params")
def load_dynamic_params(value, ctx):
    return ActionResult(params=[     # 声明启动时还不存在的参数
        Param(name="symbol", type=ValidationRule(pattern=r"^\d{6}\.(SH|SZ)$"), required=True),
        Param(name="fields", default="close"),
    ])

result = app.run(["--type", "stock_daily", "--symbol", "600000.SH"])
print(result.outcome, result.data)
# ok {'type': 'stock_daily', 'source': 'tushare', 'symbol': '600000.SH', 'fields': 'close'}
```

`--source` 是推断出来的，`symbol` / `fields` 在开始解析时并不存在，`--date` 和
`--year` 不能同时出现——这些都不需要在 `main()` 里写 `if/else`。

> `examples/` 下有 8 个可运行场景和一个演示脚本。在仓库根目录运行
> `python examples/demo.py`。

---

## 2. 语法速查

### `Param` 字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `name` | `str` | 命令行名（`--name`），也是 `cli_args` 里的键 |
| `type` | `"str" \| "int" \| "float" \| "bool"` 或 `ValidationRule` | 规则对象隐含 `str` |
| `required` | `bool` | 必须来自命令行或 Action——**不能**来自默认值 |
| `default` | 值或 `Callable(ctx)` | 静态值，或执行期求值函数 |
| `help` | `str` 或 `Callable(ctx)` | 静态文本，或根据当前上下文生成的帮助 |
| `action` | 名字或 `Callable(value, ctx)` | 已注册的 Action 名，或直接传函数 |
| `validation` | `ValidationRule` | `type` 为字符串时的附加规则 |
| `depends_on` | `list[str]` | 必须先于本参数处理的参数名 |

### `ValidationRule` 字段

| 字段 | 适用 | 检查 |
| --- | --- | --- |
| `choices` | 任意 | 值必须在列表内 |
| `min` / `max` | 数值 | 闭区间数值边界 |
| `min_length` / `max_length` | 字符串 | 闭区间长度边界 |
| `pattern` | 字符串 | `re.match`（前缀匹配，精确匹配要加 `$` 锚点） |
| `custom` | 任意 | 通过 `custom_validators=...` 注册的校验器名字 |

先做类型转换再做规则校验：`str` 用 `str()`，`int` / `float` 用各自的构造函数，
`bool` 接受 `true/1/yes/on/t` 与 `false/0/no/off/f`（仅小写字符串）。可选参数的
`None` 原样返回——必填检查在执行器里，不在校验器里。

### `Constraint` 规则（配置顶层 `constraints`）

| 规则 | 配置 | 含义 |
| --- | --- | --- |
| `mutually_exclusive` | `{"rule":"mutually_exclusive","params":["date","year"]}` | 最多一个 |
| `together` | `{"rule":"together","params":["user","token"]}` | 全有或全无 |
| `requires` | `{"rule":"requires","param":"type","requires":"source"}` | A 出现则 B 必须出现 |
| `exclusive_with` | `{"rule":"exclusive_with","param":"date","group":["start_date","end_date"]}` | A 与整组互斥 |
| `at_least_one` | `{"rule":"at_least_one","params":["source","file"]}` | 至少提供一个 |

任意规则还可加两个可选键：`"message"`（覆盖默认英文错误文案）与
`"include_generated": true`（把 Action 生成的值也计入，而不只是命令行参数）。
默认**只检查用户显式传入的命令行参数**，因此 `date → start_date/end_date`
这类展开不会误报冲突。

### `ActionResult` 与 `CliResult`

| 类型 | 字段 | 用途 |
| --- | --- | --- |
| `ActionResult` | `values: dict`、`params: list[Param]` | 回填取值和/或声明新参数 |
| `CliResult` | `success`、`data`、`error`、`exit_code`、`outcome` | `run()` 的结果；`outcome` 为 `ok` / `help` / `error` |

`ParamInfo.from_source` 是全流程的决策依据：`"cli"`（用户显式传入）、
`"default"`（静态/函数默认值）、`"action"`（由 Action 生成）。

---

## 3. 核心 API 实用案例

### `CliApp(params, ..., constraints=..., registry=...)`

统一门面。`params` 接受 `list[Param]` 或声明字典。其余构造参数：

```python
app = CliApp(
    params=[...],
    prog="fetch.py",                       # 帮助里的程序名
    help="抓取行情数据",                   # 也可用 description=
    max_iterations=100,                   # 延迟循环的安全上限
    action_modules=["myapp.actions"],     # 导入注册了 Action 的模块
    custom_validators={"even": lambda v: ...},
    available_sources=["tushare", "yahoo"],  # 列在全局帮助里
    constraints=[...],
    registry=ActionRegistry(),            # 省略则用全局注册表
)
```

运行后可用的属性：`app.params`（静态 + 动态）、`app.static_params`、
`app.dynamic_params`、`app.get_param(name)`。

### `CliApp.from_config(config, prog=None, help=None, loader=None, mount=None, **kwargs)`

```python
app = CliApp.from_config("config/fetch.json")                 # JSON，仅标准库
app = CliApp.from_config({"cli_args": {...}})                  # 字典
app = CliApp.from_config("fetcher.cli", loader=my_loader)     # 自定义来源
app = CliApp.from_config("settings.json", mount="fetcher.cli")  # 取子树
```

`mount` 先按点分路径钻进加载后的字典，再提取 `cli_args`（或 `params`）、
`constraints`、`prog` 和 `help`。`loader` 是任意"把字符串转成 dict"的可调用对象；
不传时字符串被当作 JSON 文件路径。

### `run(args=None)` 与 `run_or_exit(args=None)`

```python
result = app.run(["--type", "stock_daily"])
if result.outcome == "ok":
    handle(result.data)
elif result.outcome == "help":
    pass                    # 帮助已打印；exit_code == 0
else:
    log(result.error)       # exit_code == 1

data = app.run_or_exit()    # 读 sys.argv[1:]；非 ok 时自动退出
```

`run()` **不会退出进程**，而是返回 `CliResult`，便于嵌入和测试。
工厂方法为 `CliResult.ok(data)`、`CliResult.help()`、
`CliResult.fail(error, exit_code=1)`。

### `register_action(name, *, registry=None)` 与 `ActionRegistry`

```python
from darwin_cli import ActionRegistry, register_action

@register_action("guess_source")        # 全局注册表
def guess_source(value, ctx): ...

reg = ActionRegistry()                  # 单个 app 独占的注册表
@register_action("guess_source", registry=reg)
def isolated(value, ctx): ...

app = CliApp(params=[...], registry=reg)
```

`has_action` / `get_action` / `list_actions` / `clear_actions` 都接受同样的可选
`registry`。`ACTION_REGISTRY` 与 `GLOBAL_ACTIONS` 都指向进程级全局注册表。
`load_actions_from_module(path)` 导入模块以触发其中的装饰器；
`validate_before(fn)` 给 Action 包一层前置校验。

### `ActionResult` —— Action 的返回值

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

返回普通字典等价于 `ActionResult(values=那个字典)`。`values` 负责填值或覆盖，
`params` 让新名字获得正式定义，从而参与校验、帮助和后续处理。

### 校验与解析辅助

```python
from darwin_cli import Validator, create_validator, parse_args_with_meta, build_parser

validator = create_validator(custom_validators={"even": lambda v: v if v % 2 == 0 else None})
validator.validate_one(Param(name="n", type="int"), "4")   # -> 4

meta = parse_args_with_meta(params, ["--type=stock_daily", "--count", "3"])
meta["type"].from_source        # 'cli'
meta["count"].from_source       # 'cli'
parser = build_parser(params, prog="fetch.py")
```

`parse_params_from_config`、`parse_constraints`、`merge_params`、
`params_to_dict`、`get_param_by_name`、`check_constraint`、`check_constraints`
也都导出，方便构建自定义前端。

### 异常

`ActionError`、`ConflictError`（子类）、`ConstraintError`（子类，带
`.violations`）、`CycleDetected`（子类）、`HelpRequested`、
`MaxIterationsExceeded`、`RequiredError`。错误文案统一为英文；
`CliApp.run()` 会把它们转成 `CliResult` 并打印上下文帮助。

---

## 4. 特色功能详解

### 4.1 精确的来源跟踪

`--key value`、`--key=value`、裸 `--flag` 都由自定义 `argparse.Action` 子类记录，
而不是扫描原始 `argv`。因此 `from_source == "cli"` 是可靠的——早期版本用
O(n²) 的 argv 扫描，会把 `--key=value` 标错。这个判断直接影响三件事：必填校验、
约束校验、以及 Action 能否覆盖某个值。

### 4.2 动态参数

Action 可以返回 `ActionResult(params=[...])`，执行器在运行中途注册新定义。
用户为"尚未声明的名字"传入的值会先被当作未知参数收下，等定义出现后再正式校验。
这是 `argparse` 做不到的：它的参数集在解析开始前就固定了。

```python
r = app.run(["--type", "stock_daily", "--symbol", "600000.SH"])
# tushare 分支声明 symbol+fields；yahoo 分支声明 symbol+interval
```

### 4.3 `depends_on` 与真正的环检测

参数的依赖若尚未处理完，它会被放回队列、排到依赖后面，声明顺序不影响结果。
环通过 `depends_on` 图上的三色 DFS 检测，并报出真实路径，例如
`Dependency cycle detected: a -> b -> c -> a` → `CycleDetected`。
`max_iterations` 作为失控链的兜底保留。

### 4.4 值展开与链式反应

被 Action 写过的值会标脏并重新入队，于是 `A` 生成 `B`、`B` 生成 `C` 会自动收敛。
Action 要写成幂等的（`if value is not None: return {}`），因为同一参数可能被重新访问多次。

### 4.5 校验

顺序为：类型转换 → `ValidationRule` 规则 → 自定义校验器。规则对象作为 `type`
时隐含先做 `str` 转换。`pattern` 用 `re.match`，所以 `"^\\d{6}\\.SH$"` 是精确匹配，
`"^\\d{6}\\.SH"` 则允许后缀。自定义校验器通过 `CliApp(custom_validators={...})`
注册，并由 `ValidationRule.custom` 按名字引用。

### 4.6 跨参数关系约束

参数之间的关系写在配置里，而不必写成 Action。约束在延迟循环**之后**执行（此时
生成值都已存在）、在必填检查**之前**执行，且默认只看 `cli` 来源的值：

```python
r = app.run(["--date", "2026-01-01", "--year", "2026"])
# CliResult(outcome='error', error="Parameters ['date', 'year'] are mutually exclusive; ...")
```

需要把 Action 生成的值也算进去时，在规则上加 `"include_generated": true`。
复杂的业务条件（查配置、查库、多步计算）仍然用 Action，两种机制共存。

### 4.7 上下文帮助

`--help` 被移到队列**末尾**。单独 `--help` 时立即显示全局帮助；与其它参数一起时，
先跑完推断和动态参数发现，再显示场景帮助：

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

`help` 可以是 `Callable(ctx)`；若它抛异常，该行会降级为
`(help generation failed: ...)`，不会让整次运行崩掉。注意帮助请求返回
`success=False` 且 `exit_code=0`——请用 `outcome == "help"` 与错误区分。

### 4.8 实例级注册表隔离

全局注册表方便，但它是进程级的。给 `CliApp` 传
`registry=ActionRegistry()`，并配合 `register_action(..., registry=reg)`，
就能让同一进程里的多个 app 不因 Action 重名而冲突。省略时保持经典的
`@register_action("name")` 写法。

---

## 5. 执行流水线与优先级

`Executor.run()` 是一个延迟循环，不是一次性解析。

| # | 阶段 | 发生什么 |
| --- | --- | --- |
| 1 | 帮助短路 | 只有 `--help` 且没有其它可触发的 Action 参数 → 立即显示全局帮助 |
| 2 | 默认值 | 应用静态/函数默认值，来源标为 `default` |
| 3 | 待处理队列 | 所有已声明参数入队 |
| 4 | help 放队尾 | `--help` 移到末尾，让推断先跑 |
| 5 | 延迟循环 | 出队 → 依赖检查（重排或抛 `CycleDetected`）→ 校验 → Action → 合并 `ActionResult`（新 `params` 也入队）→ 标记已处理 |
| 6 | 未知参数 | 始终没获得定义的命令行参数 → `ActionError: Unknown parameter: --x` |
| 7 | 复检 | 只重新校验被 Action 改过的值 |
| 8 | 约束 | 执行跨参数规则（默认只看显式命令行参数） |
| 9 | 必填 | 值必须存在，且来源为 `cli` 或 `action` |
| — | 返回 | `{名字: 值}` 包装成 `CliResult` |

**取值优先级（高 → 低）**：已存在的 CLI 值或 Action 生成值不会被后续 Action
覆盖 → 新的 Action 值 → 静态/函数默认值。Action 声明的参数若已持有 CLI 值，
会保留该值、只补上定义。

**几个值得记住的坑**

1. `required=True` 配静态 `default` 依然失败：默认值不是必填值的合法来源（"must come from CLI or an Action"）。
2. Action 返回的普通字典被当作 `values`；只有 `ActionResult(params=...)` 才声明新参数。
3. `pattern` 是前缀匹配（`re.match`），精确匹配要加 `$`。
4. bool 开关：`default=True` 时 `--flag` 置 `False`，否则 `--flag` 置 `True`。
5. `CliApp.run()` 会把帮助/错误帮助打印到 stdout；嵌入其它程序时需自行捕获。
6. 约束在必填之前执行，因此缺失必填参数有时会以 `at_least_one` 违规的形式先暴露。

---

## 6. 生态集成

### darwin-config（可选适配器）

把参数声明放进由
[darwin-config](https://github.com/darwinalpha/darwin-config) 管理的
JSON / YAML / TOML 配置里。适配器位于 `darwin_cli.integrations.darwin_config`，
**核心库不会导入它**：只有显式 import 该模块才会加载 darwin-config，因此
`darwin-cli` 自身保持零依赖。

```python
from darwin_cli.integrations.darwin_config import from_config, from_file, get_loader

app = from_config("fetcher.cli", prog="fetch.py")                 # 点分配置键
app = from_file("config/settings.yaml", mount="fetcher", prog="fetch.py")
app = CliApp.from_config("cli", loader=get_loader("fetcher"), prog="fetch.py")
```

`from_config` 通过 `get_config` 读点分键，`from_file` 先从文件初始化
darwin-config，`get_loader` 返回可供 `CliApp.from_config` 使用的 loader 回调。
三者都能配合 `mount` 选取子树。

### 其它使用方

`darwin-fetch` 用本库构建数据抓取 CLI。从 `darwin_common.cli` 迁移时 API 名称
不变，只是包名不同。新能力（`constraints`、`from_config`、`outcome`、实例注册表）
需要改为 `import darwin_cli` 才能使用。

### 什么时候不该用它

它**不是**通用 CLI 框架的竞争者。只有几个固定选项的小脚本用 `argparse` 或
`click` 更简单；要子命令、补全、彩色帮助请用 `click` / `typer`。darwin-cli 面向的是
"参数集随上下文变化"的工具：数据源可切换、参数动态展开、参数之间有推断与链式依赖。
逐场景的对比见 [`docs/by-example.cn.md`](docs/by-example.cn.md)（[English](docs/by-example.md)）。

---

## 7. 测试

```bash
pip install -e '.[test]'
pytest tests -q
# 或：uv run --extra test python -m pytest tests -q
```

测试分为 `tests/unit/`（按模块划分：base、actions、loader、parser、validator、
executor、help、app、constraints、registry、来源跟踪、环检测、配置对接）与
`tests/integration/`（端到端抓取流程、复杂链式，以及 `test_examples.py`——它会
执行 `examples/` 下的每一个配置）。所有错误文案断言均为英文。

> `examples/` 里的样本由集成测试覆盖，因此它们始终是"可执行的文档"。

## 8. 许可

MIT
