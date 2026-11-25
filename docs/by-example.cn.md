# darwin-cli：用案例讲明白

[English](by-example.md) · 简体中文

> 这是入门文档。源码细节见 `src/darwin_cli/`，API 清单见 [README.cn.md](../README.cn.md)，可运行样本见 [examples/](../examples/README.cn.md)。
>
> 一句话：**这不是普通的命令行参数库，而是一个"参数会自己干活"的小工作流引擎。**

---

## 先看痛点

写抓行情数据的脚本，用普通 `argparse`：

```python
parser.add_argument("--type", required=True)   # stock_daily / index_daily
parser.add_argument("--source")                # tushare / yahoo
parser.add_argument("--symbol")                # tushare 要 600000.SH，yahoo 要 AAPL
parser.add_argument("--interval")              # 只有 yahoo 需要
```

麻烦：用户得自己记 `type → source` 映射；`--help` 列出所有参数却不知道当前该用哪些；`main()` 里堆满 if/else。

darwin-cli 的思路：**让参数不再是被动空位，而是携带逻辑、能生成别的参数的主动单元。**

---

## 案例 1：最小用法

```python
from darwin_cli import CliApp, Param

app = CliApp(
    params=[
        Param(name="name", type="str", required=True, help="姓名"),
        Param(name="count", type="int", default=1, help="次数"),
    ],
    prog="hello.py",
)

result = app.run(["--name", "World", "--count", "3"])
print(result.success, result.outcome, result.data)
# True ok {'name': 'World', 'count': 3}
```

`run()` 不退出进程，返回 `CliResult`。`outcome` 明确区分 `ok` / `help` / `error`。脚本入口可用 `run_or_exit()`。

---

## 案例 2：参数自己会算

```python
from darwin_cli import CliApp, Param, register_action

@register_action("guess_source")
def guess_source(value, ctx):
    if value is not None:            # 用户显式传了 --source，尊重用户
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

Action 收到 `(value, current_args)`，`current_args` 是全量上下文，所以能读 `type` 推 `source`。返回的 dict 意思是"把这几个值补进参数表"。

**何时用**：映射规则留在代码里，不让用户记。参数少时手写 if 更简单；规则多了之后，每个 Action 只负责一个决定，可单独测试。

---

## 案例 3：参数会"长出来"

不同数据源需要的参数不同：

```python
from darwin_cli import ActionResult, CliApp, Param, ValidationRule, register_action

