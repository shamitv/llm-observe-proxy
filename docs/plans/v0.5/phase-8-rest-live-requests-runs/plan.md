# Phase 8 — REST Live Requests/Runs UI

[← Back to Master Plan](../implementation_plan.md)

## Goal

Move Requests and Runs admin data out of server-rendered tables and into REST-backed
live views that update while traffic is being captured.

## Key Changes

- Add JSON APIs for request list/detail and run list/detail, with the same filters,
  pagination, formatting, render modes, run metrics, and not-found behavior previously
  handled by Jinja contexts.
- Keep `/admin`, `/admin/requests/{id}`, `/admin/runs`, and `/admin/runs/{id}` as
  lightweight HTML shells with live-page attributes, loading states, and fallback run
  forms.
- Add client-side controllers that fetch immediately, poll every second while visible,
  abort overlapping fetches, preserve state on failures, update filters/pagination with
  browser history, and submit run start/end through REST.
- Keep Settings, proxy forwarding/capture, SQLite schema, and the existing run what-if
  API unchanged.
- Update pytest to use a free dynamic fake-upstream port so a real proxy can continue
  running on `8080` during tests.

## Test Plan

- Verify live request APIs cover filtering, pagination, render modes, pending records,
  route metadata, image/tool/Markdown/SSE rendering, and JSON 404 responses.
- Verify live run APIs cover start/end actions, active-run summaries, detail metrics,
  request pagination, formatting, and JSON 404 responses.
- Verify shell pages expose the expected `data-live-page`, API URL, and 1-second polling
  markers, with static JS assertions for polling and run controls.
- Run:
  - `.venv/bin/ruff check src tests scripts`
  - `.venv/bin/python -m compileall -q src tests scripts`
  - `.venv/bin/pytest -q`

## Assumptions

- “Remove server side rendering” applies to request/run data regions, not the shared
  admin shell or Settings pages.
- Polling is the Phase 8 transport; WebSockets remain deferred.
- No database migration is required.
