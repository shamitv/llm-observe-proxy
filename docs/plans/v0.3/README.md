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

## Feature 3: Local Timezone Timestamps

### Problem

The admin UI currently renders timestamp objects directly from the database. In the
request table this appears as raw ISO-like values such as:

```text
2026-05-10
05:18:52.830265
```

That is hard to scan and does not make it clear whether the value is UTC, server
local time, or the user's local timezone. Users looking at captured traffic should
see times in their own browser timezone.

Current timestamp surfaces include:

- request table `Time` column in `_requests_table.html`
- request detail metadata in `detail.html`
- run detail started/ended badges in `run_detail.html`
- runs list started time in `runs.html`
- any future pagination range or activity timestamps

### Desired UX

- Timestamps should display in the user's browser timezone.
- Timestamp text should be compact and scannable in tables.
- The full absolute timestamp should remain available through the native tooltip or
  accessible label.
- Relative/duration values such as `2.42 s`, `10 days 3h open`, and wall-clock
  durations should not change.
- If JavaScript is disabled, the UI should still show a clear UTC fallback instead
  of an ambiguous raw datetime.

Suggested display shape:

```text
May 10, 2026
10:48:52 AM
```

or a denser table variant:

```text
May 10
10:48:52 AM
```

### Non-goals

- Do not change how timestamps are stored in SQLite.
- Do not change duration calculations.
- Do not add a user account, settings table, or profile-level timezone preference
  for the first version.
- Do not add a frontend framework or heavy date library.

### Implementation Plan

1. Normalize timestamp output in `admin.py`.
   - Add a Jinja filter/helper that turns `datetime` values into UTC ISO strings
     for the `datetime` attribute.
   - Treat naive datetimes returned from SQLite as UTC, matching the app's existing
     write behavior.
   - Add a compact UTC fallback formatter for no-JS rendering.

2. Add a reusable timestamp partial or macro.
   - Render timestamps as semantic `<time>` elements.
   - Include the UTC ISO value in `datetime`.
   - Include a class or data attribute such as `data-local-time`.
   - Support table-friendly and badge-friendly display variants.

3. Add lightweight local-time JavaScript.
   - On page load, find all `[data-local-time]` elements.
   - Use `Intl.DateTimeFormat` with the browser's default timezone.
   - Replace fallback UTC text with local date/time text.
   - Set `title` to include the full localized timestamp and UTC fallback.
   - Handle invalid or missing timestamps without throwing.

4. Update templates.
   - Replace direct timestamp rendering in `_requests_table.html`, `detail.html`,
     `run_detail.html`, and `runs.html`.
   - Keep `active` fallback for open-ended runs.
   - Keep compact table cells from growing too wide.

5. Update CSS.
   - Add table timestamp styling so date and time can stack cleanly in the Time
     column.
   - Ensure localized text does not overlap adjacent columns on narrow screens.

6. Update tests.
   - Add coverage that timestamp cells render semantic `<time>` elements with UTC
     ISO `datetime` attributes.
   - Add coverage for active run `Ended active` fallback.
   - Add a small unit test for the UTC fallback formatter if it is implemented as a
     Python helper.

7. Run focused verification.
   - `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`
   - `.\.venv\Scripts\ruff.exe check src tests`
   - `.\.venv\Scripts\python.exe -m compileall -q src tests`

8. Run the full test suite before committing the implementation.
   - `.\.venv\Scripts\pytest.exe -q`

### Acceptance Criteria

- Request table timestamps display in the browser's local timezone after page load.
- The raw table timestamp format is replaced by a compact, readable local time.
- Run list and run detail timestamps use the same local-time rendering path.
- No-JS fallback text is explicitly UTC.
- Tests cover the generated timestamp markup and existing admin UI behavior still
  passes.

## Feature 4: Pending Request Elapsed Time

### Problem

Pending requests currently show `pending` in the Status column and `-` in the
Duration column. For long-running streaming requests, stuck upstream calls, or slow
local models, that hides the most important operational signal: how long the
request has been running so far.

Current behavior:

- `RequestRecord.response_status` is `NULL` while the request is pending.
- `RequestRecord.completed_at` is `NULL` while the request is pending.
- `RequestRecord.duration_ms` is `NULL` until the proxy records completion or an
  error.
- `_requests_table.html` renders `{{ record.duration_ms | duration_ms }}`, so
  pending rows display `-`.

### Desired UX

- Pending request rows should show elapsed time in the Duration column.
- The value should read as in-progress, for example:

```text
3m 12s so far
```