@register_action("load_params")
def load_params(data_type, ctx):
    source = ctx["source"].value
    if source == "tushare":
        return ActionResult(params=[
            Param(name="symbol", type=ValidationRule(pattern=r"^\d{6}\.(SH|SZ|BJ)$"),
                  required=True, help="A股代码"),
            Param(name="fields", type="str", default="close", help="字段"),
        ])
    return ActionResult(params=[
        Param(name="symbol", type="str", required=True, help="美股代码"),
        Param(name="interval", type="str", default="1d",
              validation=ValidationRule(choices=["1d", "1wk", "1mo"]), help="间隔"),
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

`symbol` 没在静态参数里声明，用户照样可以传——引擎先当"未知参数"收下，等 Action 定义了它再正式校验。这是 argparse 做不到的（参数在解析前就固定了）。

---

## 案例 4：谁先谁后

`type` 的 Action 要读 `source`，但 `type` 写在前面。`depends_on` 解决：

```python
Param(name="type", type="str", required=True,
      action="load_params",
      depends_on=["source"],      # 先处理 source
      help="类型"),
Param(name="source", type="str", action="guess_source"),
```

引擎发现 `source` 没处理完，就把 `type` 放回队列后面。循环依赖会被**真的依赖图检测**抓到，报 `CycleDetected`，不再靠"重试 5 次"猜。

---

## 案例 5：一个输入拆成两个

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

`values` 填值，`params` 让新参数"正式入籍"（参与校验和帮助）。

---

## 案例 6：链式反应

被 Action 写过的参数会重新入队，于是自动连锁：

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

Action 最好写成幂等的（`if value is not None: return {}`），因为同一参数可能被重新入队多次。

---

## 案例 7：关系约束——不用写 Action 的常见逻辑

互斥、同现这类关系，不必再手写 validator 再贴到每个 Action 上：

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

五种内置规则：

| 规则 | 配置 | 含义 |
| --- | --- | --- |
| `mutually_exclusive` | `params: [a, b]` | 最多一个 |
| `together` | `params: [user, token]` | 全有或全无 |
| `requires` | `param: type, requires: source` | A 有则 B 必须有 |
| `exclusive_with` | `param: date, group: [start_date, end_date]` | A 与整组互斥 |
| `at_least_one` | `params: [source, file]` | 至少提供一个 |

**关键语义**：约束只检查用户显式传入的参数，不检查 Action 生成的值。所以 `date → start_date/end_date` 展开不会触发"`date` 与 `start_date` 互斥"的误报。需要包含生成值时加 `"include_generated": true`。

复杂条件逻辑（查配置、查数据库）依然用 Action，两者共存。

---

## 案例 8：配置文件驱动

参数定义和关系规则都写在配置文件里：

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
result = app.run()   # 读 sys.argv[1:]
```

对接 darwin-config（可选模块，核心库零依赖）：

```python
from darwin_cli.integrations.darwin_config import from_config
app = from_config("fetcher.cli", prog="fetch.py")
```

配置里写不了 Callable（JSON 无法表达函数），所以 `action` 用字符串名从注册表查；需要动态 default/help 时仍要在代码里写。

---

## 案例 9：帮助信息看情况说话

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

`--help` 被放到队列末尾：只有 help 时立即显示全局帮助；和其他参数一起时，先把推断和动态参数跑完，再显示场景帮助。

---

## 案例 10：多应用隔离

新库支持实例级 Action 注册表，避免全局命名冲突：

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

不传 `registry` 时走全局注册表，`@register_action("name")` 的旧写法完全兼容。

---

## 这次相对旧库改了什么

| 项 | 旧库 | 新库 |
| --- | --- | --- |
| 依赖 | 经 `darwin_common` 连带 dotenv/pandas/pyarrow | 核心零依赖 |
| Python | ≥3.11（实际 ≥3.12） | ≥3.10 |
| 来源判断 | 扫描 argv，`--key=value` 会误判 | 自定义 argparse Action，准确且 O(1) |
| 循环检测 | "重试 5 次"启发式 | 真依赖图 DFS，报出环路径 |
| 阶段 6 校验 | 全量重复校验 | 只复检被 Action 改过的值 |
| 关系约束 | 只能写 Action + `@validate_before` | 配置驱动，5 条内置规则 |
| 配置对接 | 调用方手工 `get_config → parse_params` | `CliApp.from_config` + 可选适配模块 |
| Action 注册表 | 全局单例 | 全局 + 实例级可选 |
| 结果状态 | 靠 `success` + `exit_code` 猜 | 新增明确的 `outcome` |
| 死代码 | 若干 | 已清理 |

---

## 它是不是最优方案？

分场景：

| 场景 | 更合适的选择 |
| --- | --- |
| 固定几个参数的小脚本 | `argparse` / `click` |
| 要子命令、补全、彩色帮助 | `click` / `typer` |
| 参数随数据源/类型动态变化 | **darwin-cli** |
| 参数间有推断、展开、链式依赖 | **darwin-cli** |
| 简单参数关系（互斥/同现） | **darwin-cli 的 constraints**（不用写 Action） |
| Darwin 工具链一环 | **darwin-cli**（与 darwin-config 配套） |

**结论**：它不是通用 CLI 框架，而是"配置驱动的数据获取工具"的微型工作流引擎。在目标场景里贴切；超出范围既不比 click 好用，也不比 argparse 简单。
