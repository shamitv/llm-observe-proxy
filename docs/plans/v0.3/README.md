# v0.3 Feature Plan

This plan tracks the user-facing work intended for the `0.3.0` release branch.

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

## Feature 2: Paginated Request Tables

### Problem

The admin request tables should not load every matching request on initial page
load. This is especially important for run detail pages, where a long-running task
can contain hundreds or thousands of captured requests.

Current behavior:

- `GET /admin` applies a default `limit=100`, but has no page navigation and no
  total/page context for the filtered result set.
- `GET /admin/runs/{id}` loads every request in that run, then renders the same
  `_requests_table.html` partial.
- The run detail route also passes the full run request list into the what-if cost
  calculation, so table pagination should be paired with aggregate cost queries
  instead of simply hiding extra rows in the template.

### Desired UX

- Request tables should render one page of rows at a time.
- The default first page should load quickly for large capture databases.
- Pagination controls should be server-rendered and bookmarkable with query
  parameters.
- Filtering should preserve pagination context where it makes sense, and applying
  a new filter should return to page 1.
- The user should see enough context to know what slice they are viewing, such as
  `Showing 1-50 of 1,249`.
- The UI should include previous/next controls and page number context.
- The same request table partial should support pagination on:
  - `GET /admin`
  - `GET /admin/runs/{id}`

### Non-goals

- Do not add infinite scroll for the first version.
- Do not require JavaScript for pagination.
- Do not change request capture behavior or retention settings.
- Do not remove run-level stats, what-if cost totals, or request filters.

### Implementation Plan

1. Add a small pagination helper in `admin.py`.
   - Parse `page` and `per_page` query parameters.
   - Clamp `per_page` to a safe maximum, such as 200.
   - Return offset, limit, total rows, total pages, previous/next page numbers, and
     a query string builder that preserves existing filters.
   - Use a default page size, such as 50.

2. Update `GET /admin`.
   - Replace the current `limit`-only behavior with `page`/`per_page`.
   - Apply all existing filters to a base `select(RequestRecord)` query.
   - Run a filtered `count(*)` query for pagination metadata.
   - Load only the current page of records with `order_by(created_at desc)`,
     `offset`, and `limit`.
   - Keep model, endpoint, run options, and summary counters working as they do
     now.

3. Update `GET /admin/runs/{id}`.
   - Load only the current page of requests for the `Run traffic` table.
   - Keep `get_task_run_stats` or equivalent aggregate SQL for header metrics.
   - Replace the what-if cost dependency on full ORM records with an aggregate
     token-usage query or a lightweight helper that selects only the fields needed
     for cost totals.
   - Avoid loading request/response body columns for rows that are not visible.

4. Update `_requests_table.html`.
   - Render pagination controls when a `pagination` context object is present.
   - Show range text, total count, page size, and previous/next links.
   - Preserve filters and repeated query parameters, including `what_if` on run
     detail pages.
   - Keep the empty state clear when a filter returns no rows.

5. Update templates that include `_requests_table.html`.
   - Pass pagination context from `index.html` and `run_detail.html`.
   - Keep the filter form on `/admin` aligned with the new query parameters.
   - Do not expose an unbounded `all` option.

6. Update tests in `tests/test_admin_ui.py`.
   - Add coverage that `/admin` only renders the requested page of records.
   - Add coverage that `/admin?page=2` shows later records and preserves filters.
   - Add coverage that `/admin/runs/{id}` paginates run traffic.
   - Add coverage that run-level what-if totals still include the full run, not
     only the visible request page.

7. Run focused verification.
   - `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`
   - `.\.venv\Scripts\ruff.exe check src tests`
   - `.\.venv\Scripts\python.exe -m compileall -q src tests`

8. Run the full test suite before committing the implementation.
   - `.\.venv\Scripts\pytest.exe -q`

### Acceptance Criteria

- `/admin` loads only the current request page, with a bounded page size.
- `/admin/runs/{id}` loads only the current run traffic page, even for large runs.
- Pagination controls show the current range, total matching rows, and previous/next
  navigation.
- Existing filters keep working with pagination.
- Run summary stats and what-if cost totals are computed from the full filtered run
  data where appropriate, not just from visible rows.
- Existing admin UI tests pass, with added pagination coverage.

## Later v0.3 Features

Add the next requested features here as they are defined. Each feature should include
the problem, desired UX or behavior, non-goals, implementation plan, and acceptance
criteria before implementation begins.
