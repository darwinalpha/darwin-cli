# Release guide

[English](releasing.md) · [简体中文](releasing.cn.md)

> The operational runbook for publishing `darwin-cli` to PyPI. Follow the
> standard flow in section 2; the rest explains why each step exists and what
> to do when something breaks.
>
> In one sentence: **pushing a `v*` tag is the release.** GitHub Actions builds
> and uploads the package via PyPI Trusted Publishing (OIDC); no local token,
> no local build, no manual upload.

---

## 1. One-time setup

Everything in this section is already configured for `darwin-cli`. You only
need it again when setting up a new project, a new PyPI account, or after
renaming the repo / workflow / environment.

### 1.1 What must exist

| Item | Value for this project |
| --- | --- |
| GitHub repo | `darwinalpha/darwin-cli` (SSH remote `git@github.com:darwinalpha/darwin-cli.git`) |
| PyPI project | `darwin-cli`, owned by the account used to create it |
| Local tools | `git`, `uv` (0.13.10+), Python >= 3.10 |
| Local test env | `uv run --extra test ...` is self-contained; no global pytest required |

### 1.2 The workflow

`.github/workflows/publish.yml` is deliberately minimal and kept byte-identical
to the `darwin-config` project. Do not "improve" it casually:

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

Four things are load-bearing:

- `tags: ['v*']` — only a tag push triggers a release. Ordinary commits to
  `main` do not.
- `environment: pypi` — the OIDC token carries this claim; the PyPI publisher
  registration must use the same name.
- `id-token: write` — without it the job cannot mint an OIDC token.
- `uv publish --trusted-publishing always` — forces the OIDC path. It fails
  rather than silently falling back to a token.

GitHub creates the `pypi` environment automatically on first reference; you do
not need to create it by hand. **Do not add required reviewers** to that
environment, or the job will sit waiting for approval.

### 1.3 Register the Trusted Publisher on PyPI

This requires a browser login to pypi.org (2FA may be needed); it cannot be
done from the CLI. Because the project already exists, use the **existing
project** path — not "pending publisher", which is only for a project that has
never been published.

1. Log in at https://pypi.org with the account that owns `darwin-cli`.
2. Go to https://pypi.org/manage/projects/ → `darwin-cli` → **Manage**.
3. Left sidebar → **Publishing** → GitHub Actions → **Add a new publisher**.
4. Fill in exactly:

| PyPI form field | Value | Note |
| --- | --- | --- |
| PyPI Project Name | `darwin-cli` | Usually fixed on an existing project page |
| Owner | `darwinalpha` | Matches the `repository_owner` claim |
| Repository name | `darwin-cli` | Repo name only, no owner prefix |
| Workflow name | `publish.yml` | **Filename only**, not `.github/workflows/publish.yml` |
| Environment name | `pypi` | **Required** because the workflow declares it |

5. Click **Add**; confirm one publisher row appears.

Every field must match the OIDC claim character-for-character. Renaming the
repo, the workflow file, or the environment immediately breaks publishing with
an `invalid-publisher` error.

> `~/.pypirc` holds a `pypi-*` API token. It is a **fallback only** — keep it,
> but the standard flow never reads it. `.gitignore` already excludes `.pypirc`.

---

## 2. Standard release flow (every time)

### Step 0 — Check the starting point

```bash
git status -sb                     # must be clean and in sync with origin/main
git log --oneline -1
curl -s "https://pypi.org/pypi/darwin-cli/json?ts=$RANDOM" \
  | python -c "import sys,json; print('latest:', json.load(sys.stdin)['info']['version'])"
```

Pick a version **strictly greater** than `latest`. PyPI versions are immutable:
a version that has been uploaded can never be re-uploaded or reused, even if
the release failed later.

### Step 1 — Sync the version in two places

```toml
# pyproject.toml
version = "0.2.2"
```

```python
# src/darwin_cli/__init__.py
__version__ = "0.2.2"
```

These are the only two version literals in the library; README, tests and
`examples/` do not hard-code a version. If they disagree, the installed package
reports a version different from PyPI — and the upload is irreversible.

