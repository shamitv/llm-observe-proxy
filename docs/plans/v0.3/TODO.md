# v0.3 Implementation TODO

This checklist tracks the implementation work for the v0.3 admin observability
features. Keep commits focused and run the listed checks before each feature commit.

## Commit Plan

- [ ] `docs: add v0.3 implementation todo`
- [ ] `feat: compact run detail header`
- [ ] `feat: paginate request tables`
- [ ] `feat: localize admin timestamps`
- [ ] `feat: show pending request elapsed time`
- [ ] `feat: account for cached input tokens`
- [ ] `feat: estimate pending input tokens`
- [ ] `docs: document v0.3 admin observability`
- [ ] `chore: bump version to 0.3.0`

## Feature Tasks

### 1. Compact Run Detail Header

- [ ] Collapse the run detail page heading, active run card, and KPI grid into one
  compact header.
- [ ] Keep status, run name, notes, started/ended timestamps, and the active run end
  action visible.
- [ ] Render all current run KPI values as compact stat chips.
- [ ] Keep the what-if cost panel directly below the compact header.
- [ ] Add admin UI tests for active and completed run header behavior.
- [ ] Run `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`.

### 2. Paginated Request Tables

- [ ] Add bounded page/per-page parsing with defaults `page=1`, `per_page=50`, max
  `per_page=200`.
- [ ] Paginate `/admin` after applying filters and show range/total controls.
- [ ] Paginate `/admin/runs/{id}` run traffic without changing full-run stats or
  what-if totals.
- [ ] Preserve filter and repeated `what_if` query parameters in pagination links.
- [ ] Add admin UI tests for browser pagination, run pagination, filters, and full-run
  what-if totals.
- [ ] Run `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`.

### 3. Local Timezone Timestamps

- [ ] Add timestamp helpers that render UTC ISO values and clear no-JS UTC fallback.
- [ ] Replace raw timestamp rendering with semantic `<time>` markup in request, run,
  and detail templates.
- [ ] Localize timestamps in `static/app.js` with `Intl.DateTimeFormat`.
- [ ] Add tests for generated timestamp markup and active-ended fallback.
- [ ] Run `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`.

### 4. Pending Request Elapsed Time

- [ ] Compute elapsed duration for pending requests at page render time.
- [ ] Show `so far` duration in request tables and request detail when
  `duration_ms` is missing.
- [ ] Live-update pending elapsed durations in `static/app.js`.
- [ ] Add tests proving pending rows/details show elapsed time and completed rows
  still use stored duration.
- [ ] Run `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`.

### 5. Cached Token Cost Accounting

- [ ] Extend token extraction with `cached_input_tokens`.
- [ ] Add nullable `billing_cached_input_tokens` and `cached_input_usd_per_million`
  columns plus SQLite upgrade support.
- [ ] Add optional cached-input pricing to settings UI and model price validation.
- [ ] Update cost snapshots and run what-if calculations to use cached-input rates
  when configured.
- [ ] Add extraction, DB upgrade, cost, proxy capture, settings UI, and run what-if
  tests.
- [ ] Run `.\.venv\Scripts\pytest.exe -q tests\test_rendering_and_cli.py tests\test_proxy_capture.py tests\test_admin_ui.py`.

### 6. Pending Input Token Estimates

- [ ] Add `tiktoken>=0.12.0` as a runtime dependency.
- [ ] Add a token estimation helper for OpenAI-compatible chat completions and
  responses request bodies.
- [ ] Store estimate fields separately from billing usage.
- [ ] Compute estimates when creating request records.
- [ ] Render shaded/muted estimated input tokens for pending requests only when
  actual usage is unavailable.
- [ ] Add helper, proxy capture, admin UI, and run-total exclusion tests.
- [ ] Run `.\.venv\Scripts\pytest.exe -q tests\test_rendering_and_cli.py tests\test_proxy_capture.py tests\test_admin_ui.py`.

### 7. Documentation And Release

- [ ] Update `README.md`, `README.pypi.md`, and `docs/tests/README.md`.
- [ ] Bump `pyproject.toml` version to `0.3.0`.
- [ ] Run release checks:
  - [ ] `.\.venv\Scripts\ruff.exe check src tests scripts`
  - [ ] `.\.venv\Scripts\python.exe -m compileall -q src tests scripts`
  - [ ] `.\.venv\Scripts\pytest.exe -q`
  - [ ] `.\.venv\Scripts\python.exe scripts\publish_pypi.py --dry-run`

## Acceptance Checklist

- [ ] Record-only proxy behavior is unchanged.
- [ ] Request tables are paginated and bounded.
- [ ] Run detail first viewport is materially denser.
- [ ] Timestamps localize in the browser with UTC fallback.
- [ ] Pending rows show elapsed duration and estimated input tokens.
- [ ] Cached input token counts affect cost only when a cached rate is configured.
- [ ] Estimated pending tokens never affect billing, run stats, or what-if costs.
- [ ] Full test suite and release dry run pass.
