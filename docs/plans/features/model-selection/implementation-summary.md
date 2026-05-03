# Model Selection Implementation Summary

## Implemented Behavior

- Added config-driven model routes through `LLM_OBSERVE_MODELS_JSON`,
  `LLM_OBSERVE_MODELS_FILE`, and CLI `--models-file`.
- Added exact-match routing by the request payload's top-level `model`.
- Configured routes can select a different upstream `/v1` base URL, rewrite the
  forwarded JSON `model`, and inject an upstream `Authorization` header.
- Unknown models, missing models, non-JSON bodies, and generic requests without a model
  continue to use the global upstream fallback.
- Captured request headers and bodies remain the original client request; injected API
  keys are not stored or rendered.
- Added `request_records.upstream_model` and `request_records.model_route`, plus SQLite
  upgrade handling for existing databases.
- Added read-only model route visibility in `/admin/settings`, route-aware upstream
  testing, and route/upstream-model metadata in request browser/detail views.

## Main Code Changes

- `config.py`: `ModelRoute`, route parsing, file/env precedence, `/v1` URL validation.
- `routing.py`: pure route selection, forwarded body rewrite, header/key policy, masked
  display helpers.
- `proxy.py`: route-aware upstream URL resolution, forwarded body/header selection, and
  route metadata capture for streaming and non-streaming requests.
- `admin.py` and templates/static assets: model route settings panel, route-aware test
  upstream action, and request route metadata.
- `database.py`: nullable route metadata columns and SQLite schema upgrade helper.

## Tests Added

- Config/routing unit tests for JSON/file parsing, duplicate rejection, invalid upstream
  URLs, key validation, route selection, body rewriting, env key resolution, and auth
  handling.
- Proxy integration tests for route selection, model rewriting, API key override,
  no-key preservation, missing-env auth drop, global fallback, streaming route capture,
  original request body storage, and persisted route metadata.
- Admin tests for route panel rendering, secret masking, route-aware upstream tests,
  fallback upstream tests, and request route metadata display.
- SQLite upgrade coverage for `upstream_model`, `model_route`, and their indexes.

## Verification

Commands run from the repository root with `.venv`:

```bash
.venv/bin/ruff check src tests
.venv/bin/python -m compileall -q src tests
.venv/bin/pytest -q
```

Result: full suite passed with `53 passed` and two dependency deprecation warnings from
`websockets`/`uvicorn`.
