# 发布指南

[English](releasing.md) · 简体中文

> `darwin-cli` 发布到 PyPI 的操作手册。日常照第 2 节走即可；其余部分解释
> 每一步为什么存在，以及出问题时怎么办。
>
> 一句话：**推送 `v*` tag 就是发版。** GitHub Actions 通过 PyPI Trusted
> Publishing（OIDC）构建并上传，不需要本地 token、不需要本地构建、不需要手动上传。

---

## 1. 一次性配置

本节内容对 `darwin-cli` 已经配置完成。只有在新建项目、更换 PyPI 账号，或
重命名仓库 / 工作流文件 / environment 之后才需要重做。

### 1.1 必须具备的条件

| 项 | 本项目的值 |
| --- | --- |
| GitHub 仓库 | `darwinalpha/darwin-cli`（SSH 远程 `git@github.com:darwinalpha/darwin-cli.git`） |
| PyPI 项目 | `darwin-cli`，归属创建它的账号 |
| 本地工具 | `git`、`uv`（0.13.10+）、Python >= 3.10 |
| 本地测试环境 | `uv run --extra test ...` 自包含，无需全局安装 pytest |

### 1.2 工作流

`.github/workflows/publish.yml` 刻意保持极简，且与 `darwin-config` 项目逐字一致。
不要随意"优化"它：

```yaml
name: publish
on:
  push:
    tags:
      - 'v*'
jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - run: uv publish --trusted-publishing always
```

四处是关键，改了就会坏：

- `tags: ['v*']` —— 只有推送 tag 才触发发版，普通提交到 `main` 不会。
- `environment: pypi` —— OIDC token 会带上这个 claim，PyPI 侧注册的
  publisher 必须填同名。
- `id-token: write` —— 没有它，job 无法签发 OIDC token。
- `uv publish --trusted-publishing always` —— 强制走 OIDC；失败时直接报错，
  不会悄悄退回 token。

GitHub 会在首次引用时自动创建 `pypi` environment，不用手动建。**不要给该
environment 加 required reviewers**，否则工作流会一直等人审批。

### 1.3 在 PyPI 注册 Trusted Publisher

这一步必须在 pypi.org 网页登录操作（可能需要 2FA），命令行代劳不了。因为项目
已经存在，走的是**现有项目**路径，不是 "pending publisher"——后者只用于从未
发布过、PyPI 上还不存在的项目。

1. 用拥有 `darwin-cli` 的账号登录 https://pypi.org。
2. 打开 https://pypi.org/manage/projects/ → `darwin-cli` → **Manage**。
3. 左侧 **Publishing** → GitHub Actions 区块 → **Add a new publisher**。
4. 逐字填写：

| PyPI 表单字段 | 值 | 说明 |
| --- | --- | --- |
| PyPI Project Name | `darwin-cli` | 现有项目页通常已固定 |
| Owner | `darwinalpha` | 与 `repository_owner` claim 一致 |
| Repository name | `darwin-cli` | 仅仓库名，不带 owner 前缀 |
| Workflow name | `publish.yml` | **只要文件名**，不是 `.github/workflows/publish.yml` |
| Environment name | `pypi` | **必填**，因为工作流声明了它 |

5. 点 **Add**，页面上出现一条 publisher 记录即完成。

每个字段都必须与 OIDC claim 逐字一致。以后改仓库名、工作流文件名或
environment 名，都会立刻以 `invalid-publisher` 发布失败。

> `~/.pypirc` 里有一个 `pypi-*` API token，**仅作后备**——保留即可，标准流程
> 完全不读它。`.gitignore` 已排除 `.pypirc`。

---

## 2. 标准发版流程（每次都这么做）

### 第 0 步 — 确认起点

```bash
git status -sb                     # 必须干净，且与 origin/main 同步
git log --oneline -1
curl -s "https://pypi.org/pypi/darwin-cli/json?ts=$RANDOM" \
  | python -c "import sys,json; print('latest:', json.load(sys.stdin)['info']['version'])"
```