- Completed request rows should continue showing their final captured duration.
- TPS should remain `-` for pending rows unless output token usage and a meaningful
  elapsed denominator are both available in a future feature.
- The request detail page should also show elapsed time for pending requests.
- If the page remains open, elapsed pending durations should update without a full
  refresh when feasible.

### Non-goals

- Do not mutate `duration_ms` in SQLite until the request completes.
- Do not mark pending requests as failed just because they have been pending for a
  long time.
- Do not change timeout behavior or upstream forwarding behavior.
- Do not infer final token usage or cost for pending requests.

### Implementation Plan

1. Add pending elapsed fields in `admin.py` row/detail shaping.
   - Capture a single `now = datetime.now(UTC)` per page render.
   - For records with `duration_ms is None` and `completed_at is None`, compute
     `elapsed_ms = now - created_at`.
   - Add fields such as `duration_display_ms`, `is_pending`, and
     `duration_is_elapsed` to `_record_list_item` and `_record_detail`.
   - Treat naive datetimes from SQLite as UTC for the elapsed calculation.

2. Update request table rendering.
   - Render final durations exactly as today for completed rows.
   - Render pending elapsed durations with a compact qualifier such as `so far`.
   - Add a data attribute with the pending request start time so JavaScript can
     update the value while the page is open.

3. Update request detail rendering.
   - Show elapsed time in the Duration metadata pill for pending requests.
   - Keep status displayed as `pending`.

4. Add lightweight live elapsed JavaScript.
   - Reuse the local-time JavaScript file if Feature 3 has already introduced one,
     or add a small admin UI script if not.
   - Find elements with a pending elapsed data attribute.
   - Update the text every second or every few seconds using the same duration
     formatting rules as the server where practical.
   - Stop cleanly if the timestamp is invalid.

5. Update CSS.
   - Add a subtle style for elapsed pending duration text if needed.
   - Keep the Duration column width stable so values like `10m 4s so far` do not
     shift the table layout.

6. Update tests.
   - Add a pending `RequestRecord` directly in a test database and assert the
     request browser shows an elapsed duration instead of `-`.
   - Assert completed rows still show the stored `duration_ms`.
   - Assert request detail shows elapsed duration for a pending record.
   - Avoid tests that depend on exact wall-clock seconds; use broad text markers
     such as `so far` and deterministic old `created_at` values.

7. Run focused verification.
   - `.\.venv\Scripts\pytest.exe -q tests\test_admin_ui.py`
   - `.\.venv\Scripts\ruff.exe check src tests`
   - `.\.venv\Scripts\python.exe -m compileall -q src tests`

8. Run the full test suite before committing the implementation.
   - `.\.venv\Scripts\pytest.exe -q`

### Acceptance Criteria

- Pending rows in request tables show elapsed duration instead of `-`.
- Completed rows still show their final recorded duration.
- Request detail pages show elapsed duration for pending requests.
- Pending elapsed values are not persisted into `duration_ms`.
- Tests cover pending and completed duration rendering.

## Feature 5: Cached Token Cost Accounting

### Problem

Cost estimates currently treat all input tokens as the same price class. Some
upstreams expose cached input token counts in response usage metadata, and cached
tokens can be billed differently from ordinary input tokens. When those cached
tokens are visible in the captured response, cost calculation should use them
instead of charging the entire input total at the standard input rate.

Current behavior:

- `ExtractedTokenUsage` contains only input, output, and total token counts.
- `estimate_cost` calculates:

```text
input cost = input_tokens * input_usd_per_million / 1,000,000
output cost = output_tokens * output_usd_per_million / 1,000,000
```

- `ModelPrice` stores only standard input and output rates.
- Pricing snapshots do not explain whether cached tokens were present or ignored.

### Desired Behavior

- If the response usage includes cached input tokens, extract and preserve that
  count.
- If a model price has a configured cached-input rate, calculate input cost as:

```text
uncached_input_tokens = max(input_tokens - cached_input_tokens, 0)
input cost =
  uncached_input_tokens * input_usd_per_million / 1,000,000
  + cached_input_tokens * cached_input_usd_per_million / 1,000,000
```

- If cached tokens are present but no cached-input rate is configured, fall back to
  the standard input rate for all input tokens and make that clear in the pricing
  snapshot.
- If cached tokens cannot be determined from the response, keep the current cost
  calculation.
- Run-level what-if cost should use cached-token accounting when both run usage and
  the selected model price support it.

### Usage Shapes To Recognize

