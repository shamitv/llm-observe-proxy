# Phase 2 — REST-Backed Admin UI — TODO

[← Phase 2 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Commit Plan

- [x] `docs: add v0.6 REST admin UI phase`
- [x] `feat: add REST settings and pricing APIs`
- [x] `test: cover REST settings and pricing APIs`
- [x] `feat: render settings updates without reloads`
- [x] `test: cover REST-backed admin UI`
- [x] `docs: document REST-backed admin updates`

## Planning

- [x] Add Phase 2 to the v0.6 master plan.
- [x] Add the Phase 2 implementation plan and TODO.
- [x] Keep the planning commit free of application-code changes.
- [x] Define normal navigation as out of scope for in-place rendering.
- [x] Choose event-driven Settings refresh instead of continuous polling.

## Settings Page Payloads

- [x] Add `GET /admin/api/settings/{tab}`.
- [x] Return JSON `404` for unknown tabs.
- [x] Standardize `tab`, `summary`, `data`, `options`, and `pagination`.
- [x] Add shared `days=30` handling with `1..3650` validation.
- [x] Add bounded `page` and `per_page` parsing for registry tabs.
- [x] Add Server payload.
- [x] Add Routing payload with startup and database routes.
- [x] Add Providers payload with usage and cached health.
- [x] Add Pricing payload with nested tiers.
- [x] Add Diagnostics payload with defaults and cached health.
- [x] Add Data payload with storage and retention stats.
- [x] Reuse existing row and formatting helpers.

## Pricing REST API

- [x] Add filtered/paginated `GET /admin/api/model-prices`.
- [x] Add `POST /admin/api/model-prices`.
- [x] Add `PUT /admin/api/model-prices/{price_id}`.
- [x] Add `DELETE /admin/api/model-prices/{price_id}`.
- [x] Add `POST /admin/api/model-prices/{price_id}/tiers`.
- [x] Add `DELETE /admin/api/model-price-tiers/{tier_id}`.
- [x] Return saved price/tier rows after mutations.
- [x] Return `201` for created prices and tiers.
- [x] Return JSON `404` for missing prices, parents, and tiers.
- [x] Preserve current aliases, rate, bound, metadata, and active-state validation.

## Diagnostics REST API

- [x] Add `POST /admin/api/diagnostics/upstream-test`.
- [x] Accept simple, image, and tool-call tests.
- [x] Reuse routing selection and upstream forwarding helpers.
- [x] Return structured success and failed-diagnostic results.
- [x] Return JSON `400` for invalid test kinds.
- [x] Keep diagnostic failures distinct from API transport/validation failures.

## Settings Shells

- [x] Add live Settings root, tab, and API URL markers.
- [x] Add accessible loading/status/retry region.
- [x] Keep shared sidebar, tabs, headings, and normal links server-rendered.
- [x] Replace server data rows/cards with loading mount points.
- [x] Keep static form structures and HTML fallback actions.
- [x] Add stable mount points for summaries, registries, editors, options, usage,
  diagnostics, storage, and retention.
- [x] Add explicit empty and stale-data states.

## Settings Controller

- [x] Fetch the current tab immediately.
- [x] Abort superseded reads.
- [x] Add event-delegated form and action handling.
- [x] Prevent duplicate mutations.
- [x] Disable and restore initiating controls during mutations.
- [x] Refresh affected data after successful mutations.
- [x] Keep the last successful rendering after read failures.
- [x] Add Retry/Refresh behavior.
- [x] Add `pushState`/`popstate` for filters and pagination.
- [x] Reset pagination to page 1 when filters change.
- [x] Refresh on safe visibility return.
- [x] Do not add interval polling for Settings.

## State Preservation

- [x] Track form dirty state from input/change events.
- [x] Do not overwrite dirty editor forms.
- [x] Preserve valid select values when options refresh.
- [x] Preserve scroll position.
- [x] Preserve focus and input selection when still applicable.
- [x] Preserve selected provider/route rows.
- [x] Preserve open pricing tier drawers.
- [x] Keep confirmation and image modals outside live replacement regions.
- [x] Clear dirty state only after success or explicit reset.
- [x] Skip visibility refresh while dirty or mutating.

## Server Tab

- [x] Save listener settings through REST.
- [x] Save fallback/pass-through defaults through REST.
- [x] Save compatibility fixes through REST.
- [x] Run upstream diagnostics through REST.
- [x] Refresh recent routes without navigation.
- [x] Refresh retention preview without navigation.

## Routing Tab

- [x] Render filtered/paginated route registry from JSON.
- [x] Create and update editable routes through REST.
- [x] Delete editable routes through REST confirmation.
- [x] Keep startup routes locked.
- [x] Keep route discovery preview/apply in place.
- [x] Keep route simulation/sample rendering in place.
- [x] Refresh registry, usage, summary, and provider options after mutations.

## Providers Tab

- [x] Render filtered/paginated provider registry from JSON.
- [x] Create and update providers through REST.
- [x] Delete providers through REST confirmation.
- [x] Run selected-provider health test in place.
- [x] Run all-provider health checks in place.
- [x] Refresh registry, usage, health, summary, and fallback options after mutations.

## Pricing Tab

- [x] Render filtered/paginated prices and nested tiers from JSON.
- [x] Create and update model prices through REST.
- [x] Delete model prices through REST confirmation.
- [x] Create and delete tiers through REST.
- [x] Preserve open tier drawers after refresh.
- [x] Keep catalog preview/apply in place.
- [x] Refresh pricing registry and summary after catalog apply.

## Diagnostics Tab

- [x] Run provider health checks in place.
- [x] Run upstream simple/image/tool tests in place.
- [x] Keep latest upstream result visible until replaced.
- [x] Run route simulation and sample generation in place.
- [x] Show diagnostic errors without discarding form values.

## Data Tab

- [x] Render storage stats from JSON.
- [x] Refresh retention preview in place.
- [x] Trim through REST confirmation.
- [x] Clear confirmation state after successful trim.
- [x] Refresh storage and retention counts after trim.

## Requests, Runs, And Phase 1 Audit

- [x] Confirm request filters/pagination/render modes remain REST-backed.
- [x] Confirm run filters/pagination/actions/what-if remain REST-backed.
- [x] Keep normal navigation for opening or creating resources.
- [x] Confirm request/run polling remains one second.
- [x] Confirm an open Phase 1 image modal survives request-detail polling.
- [x] Confirm actual-size mode is not reset by polling.

## Accessibility And Feedback

- [x] Announce loading, success, stale, and error states with `aria-live`.
- [x] Keep validation errors adjacent to their forms.
- [x] Add accessible Retry/Refresh controls.
- [x] Preserve visible focus indicators.
- [x] Keep destructive confirmation keyboard-accessible.
- [x] Do not use color alone for status or errors.

## API Tests

- [x] Test every Settings tab payload and unknown-tab `404`.
- [x] Test payload top-level and tab-specific contracts.
- [x] Test provider/route/pricing filters and pagination bounds.
- [x] Test price create/list/update/delete.
- [x] Test tier create/delete and validation.
- [x] Test missing price, parent, and tier responses.
- [x] Test simple, image, tool, invalid, and failed diagnostics.
- [x] Test existing admin API compatibility.
- [x] Test new admin routes remain outside public OpenAPI.

## UI Tests

- [x] Test every Settings shell's live markers and mount points.
- [x] Test HTML fallback actions remain present.
- [x] Test read cancellation and duplicate-mutation guards.
- [x] Test event delegation and history handling.
- [x] Test dirty-form and visibility-refresh protection.
- [x] Test loading, stale-data, error, and retry rendering.
- [x] Test request/run in-page actions avoid reload paths.
- [x] Test Phase 1 gallery/modal placement relative to live regions.

## Browser Verification

- [x] Verify all six Settings tabs at desktop width.
- [x] Verify all six Settings tabs at mobile width.
- [x] Verify filter and pagination without document navigation.
- [x] Verify provider, route, price, and tier mutations without reload.
- [x] Verify health, diagnostics, simulation, catalog, and retention actions.
- [x] Verify validation and failed requests preserve user input.
- [x] Verify duplicate submissions are blocked.
- [x] Verify dirty forms survive visibility changes.
- [x] Verify scroll, focus, selection, and drawers survive refresh.
- [x] Verify Requests/Runs and Phase 1 image preview remain stable.
- [x] Refresh affected seeded screenshots from the demo harness only.

## Documentation

- [x] Update `design.md` with REST-backed Settings behavior and state preservation.
- [x] Update `README.md`.
- [x] Update `README.pypi.md`.
- [x] Update `docs/tests/README.md`.
- [x] Keep PyPI documentation free of local screenshot references.

## Final Verification

- [x] `.venv/bin/ruff check src tests scripts`
- [x] `.venv/bin/python -m compileall -q src tests scripts`
- [x] `.venv/bin/pytest -q`
- [x] `git diff --check`
- [x] Confirm no public API contract changes.
- [x] Confirm no database migration or dependency change.
- [x] Confirm Settings has no continuous poller.
- [x] Confirm HTML POST compatibility handlers remain.
- [x] Confirm record-only forwarding behavior is unchanged.
- [x] Review the final branch diff for unrelated changes.