选一个**严格大于** `latest` 的版本号。PyPI 版本不可变：一旦上传，即使后续
环节失败，该版本也永远不能重传或复用。

### 第 1 步 — 同步两处版本号

```toml
# pyproject.toml
version = "0.2.2"
```

```python
# src/darwin_cli/__init__.py
__version__ = "0.2.2"
```

全库只有这两处版本字面量；README、测试、`examples/` 都没有硬编码版本号。
两者不一致时，装到用户机器上的包会报告与 PyPI 不同的版本，而上传不可逆。

### 第 2 步 — 跑全量测试

```bash
cd C:/Users/admin/darwin_project/darwin-cli
uv run --extra test python -m pytest tests -q
# 等价写法：pip install -e '.[test]' && pytest tests -q
```

预期 `300 passed, 1 skipped`（随功能增加会变多）。测试红了不要发版。

> `uv run --extra test` 首次使用需要联网解析 pytest。若处于离线环境，任何已装
> pytest 的环境都可以（`python -m pytest tests -q`）——本库本身没有第三方运行时
> 依赖。

### 第 3 步 — 提交并推送 main

```bash
git add pyproject.toml src/darwin_cli/__init__.py
git commit -m "Bump version to 0.2.2"
git push origin main
```

这个提交里只放版本改动。若还有其他待提交改动，先分开提交——发版提交应当
一眼就能认出来。

### 第 4 步 — 创建并推送 tag（唯一的触发点）

```bash
git tag -a v0.2.2 -m "Release v0.2.2"
git push origin v0.2.2
```

**务必拆成两条命令**。在沙箱环境里命令可能被重跑，若写成
`git tag -a ... && git push ...`，第二次执行会因 "tag already exists" 中断，
tag 反而没被推出去。用 `-a` 建附注标签，让发布带有说明和日期。

> 标准流程下**不要**在本地执行 `uv build` 或 `uv publish`。CI runner 会签出
> tag 从干净工作树构建。本地 `dist/` 对工作流无影响，但在第 5 节的兜底流程里
> 会变成隐患。

### 第 5 步 — 监控 run

打开 https://github.com/darwinalpha/darwin-cli/actions ，或查 API：

```bash
curl -s -H "User-Agent: darwin-cli-release-check" \
  "https://api.github.com/repos/darwinalpha/darwin-cli/actions/runs/45625338874/jobs" \
  | python -c "
import sys,json
d=json.load(sys.stdin)
for j in d.get('jobs',[]):
    print('JOB', j['name'], j['conclusion'])
    for s in j.get('steps',[]):
        print('  ', s['number'], s['name'], '->', s['conclusion'])
"
```

五个业务步骤应全部 `success`，尤其是
`Run uv publish --trusted-publishing always`。一次 run 通常约 15 秒。

未认证的 GitHub API 配额是每小时 60 次；遇到 403 就改用 Actions 网页，或等
配额窗口重置。

### 第 6 步 — 在 PyPI 上验证

```bash
curl -s "https://pypi.org/pypi/darwin-cli/0.2.2/json?ts=$RANDOM" \
  | python -c "
import sys,json
d=json.load(sys.stdin); i=d['info']
print(i['name'], i['version'], i['requires_python'], i.get('author'))
print([u['filename'] for u in d['urls']])
"
curl -s -o /dev/null -w "project_page=%{http_code}\n" \
  "https://pypi.org/project/darwin-cli/0.2.2/?ts=$RANDOM"
uv run --no-project --refresh --with darwin-cli==0.2.2 \
  python -c "import darwin_cli; print(darwin_cli.__version__)"
```

一定要加 `--refresh`：uv 会缓存 simple index，刚上传的包否则会报
"no version of darwin-cli==0.2.2"。

---