### Step 2 — Run the full test suite

```bash
cd C:/Users/admin/darwin_project/darwin-cli
uv run --extra test python -m pytest tests -q
# equivalently: pip install -e '.[test]' && pytest tests -q
```

Expect `300 passed, 1 skipped` (the count grows as features are added). Do not
release on a red suite.

> `uv run --extra test` resolves pytest on first use and therefore needs
> network access. If you are offline, any environment that already has pytest
> works too (`python -m pytest tests -q`) — the library itself has no
> third-party runtime dependencies.

### Step 3 — Commit and push to main

```bash
git add pyproject.toml src/darwin_cli/__init__.py
git commit -m "Bump version to 0.2.2"
git push origin main
```

Only the version bump belongs in this commit. If there are other pending
changes, commit them separately first — a release commit should be trivially
identifiable.

### Step 4 — Create and push the tag (the trigger)

```bash
git tag -a v0.2.2 -m "Release v0.2.2"
git push origin v0.2.2
```

Keep these as **two separate commands**. If a sandboxed command is re-run, a
combined `git tag -a ... && git push ...` will fail on the second execution with
"tag already exists" and the tag never gets pushed. Use an annotated tag (`-a`)
so the release has a message and a date.

> Do **not** run `uv build` or `uv publish` locally in the standard flow. The
> CI runner checks out the tag and builds from a clean tree. A local `dist/`
> is irrelevant to the workflow, but it becomes dangerous in the fallback flow
> (section 5).

### Step 5 — Watch the run

Open https://github.com/darwinalpha/darwin-cli/actions or query the API:

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

All five business steps should be `success`, especially
`Run uv publish --trusted-publishing always`. A typical run takes ~15 seconds.

Anonymous GitHub API calls are limited to 60/hour. If you get a 403, use the
Actions web page instead, or wait for the quota window to reset.

### Step 6 — Verify on PyPI

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

Use `--refresh`: uv caches the simple index, so a fresh upload can otherwise
look like "no version of darwin-cli==0.2.2".

---

## 3. Copy-paste checklist

```bash
VERSION=0.2.2

# 0. confirm a clean tree and that PyPI has no such version yet
git status -sb
curl -s "https://pypi.org/pypi/darwin-cli/json?ts=$RANDOM" \
  | python -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"

# 1. edit version in pyproject.toml AND src/darwin_cli/__init__.py

# 2. test
uv run --extra test python -m pytest tests -q

# 3. commit + push
git add pyproject.toml src/darwin_cli/__init__.py
git commit -m "Bump version to $VERSION"
git push origin main

# 4. tag + push  <-- this alone triggers the release
git tag -a "v$VERSION" -m "Release v$VERSION"
git push origin "v$VERSION"

# 5. verify
curl -s "https://pypi.org/pypi/darwin-cli/$VERSION/json?ts=$RANDOM" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['info']['version'], [u['filename'] for u in d['urls']])"
uv run --no-project --refresh --with "darwin-cli==$VERSION" \
  python -c "import darwin_cli; print(darwin_cli.__version__)"
```

Verification checklist:

- [ ] GitHub Actions run is green, step 5 `uv publish ...` is `success`
- [ ] `https://pypi.org/pypi/darwin-cli/<VERSION>/json` returns 200
- [ ] `latest` on the project JSON equals the new version
- [ ] Both a `.whl` and a `.tar.gz` are listed
- [ ] A clean install reports the correct `__version__`
- [ ] `git tag -l` and `git ls-remote --tags origin` both contain the new tag
- [ ] README.md and README.cn.md were updated together, if either changed

---

