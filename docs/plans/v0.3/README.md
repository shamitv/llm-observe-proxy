# v0.3 Feature Plan

This plan tracks the user-facing work intended for the `0.3.0` release branch.
The first requested feature is a density pass on the active run detail page.

## Release Goals

- Improve the admin UI for run-oriented workflows without adding frontend
  dependencies.
- Keep the proxy record-only: all `/v1/*` traffic must still forward upstream and
  then be stored in SQLite.
- Keep changes server-rendered and covered by the existing FastAPI/Jinja tests.
- Update `README.md` and `README.pypi.md` for user-facing behavior that changes how
  people use the app.
- Bump the package version only after the planned v0.3 feature set is implemented.

## Feature 1: Dense Active Run Header

### Problem

The run detail page currently spends a large amount of vertical space above the
what-if cost panel:

- page heading with run status, title, started, and ended badges
- active-run control card with the same run status/name plus request and open-time
  summary
- a KPI card grid for requests, wall time, run open duration, request duration,
  token totals, cost, and throughput

For active runs this pushes the analysis content far down the page. The screenshot
for `/admin/runs/{id}` shows the requested direction: condense the stats into the
`Run in progress` header itself.

### Desired UX

- The first viewport should show one compact run header, not a heading plus a
  duplicate active-run card plus a large KPI grid.
- The header should retain the primary run identity:
  - status: `Run in progress` or `Completed run`
  - title: `Run: <name>`
  - optional notes
  - started timestamp
  - ended timestamp or `active`
  - `End run` action when the viewed run is active
- The header should include compact stat chips or a dense inline stat row for:
  - Requests
  - LLM wall time
  - Run open
  - Request duration
  - Input tokens
  - Output tokens
  - Total tokens
  - Estimated cost
  - Output tok/s
- The what-if cost panel should move materially higher on the page.
- The layout must remain readable on narrow screens by wrapping stat chips and
  keeping the `End run` button accessible.

### Non-goals

- Do not change how run metrics are computed.
- Do not change cost estimation, what-if pricing, request capture, or run
  association behavior.
- Do not add authentication or JavaScript-heavy controls.
- Do not introduce new frontend dependencies.

### Implementation Plan

1. Update `src/llm_observe_proxy/templates/run_detail.html`.
   - Merge the active-run control content into the top run heading.
   - Remove the duplicate active-run card from this page.
   - Replace the full KPI grid with compact stat markup inside the header.
   - Keep the same `stats` and `run` values already provided by `admin.py`.

2. Update `src/llm_observe_proxy/static/styles.css`.
   - Add focused styles for a dense run header and compact stat chips.
   - Reuse existing colors, borders, badge styling, and button classes where
     possible.
   - Preserve responsive wrapping and avoid fixed heights that could clip labels.

3. Update `tests/test_admin_ui.py`.
   - Assert the run detail page still shows active-run metadata and the `End run`
     action.
   - Assert the important stats are still present on the page.
   - Prefer structural assertions that the duplicate active-run card is gone if the
     existing test helpers make that practical.

4. Run focused verification.
   - `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`
   - `.\.venv\Scripts\ruff.exe check src tests`
   - `.\.venv\Scripts\python.exe -m compileall -q src tests`

5. Run the full test suite before committing the implementation.
   - `.\.venv\Scripts\pytest.exe -q`

### Acceptance Criteria

- Active run detail pages show only one top run summary area above the what-if cost
  section.
- The top summary area includes status, run name, started/ended badges, end action,
  and all current KPI values.
- Completed run detail pages also use the compact stat header without showing an end
  action.
- The what-if cost panel appears immediately after the compact header.
- Existing admin UI tests pass, with added coverage for the new header layout.

## Later v0.3 Features

Add the next requested features here as they are defined. Each feature should include
the problem, desired UX or behavior, non-goals, implementation plan, and acceptance
criteria before implementation begins.
