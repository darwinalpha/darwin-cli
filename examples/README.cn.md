# examples/ 示例索引

[English](README.md) · 简体中文

每个场景都是 `configs/` 里的一个 **JSON 配置文件** 加一段可运行演示。不需要任何第三方包：`from_config()` 用标准库读 JSON，`demo.py` 会自己把 `src/` 加入 `sys.path`。

```bash
# 在仓库根目录（无需安装包即可运行）
python examples/demo.py
PYTHONPATH=src python examples/demo.py

# 安装包之后
python examples/demo.py
```

| # | 配置文件 | 演示能力 | 试跑命令 |
| --- | --- | --- | --- |
| 01 | `configs/01-basic.json` | 静态参数、`run()` 返回 `CliResult`、必填与默认值 | `--name World --count 3` |
| 02 | `configs/02-inference.json` | Action 根据 `--type` 推断 `--source`；用户显式传值优先 | `--type stock_daily` |
| 03 | `configs/03-dynamic.json` | `ActionResult(params=...)` 按数据源长出参数集；`depends_on` | `--type stock_daily --symbol 600000.SH` |
| 04 | `configs/04-constraints.json` | 五条内置关系规则，全部只写在配置里 | `--source tushare` |
| 05 | `configs/05-validation.json` | `int` 转换、范围、枚举、长度、正则、bool 开关 | `--count 5 --status active --overwrite` |
| 06 | `configs/06-depends.json` | `depends_on` 重排处理顺序；`ActionResult(values=...)` 一个输入展开成多个值 | `--year 2026` |
| 07 | `configs/07-help.json` | 上下文帮助：裸 `--help` 与推断后的场景帮助 | `--type stock_daily --help` |
| 08 | `configs/08-mount.json` | `mount` 选取配置子树；默认值不会触发约束 | `--type stock_daily --output a.csv --stdout` |

`actions.py` 存放 02/03/06/07 用到的四个 Action 函数。构造 app 前调用
`actions.register_all()`（或 `register_all(registry)`）；它是幂等的，因此在
`clear_actions()` 之后重复调用也安全。

## 配置文件结构

```json
{
  "prog": "fetch.py",
  "help": "显示在帮助文本上方的描述",
  "cli_args": {
    "type": {
      "type": "str",
      "required": true,
      "help": "数据类型",
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

- `cli_args`（或 `params`）放参数声明，每个键对应一个 `--键名`。
- `type` 可以是 `"str" | "int" | "float" | "bool"`，也可以是规则对象，例如
  `{"pattern": "..."}`（此时隐含 `str`）。
- `action` 是注册到 Action 注册表里的**名字**；用 Python dict 构造时也可以直接传函数。
  JSON 无法表达函数，所以配置文件里只能写名字。
- `validation` 或字典形式的 `type` 会转成 `ValidationRule`。
- `constraints` 可选，五条规则见主 README。
- `prog` / `help` 可选，用于生成帮助文本。

## 参数声明的三种等价写法

```python
from darwin_cli import CliApp, Param

# 1) JSON 文件（零依赖）
app = CliApp.from_config("examples/configs/01-basic.json")

# 2) Python 字典 —— 可以传函数
app = CliApp.from_config({
    "cli_args": {
        "type": {"required": True, "action": guess_source},
        "count": {"type": "int", "default": 1},
    }
})

# 3) Param 对象 —— 完全掌控
app = CliApp(params=[
    Param(name="type", required=True, action=guess_source),
    Param(name="count", type="int", default=1),
])
```

`CliApp.from_config(path, loader=my_loader)` 接受任意"把路径/键转成 dict"的可调用对象。
要用 darwin-config 文件写 params，使用可选适配模块（核心库**不依赖** darwin-config）：

```python
from darwin_cli.integrations.darwin_config import from_config, from_file

app = from_config("fetcher.cli", prog="fetch.py")   # 点分配置键
app = from_file("config/settings.yaml", mount="fetcher", prog="fetch.py")
```

## 注意点

1. `--key=value`、`--key value`、裸 `--flag` 都支持；来源跟踪是精确的，约束不会把默认值误判成用户传值。
2. 正则校验用 `re.match`（前缀匹配）。需要精确匹配时要像 `05-validation.json` 那样加 `$` 锚点。
3. `required=True` 配静态 `default` 依然会失败：必填值必须来自命令行或 Action，不能来自默认值。
4. 约束默认只检查用户显式传入的参数。规则上加 `"include_generated": true` 才会把 Action 生成的值也算进去。
5. `tests/integration/test_examples.py` 会跑遍本目录的每个配置，所以这些样本是"可执行的文档"。