Initial extraction should support common OpenAI-compatible response shapes:

- Chat completions:
  - `usage.prompt_tokens_details.cached_tokens`
  - `usage.prompt_tokens_details.cache_read_tokens` if present
- Responses API:
  - `usage.input_tokens_details.cached_tokens`
  - `usage.input_tokens_details.cache_read_tokens` if present
- Streaming final usage events with the same nested shapes.

Future provider-specific cache-write fields, such as cache creation/write tokens,
should be captured separately only after their billing semantics are clear.

### Non-goals

- Do not invent cached-token counts when the upstream does not report them.
- Do not assume provider cache discounts without a configured cached-input rate.
- Do not broadly recalculate historical request cost snapshots automatically; v0.4's
  cached-token backfill is the narrow exception for stale cached-pricing metadata.
- Do not add image/audio/tool-specific pricing in this feature.

### Implementation Plan

1. Extend token usage extraction in `capture.py`.
   - Add `cached_input_tokens` to `ExtractedTokenUsage`.
   - Extract cached counts from known nested usage detail fields.
   - Clamp impossible values conservatively when cached tokens exceed total input
     tokens, and preserve raw response bodies for debugging as today.
   - Update streaming usage marker detection so final SSE usage events containing
     cache detail fields are found efficiently.

2. Extend persistence in `database.py`.
   - Add nullable `billing_cached_input_tokens` to `request_records`.
   - Add nullable `cached_input_usd_per_million` to `model_prices`.
   - Add SQLite upgrade statements for existing databases.
   - Update seed rows only when reliable cached-token prices are deliberately
     provided; otherwise leave cached rates null so the fallback is explicit.

3. Update settings pricing management.
   - Add an optional `Cached input / 1M` field to the model pricing form/table.
   - Validate it with the same decimal-rate rules when provided.
   - Keep existing model price rows valid when the cached rate is blank.

4. Update cost calculation in `costing.py`.
   - Include cached input tokens and cached input cost in `CostEstimate`.
   - Split standard input cost and cached input cost when a cached rate exists.
   - Keep total token counts unchanged; cached input tokens are a subset of input
     tokens, not additional tokens.
   - Add snapshot fields for:
     - cached input tokens
     - cached input rate
     - uncached input tokens
     - whether cached tokens used a special rate or fell back to standard input
       pricing

5. Update run what-if estimates.
   - Include cached input tokens in `RunCostEstimate`.
   - Sum cached input tokens across included requests.
   - Apply the selected model price's cached-input rate when present.
   - Add optional cached-token columns or compact detail text in the what-if table
     so users can see why totals changed.

6. Update admin UI request displays.
   - Show cached input token counts in request detail cost estimates.
   - Keep the request table compact; add cached-token detail only if it can fit
     cleanly without making the token column noisy.
   - Include cached-token information in pricing snapshots.

7. Update tests.
   - Add extraction tests for non-streaming Chat Completions and Responses API
     usage detail shapes.
   - Add streaming final-usage extraction coverage for cached tokens.
   - Add cost estimator tests for:
     - cached rate configured
     - cached tokens present but cached rate missing
     - cached tokens absent
   - Add persistence/UI tests for `billing_cached_input_tokens` and the settings
     pricing field.
   - Add run what-if cost coverage that proves cached tokens affect the full-run
     estimate.

8. Run focused verification.
   - `.\.venv\Scripts\pytest.exe -q tests\test_rendering_and_cli.py tests\test_proxy_capture.py tests\test_admin_ui.py`
   - `.\.venv\Scripts\ruff.exe check src tests`
   - `.\.venv\Scripts\python.exe -m compileall -q src tests`

9. Run the full test suite before committing the implementation.
   - `.\.venv\Scripts\pytest.exe -q`

### Acceptance Criteria

- Cached input tokens are extracted when present in recognized usage metadata.
- Request cost snapshots store cached input token counts.
- Cost estimates use a cached-input rate only when one is configured.
- Missing cached-input rates fall back to current standard input pricing and are
  disclosed in the pricing snapshot.
- Run what-if estimates account for cached input tokens when supported.
- Existing capture, rendering, and admin UI tests pass with new cached-token
  coverage.

## Feature 6: Estimated Input Tokens For Pending Requests

### Problem

Pending requests currently have no response usage metadata yet, so the request table
shows `-` for input, output, and total tokens. For slow or long-running requests,
users still need a rough sense of how large the prompt is while the request is in
flight.

The estimate must be visibly different from actual usage because tokenizer counts
can vary by model, provider, request shape, and hidden upstream formatting.