## 3. 可复制的速查清单

```bash
VERSION=0.2.2

# 0. 确认工作区干净，且 PyPI 上还没有这个版本
git status -sb
curl -s "https://pypi.org/pypi/darwin-cli/json?ts=$RANDOM" \
  | python -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"

# 1. 编辑 pyproject.toml 和 src/darwin_cli/__init__.py 两处版本号

# 2. 测试
uv run --extra test python -m pytest tests -q

# 3. 提交 + 推送
git add pyproject.toml src/darwin_cli/__init__.py
git commit -m "Bump version to $VERSION"
git push origin main

# 4. 打 tag + 推送  <-- 只有这一步触发发版
git tag -a "v$VERSION" -m "Release v$VERSION"
git push origin "v$VERSION"

# 5. 验证
curl -s "https://pypi.org/pypi/darwin-cli/$VERSION/json?ts=$RANDOM" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['info']['version'], [u['filename'] for u in d['urls']])"
uv run --no-project --refresh --with "darwin-cli==$VERSION" \
  python -c "import darwin_cli; print(darwin_cli.__version__)"
```

验证清单：

- [ ] GitHub Actions run 变绿，第 5 步 `uv publish ...` 为 `success`
- [ ] `https://pypi.org/pypi/darwin-cli/<VERSION>/json` 返回 200
- [ ] 项目 JSON 的 `latest` 已等于新版本
- [ ] 同时存在 `.whl` 和 `.tar.gz`
- [ ] 干净环境安装后 `__version__` 正确
- [ ] `git tag -l` 与 `git ls-remote --tags origin` 都含新 tag
- [ ] 若改动了 README，两版 README 已同步更新

---

## 4. 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `uv publish` 退出码 2，run 约 15 秒失败 | publisher 未注册，或字段不匹配（`invalid-publisher`） | 核对 1.3 的五个字段；工作流名必须是纯文件名；environment 必须是 `pypi` |
| 报 "file already exists" / 版本已在 PyPI 上 | 该版本已被上传（例如被 token 兜底发布过） | **不要 Re-run 该 job**，递增版本后重新打 tag |
| run 变绿但 PyPI JSON 仍显示旧 `latest` | PyPI CDN 缓存 | 直接查版本专属 JSON 端点与 simple index；`latest` 稍后会自动更新 |
| `uv run --with darwin-cli==X.Y.Z` 报 "no version" | uv 本地 simple index 缓存 | 加 `--refresh` |
| GitHub API 返回 403 | 未认证配额（60/小时）耗尽 | 改用 Actions 网页，或等配额重置 |
| 原始步骤日志返回 404 | 日志需要登录 GitHub | 用无需认证的 `actions/runs/<id>/jobs` API 看各步结论 |
| `uv publish` 把旧版本一起传了 | `uv build` 不清空 `dist/`，publish 会上传其中所有文件 | 任何本地发布前先删掉旧产物（第 5 节） |
| `git tag -a` 报 "already exists" | 命令被重跑，tag 其实已创建 | 核对 `git rev-list -n1 <tag>` 等于 `HEAD`，然后直接推 tag |
| 包装上了但 `__version__` 是旧值 | 只改了两处版本字面量中的一处 | 两处都修好；下次发版必须换新版本（旧的已作废） |
| `curl` 报 `schannel ... SSL/TLS connection failed` / `http_code=000` | 本机 TLS/网络临时故障，不是发版失败 | 网络恢复后重试；本指南所有 HTTPS 检查都依赖它 |

排查失败 run 的顺序：先确认 `uv build` 成功（说明是发布而非打包问题），再
确认失败步骤是 `uv publish`，然后检查 publisher 注册。本仓库历史上两次失败都
是 `uv build` 绿、第 5 步红 —— 这是"publisher 未配置"的典型特征。

---

## 5. 兜底：用 API token 本地发布