## 4. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `uv publish` exits with code 2, run fails in ~15 s | Trusted Publisher not registered, or a field mismatch (`invalid-publisher`) | Check the five fields in 1.3; workflow name must be the bare filename; environment must be `pypi` |
| Error mentions "file already exists" / the version is already on PyPI | Version was already uploaded (e.g. by a token fallback) | **Never Re-run that job.** Bump to the next version and tag again |
| Run is green but PyPI JSON still shows the old `latest` | PyPI CDN caching | Query the version-specific JSON endpoint and the simple index directly; `latest` catches up shortly |
| `uv run --with darwin-cli==X.Y.Z` says "no version" | uv's local simple-index cache | Add `--refresh` |
| GitHub API returns 403 | Anonymous quota (60/hour) exhausted | Use the Actions web page, or wait for the reset |
| Raw step logs return 404 | Logs require an authenticated GitHub session | Use the unauthenticated `actions/runs/<id>/jobs` API for step conclusions |
| `uv publish` uploads old versions too | `uv build` does not clear `dist/`; publish uploads everything in it | Delete stale artifacts before any local publish (section 5) |
| `git tag -a` reports "already exists" | A command was re-run after the tag was created | Verify `git rev-list -n1 <tag>` equals `HEAD`, then just push the tag |
| Package installs but `__version__` is stale | Only one of the two version literals was edited | Fix both; the next release needs a new version (old one is burned) |
| `curl` reports `schannel ... SSL/TLS connection failed` / `http_code=000` | Local TLS or network outage, not a release failure | Retry once connectivity returns; every HTTPS check in this guide depends on it |

Diagnosing a failed run in order: confirm `uv build` succeeded (so the failure
is publishing, not packaging), confirm the failed step is `uv publish`, then
check the publisher registration. In this repo, the two historical failures
were both at step 5 with `uv build` green — a classic publisher-not-configured
signature.

---

## 5. Fallback: publish locally with an API token

Use **only** when the workflow cannot be used (for example, before the
publisher was first registered). It bypasses Trusted Publishing, so decide up
front: either push a tag **or** publish locally with a token, not both for the
same version.

```bash
cd C:/Users/admin/darwin_project/darwin-cli

# 1. remove stale artifacts — otherwise they get uploaded too
rm -f dist/darwin_cli-*.whl dist/darwin_cli-*.tar.gz
uv build
ls -lh dist/          # must contain exactly two files, both at the target version

# 2. load the token from ~/.pypirc into an env var; never echo it
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

Notes:

- `--trusted-publishing never` prevents uv from trying OIDC locally.
- Always `--dry-run` first and confirm the file list contains **exactly two**
  files at the target version.
- The token is passed via `UV_PUBLISH_TOKEN` in a child process environment; it
  never appears in the command line or in output. `.pypirc` is gitignored.
- After a token-based upload, that version is consumed. Do not Re-run the CI
  job for it.

---

## 6. Version rules

- PyPI versions are **immutable and non-reusable**. A "failed" release that
  already uploaded files still occupies the version.
- Therefore the recovery for almost any failure is: **fix the cause → bump the
  version → tag again**. Re-running a failed job is only meaningful when the
  upload itself never happened.
- Keep `version` and `__version__` in lockstep, and bump both in one commit.
- Tags are `v` + the exact version (`v0.2.2`, not `0.2.2` or `release-0.2.2`).

---

## 7. Release history of this project

| Version | Commit | Workflow run | Outcome |
| --- | --- | --- | --- |
| 0.1.0 | `1336630` | `45621266223` (#1) | Failed at `uv publish` — publisher not registered; released via local token |
| 0.2.0 | `195b627` | `45623196668` (#2) | Failed the same way; released via local token. Also added author metadata |
| 0.2.1 | `c789168` | `45625338874` (#3) | **SUCCESS** — publisher registered; first fully automatic OIDC release |

The 0.2.1 upload timestamps on PyPI match the workflow's step-5 timestamp,
which is a useful way to prove a release came from CI rather than a local
token. From 0.2.1 onward, the standard flow in section 2 is the only path
needed.

---

## 8. Maintenance convention

This guide has two language versions, `releasing.md` (English) and
`releasing.cn.md` (Simplified Chinese), linked at the top of each. **Any change
must be applied to both**, matching the convention used by `README.md` /
`README.cn.md`, `docs/by-example.md` / `docs/by-example.cn.md` and the
`examples/` indexes. Source code, tests, examples and all error messages are
in English; Chinese appears only in the `.cn.md` documents and the language
switch links.
