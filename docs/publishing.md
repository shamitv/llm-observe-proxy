# Publishing

This document records the release checks for publishing `llm-observe-proxy` to PyPI.

## Name Availability

Checked on 2026-05-01 against PyPI JSON endpoints:

| Name | Result |
| --- | --- |
| `llm-observe-proxy` | 404 / appears available |
| `llm_observe_proxy` | 404 / appears available |
| `llm-observe` | 404 / appears available |
| `llm-cache-proxy` | 404 / appears available |
| `llm-observe-ui` | 404 / appears available |
| `llm-proxy-observe` | 404 / appears available |

Nearby existing packages found during search include `info-llm-observe`,
`openai-http-proxy`, `oai-proxy`, `llm-proxypy`, and `llm-monitor`.

PyPI normalizes `-`, `_`, and `.` in project names, so the exact package name and
underscore form were both checked.

## Build And Check

Dependency floors were refreshed on 2026-05-01 with `pip index versions`.

```powershell
.\.venv\Scripts\python.exe scripts\publish_pypi.py --dry-run
```

## Upload

The publish helper loads `.env` before reading credentials. Keep `.env` out of git and
store the PyPI API token there:

```dotenv
PYPI_TOKEN=pypi-...
TEST_PYPI_TOKEN=pypi-...
```

Use TestPyPI first:

```powershell
.\.venv\Scripts\python.exe scripts\publish_pypi.py --repository testpypi
```

Then install from TestPyPI in a clean environment and smoke-test:

```powershell
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ llm-observe-proxy
llm-observe-proxy --help
```

Publish to PyPI:

```powershell
.\.venv\Scripts\python.exe scripts\publish_pypi.py
```

Useful options:

```powershell
.\.venv\Scripts\python.exe scripts\publish_pypi.py --skip-existing
.\.venv\Scripts\python.exe scripts\publish_pypi.py --token-env PYPI_TOKEN
.\.venv\Scripts\python.exe scripts\publish_pypi.py --repository-url https://upload.pypi.org/legacy/
```

## Pre-Publish Checklist

- `git status --short --branch` is clean on `main`.
- `.\.venv\Scripts\ruff.exe check src tests` passes.
- `.\.venv\Scripts\python.exe -m compileall -q src tests` passes.
- `.\.venv\Scripts\pytest.exe -q` passes.
- `.\.venv\Scripts\python.exe scripts\publish_pypi.py --dry-run` succeeds.
- PyPI package name still returns 404 immediately before upload.
- Version in `pyproject.toml` has not already been uploaded.