**仅当**工作流不可用时才用（例如 publisher 首次注册之前）。它绕过了 Trusted
Publishing，所以要事先决定：同一个版本，**要么推 tag、要么本地 token 发布**，
不能两边都做。

```bash
cd C:/Users/admin/darwin_project/darwin-cli

# 1. 删除旧产物，否则会被一起上传
rm -f dist/darwin_cli-*.whl dist/darwin_cli-*.tar.gz
uv build
ls -lh dist/          # 必须恰好两个文件，且都是目标版本

# 2. 从 ~/.pypirc 读 token 放进环境变量；绝不回显
python - <<'PY'
import os, re, subprocess, sys

token = None
for line in open(os.path.expanduser('~/.pypirc'), encoding='utf-8'):
    m = re.match(r'\s*password\s*[=:]\s*(\S+)', line, re.I)
    if m:
        token = m.group(1)
if not token or not token.startswith('pypi-'):
    sys.exit('ERROR: no usable PyPI token in ~/.pypirc')

env = os.environ.copy()
env['UV_PUBLISH_TOKEN'] = token
base = ['uv', 'publish', '--trusted-publishing', 'never', '--no-progress']

dry = subprocess.run(base + ['--dry-run'], env=env, capture_output=True, text=True)
print(dry.stdout[-800:] + dry.stderr[-800:])
if dry.returncode != 0:
    sys.exit('ABORT: dry-run failed, nothing uploaded')

pub = subprocess.run(base, env=env, capture_output=True, text=True)
print(pub.stdout[-1500:] + pub.stderr[-1500:])
sys.exit(pub.returncode)
PY
```

要点：

- `--trusted-publishing never` 阻止 uv 在本地尝试 OIDC。
- 务必先 `--dry-run`，确认文件列表**恰好两个**且都是目标版本。
- token 通过子进程环境变量 `UV_PUBLISH_TOKEN` 传递，不出现在命令行或输出里；
  `.pypirc` 已被 gitignore。
- 用 token 上传后该版本即被占用，不要再 Re-run 对应的 CI job。

---

## 6. 版本规则

- PyPI 版本**不可变、不可复用**。哪怕"失败"的发版已经上传了文件，该版本也
  已经被占用。
- 因此几乎所有失败的恢复动作都是：**修好根因 → 递增版本 → 重新打 tag**。
  只有确认上传压根没发生时，Re-run 失败 job 才有意义。
- `version` 与 `__version__` 保持同步，且在同一个提交里一起递增。
- tag 格式是 `v` + 精确版本号（`v0.2.2`，不是 `0.2.2` 或 `release-0.2.2`）。

---

## 7. 本项目的发版记录

| 版本 | 提交 | 工作流 run | 结果 |
| --- | --- | --- | --- |
| 0.1.0 | `1336630` | `45621266223`（#1） | `uv publish` 失败 —— publisher 未注册；改用本地 token 发布 |
| 0.2.0 | `195b627` | `45623196668`（#2） | 同样失败；改用本地 token 发布。同时补充了作者信息 |
| 0.2.1 | `c789168` | `45625338874`（#3） | **成功** —— publisher 已注册，首次全自动 OIDC 发版 |

0.2.1 在 PyPI 上的上传时间戳与工作流第 5 步时间戳吻合，这是判断"这次发布
来自 CI 而不是本地 token"的一个实用证据。从 0.2.1 起，只需按第 2 节的标准
流程走即可。

---

## 8. 维护约定

本指南有两个语言版本：`releasing.md`（英文）与 `releasing.cn.md`（简体中文），
顶部互相链接。**任何修改都必须同时应用到两版**，与 `README.md` /
`README.cn.md`、`docs/by-example.md` / `docs/by-example.cn.md` 以及 `examples/`
双版索引的约定一致。源码、测试、示例和所有错误信息均为英文；中文只出现在
`.cn.md` 文档与语言切换链接里。