### Desired UX

- Pending request rows should show an estimated input token count when it can be
  derived from the captured request body.
- Estimated values should be visually shaded or muted so they are not confused with
  response-reported usage.
- The label should make the uncertainty clear, for example:

```text
~50.1k
Est. input
```

- Output and total tokens should remain `-` for pending rows unless there is actual
  upstream usage data.
- Completed rows should continue to prefer response-reported or billing snapshot
  token counts.
- Request detail pages should also show the estimated pending input token count
  with the same visual treatment.

### Non-goals

- Do not use estimated input tokens for final billing snapshots.
- Do not include estimated pending tokens in run cost totals or what-if cost totals.
- Do not mutate response-reported token usage.
- Do not promise exact provider billing parity from a local tokenizer estimate.

### Implementation Plan

1. Add a token estimation module.
   - Create a focused helper such as `token_estimation.py`.
   - Prefer `tiktoken` or a similar maintained tokenizer when available.
   - Verify Python 3.13 install support before deciding whether the tokenizer is a
     normal dependency, an optional extra, or a guarded best-effort import.
   - Keep tokenizer-specific logic behind a small adapter so a fallback can be
     swapped in later.

2. Estimate from OpenAI-compatible request bodies.
   - Decode captured JSON request bodies.
   - Support `/v1/chat/completions` by estimating message content, tool/function
     definitions, system/developer messages, and other prompt-bearing fields.
   - Support `/v1/responses` by estimating `input`, messages, and tool definitions.
   - For generic `/v1/*` requests, either estimate obvious string/list/dict prompt
     fields or return no estimate if the shape is unclear.
   - Pick the tokenizer from the requested model, routed upstream model, or billing
     model when possible; otherwise use a documented fallback encoding.

3. Decide where to compute and store estimates.
   - Prefer computing at request-record creation time so list pages do not need to
     load and parse large request bodies for every pending row.
   - Add nullable fields such as:
     - `estimated_input_tokens`
     - `estimated_input_tokenizer`
     - `estimated_input_model`
   - Keep these fields separate from `billing_input_tokens`.
   - Do not overwrite them when the request completes; actual usage should simply
     take precedence in the UI.

4. Update row and detail shaping in `admin.py`.
   - For pending records with no actual input usage, expose the estimate and an
     `is_estimated` flag.
   - For completed records, continue to prefer billing snapshot usage, then
     response-extracted usage.
   - Keep run stats and cost calculations on actual usage only.

5. Update `_requests_table.html`.
   - Render the estimated input value in the token triplet for pending rows.
   - Use muted/shaded styling for the number and label.
   - Keep output and total as `-` unless actual usage exists.
   - Avoid widening the token column or making completed rows noisier.

6. Update request detail UI.
   - Add estimated input tokens to the Cost Estimate or metadata area for pending
     records.
   - Show tokenizer/model source when available.
   - Keep pricing/cost fields empty unless actual usage and pricing are available.

7. Update CSS.
   - Add a clear visual treatment for estimated values, such as a tinted background,
     lighter text, or dashed underline.
   - Ensure contrast remains readable and the table stays compact.

8. Update tests.
   - Add tokenizer helper tests for chat completions, responses, tools, and unknown
     shapes.
   - Add admin UI tests proving pending rows show shaded estimated input tokens.
   - Add tests proving completed rows prefer actual usage over estimates.
   - Add tests proving run stats and cost totals do not count estimated pending
     input tokens.
   - Add dependency-fallback coverage if the tokenizer import is optional.

9. Run focused verification.
   - `.\.venv\Scripts\pytest.exe -q tests\test_rendering_and_cli.py tests\test_proxy_capture.py tests\test_admin_ui.py`
   - `.\.venv\Scripts\ruff.exe check src tests`
   - `.\.venv\Scripts\python.exe -m compileall -q src tests`

10. Run the full test suite before committing the implementation.
    - `.\.venv\Scripts\pytest.exe -q`

### Acceptance Criteria

- Pending request rows show an estimated input token count when the request body can
  be tokenized.
- Estimated input token values are visually shaded/muted and labeled as estimates.
- Completed request rows still show actual token usage when available.
- Estimated tokens are not used for billing snapshots, run stats, or what-if cost
  totals.
- Tests cover estimation, UI rendering, and actual-usage precedence.

## Later v0.3 Features

Add the next requested features here as they are defined. Each feature should include
the problem, desired UX or behavior, non-goals, implementation plan, and acceptance
criteria before implementation begins.
