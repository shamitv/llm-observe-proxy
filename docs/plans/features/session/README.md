# Task Runs Feature Plan

## User-facing name

Recommended name: **Run**, with **Task Run** used where extra clarity is needed.

Reason: the feature represents one bounded execution of a user task, not capture for its
own sake. A user can start a run before processing a video, benchmarking a local model,
or testing a prompt workflow, then end the run when the task is done. The UI can then
show aggregate performance and usage for that task.

Good UI labels:

- Primary nav/page: **Runs**
- Active state: **Run in progress**
- Primary action: **Start run**
- End action: **End run**
- Empty state: **No active run**
- Detail page title: **Run: Video processing benchmark**

Name tradeoffs:

- **Run**: best default from the user's point of view. Short, task-oriented, and natural
  for performance comparisons, exports, and summaries.
- **Task Run**: clearer in headings, docs, and empty states when "Run" feels too terse.
- **Trace**: useful as a technical/export concept, but less friendly as the primary UI
  noun. "Start trace" sounds observability-specific and may imply distributed tracing.
- **Session**: understandable, but overloaded with login sessions, browser sessions, and
  chat sessions.
- **Recording**: too capture-oriented for the real goal, which is measuring and
  understanding one task.

Implementation recommendation: use **Run**/**Task Run** in the UI and use an internal
model named `TaskRun` with a `task_runs` table. Keep "trace" available as a future export
format or analysis view, for example "Export trace".

## Goal

Allow a user to mark the start and end of a task-oriented run. Every proxy request
created while the run is active is still forwarded to upstream as usual and is also
associated with that run in SQLite.

The run detail page should answer questions such as:

- How long did this task take end to end?
- How many LLM requests did it make?
- Which models and endpoints were used?
- How many input, output, and total tokens were used?
- What was the observed throughput, such as output tokens per second?
- Did the task use streams, images, tools, or error-producing calls?
- Which requests contributed most to latency or token usage?

Future extensions should be able to export a run and summarize how the LLM was used for
that task by analyzing the captured request and response bodies.

## Example workflow

1. User opens the admin UI and starts a run named `Video processing - local Qwen`.
2. User runs their application workflow that processes one video through a local or cloud
   LLM.
3. The proxy records all requests as it already does, and assigns each request to the
   active run.
4. User ends the run.
5. The run detail page shows LLM wall time, request count, model mix, token totals,
   latency totals, and tokens-per-second metrics.
6. Later, the user can export or summarize that run.

## Behavior

- There is at most one active run at any time.
- Starting a new run automatically ends the currently active run.
- A request belongs to the active run at the moment the proxy creates its
  `RequestRecord`.
- If a streaming request starts during a run and completes after the run is ended, it
  still belongs to the original run.
- Ending a run sets `ended_at`; it does not mutate existing request records.
- Requests outside an active run remain captured, but have no run association.
- All proxy behavior remains record-only: always forward to upstream, then store capture
  data.

## Metrics

Initial run metrics should be computed from existing request records.

Core metrics:

- `request_count`
- `started_at`, `ended_at`, and active/incomplete status
- first request time and last completed response time
- LLM wall-clock duration, computed from first request start to last response completion
- run open duration, computed from `started_at` to `ended_at`, for context only
- total request duration, computed as the sum of `duration_ms`
- status code breakdown
- endpoint breakdown
- model breakdown
- stream/image/tool/error counts
- input, output, and total token totals from existing token extraction helpers

Throughput metrics:

- **Wall-clock output tokens/sec**: output tokens divided by LLM wall-clock duration.
- **Observed request output tokens/sec**: output tokens divided by summed request duration.
- **Wall-clock total tokens/sec**: total tokens divided by LLM wall-clock duration.

Notes:

- LLM wall-clock duration should be measured from `min(RequestRecord.created_at)` to
  `max(RequestRecord.completed_at)` for requests in the run. This captures idle gaps,
  orchestration, batching, client overhead, and concurrent request overlap between the
  first LLM call and the last LLM response.
- The manual start/end timestamps define which requests belong to a run and can show how
  long the run was open, but they should not be the denominator for tokens/sec.
- Summed request duration is useful for model/API throughput, but can over-count when
  requests overlap concurrently.
- Token totals may be incomplete for upstreams that omit usage objects. The UI should
  show unknown/missing values rather than pretending they are zero.

Future metrics:

- cost estimates per provider/model once pricing metadata exists
- prompt/cache token splits if present in upstream usage
- percentile latency across requests
- per-model throughput and token totals
- request timeline visualization

## Data model

Add a new table:

```text
task_runs
- id integer primary key
- name string nullable
- notes text nullable
- started_at datetime indexed
- ended_at datetime nullable indexed
- summary text nullable
- metadata_json text nullable
```

Add a nullable relationship from requests:

```text
request_records.task_run_id integer nullable indexed
  -> task_runs.id on delete set null
```

Indexes:

- `task_runs.started_at`
- `task_runs.ended_at`
- `request_records.task_run_id`

Compatibility note: the project currently initializes with SQLAlchemy `create_all()`.
That creates new tables but does not add columns to existing SQLite databases. Add a
small SQLite schema upgrade helper during `init_db()` to add the nullable `task_run_id`
column and index when missing.

## Backend changes

### `database.py`

- Add `TaskRun` model and `RequestRecord.task_run_id`.
- Add relationship fields:
  - `TaskRun.requests`
  - `RequestRecord.task_run`
- Add helper functions:
  - `get_active_task_run(session)`
  - `start_task_run(session, name=None, notes=None)`
  - `end_active_task_run(session)`
  - `get_task_run_stats(session, task_run_id)`
  - `list_task_runs_with_stats(session, limit=100)`
- Ensure `start_task_run` closes any active row before creating the new one.
- Ensure existing SQLite DBs get the nullable request column and index.

### `proxy.py`

- When creating `RequestRecord`, read the active task run inside the existing DB
  transaction and set `task_run_id`.
- Do not check the active run again when the upstream response completes.
- Keep non-streaming and SSE streaming capture paths unchanged except for the new
  association field.

### `admin.py`

- Add list/detail routes:
  - `GET /admin/runs`
  - `GET /admin/runs/{run_id}`
- Add action routes:
  - `POST /admin/runs/start`
  - `POST /admin/runs/end`
- Add request browser filter support:
  - `GET /admin?run=<id>`
- Include active run state in shared template contexts for the topbar or request browser
  heading.
- Build run stats using existing token extraction helpers and request metadata.

## UI changes

- Add **Runs** to the top nav.
- Add a compact active-run control near the request browser heading:
  - no active run: task name input plus **Start run**
  - active run: active name, elapsed time, request count, and **End run**
- Add a runs list with recent runs first.
- Add a run detail page with:
  - KPI band for LLM wall time, request count, token totals, and tokens/sec
  - model/endpoint/status breakdowns
  - stream/image/tool/error counts
  - request table filtered to the run
- Add a run badge/link to request detail pages and table rows.
- Keep the styling operational and dense, matching the current admin UI.

## Future export

Add exports after the basic run lifecycle is stable.

Candidate formats:

- JSON summary with run metadata, stats, and request IDs
- JSONL request export with one request/response pair per line
- HTML report for sharing benchmark results
- Zip bundle containing summary JSON, request JSONL, and extracted images/assets

Export should include enough metadata to reproduce or compare a task:

- run name, notes, start/end times
- proxy version
- upstream base URL or provider label
- models/endpoints used
- request and response payloads, unless redacted
- token, latency, status, and error stats

Open privacy decision: exports may contain prompts, responses, image data URLs, headers,
or tool arguments. Add explicit redaction options before broadening export usage.

## Future summary

Add an optional "Summarize run" action after exports or alongside them.

Possible summary output:

- what the task appeared to do
- models and endpoints used
- request timeline in plain language
- major latency and token contributors
- errors/retries/unusual responses
- tool use and image use
- suggested performance improvements

Safety/privacy considerations:

- Summarization should be explicit and user-triggered.
- Let the user choose the summarization model/upstream.
- Consider a local-only summarization mode for sensitive traces.
- Redact authorization headers and other secrets before any summary prompt is built.

## Testing plan

Add/update tests in `tests/test_admin_ui.py`:

- Starting a run creates an active run and shows active state.
- Ending a run closes the active run.
- Starting a second run ends the first one.
- Request browser can filter by run.
- Run detail page lists only associated requests.
- Run detail page shows aggregate token and request stats.
- Existing settings/template defaults remain defensive when active run context is absent.

Add/update tests in `tests/test_proxy_capture.py`:

- Requests made during an active run get `task_run_id`.
- Requests made outside an active run have `task_run_id is None`.
- A streaming request that starts during a run remains associated after the run ends.

Add/update database tests where appropriate:

- Existing SQLite DBs created before this feature can be opened and upgraded without data
  loss.
- Deleting a run leaves request rows intact with a null association, if delete is exposed
  later.
- Stats helpers handle missing token usage without treating unknown values as confirmed
  zero.

Run:

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe -q
```

## Open decisions

- Should run names be required, or default to a timestamp-based name such as
  `Run 2026-05-02 14:30`?
- Should users be able to edit run names/notes after completion?
- Should the UI use "End run" or "Stop run"? Recommendation: **End run**, because it
  sounds like completing a bounded task rather than stopping the proxy/capture system.
- Should the default request browser show all requests, or filter to the active/latest
  run when one exists?
- Should trimming old requests also trim empty old runs?
- Should a run be able to include manually selected requests from before/after the active
  window?

## Suggested implementation order

1. Add the `TaskRun` database model, request relationship, helper functions, and SQLite
   upgrade path.
2. Attach active `task_run_id` values in `proxy.py`.
3. Add admin start/end routes and minimal active-run context.
4. Add request browser filtering by run.
5. Add run stats helpers.
6. Add runs list/detail pages.
7. Add UI controls and request table/detail badges.
8. Add tests for lifecycle, run association, filtering, stats, and upgrade behavior.
9. Run quality checks and update screenshots/docs if the UI changes materially.
