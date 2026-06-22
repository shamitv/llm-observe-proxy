# Phase 2 — REST-Backed Admin UI — TODO

[← Phase 2 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Commit Plan

- [x] `docs: add v0.6 REST admin UI phase`
- [ ] `feat: add REST settings page payloads`
- [ ] `feat: add pricing and diagnostics admin APIs`
- [ ] `feat: render settings updates without reloads`
- [ ] `test: cover REST-backed admin UI`
- [ ] `docs: document REST-backed admin updates`

## Planning

- [x] Add Phase 2 to the v0.6 master plan.
- [x] Add the Phase 2 implementation plan and TODO.
- [x] Keep the planning commit free of application-code changes.
- [x] Define normal navigation as out of scope for in-place rendering.
- [x] Choose event-driven Settings refresh instead of continuous polling.

## Settings Page Payloads

- [ ] Add `GET /admin/api/settings/{tab}`.
- [ ] Return JSON `404` for unknown tabs.
- [ ] Standardize `tab`, `summary`, `data`, `options`, and `pagination`.
- [ ] Add shared `days=30` handling with `1..3650` validation.
- [ ] Add bounded `page` and `per_page` parsing for registry tabs.
- [ ] Add Server payload.
- [ ] Add Routing payload with startup and database routes.
- [ ] Add Providers payload with usage and cached health.
- [ ] Add Pricing payload with nested tiers.
- [ ] Add Diagnostics payload with defaults and cached health.
- [ ] Add Data payload with storage and retention stats.
- [ ] Reuse existing row and formatting helpers.

## Pricing REST API

- [ ] Add filtered/paginated `GET /admin/api/model-prices`.
- [ ] Add `POST /admin/api/model-prices`.
- [ ] Add `PUT /admin/api/model-prices/{price_id}`.
- [ ] Add `DELETE /admin/api/model-prices/{price_id}`.
- [ ] Add `POST /admin/api/model-prices/{price_id}/tiers`.
- [ ] Add `DELETE /admin/api/model-price-tiers/{tier_id}`.
- [ ] Return saved price/tier rows after mutations.
- [ ] Return `201` for created prices and tiers.
- [ ] Return JSON `404` for missing prices, parents, and tiers.
- [ ] Preserve current aliases, rate, bound, metadata, and active-state validation.

## Diagnostics REST API

- [ ] Add `POST /admin/api/diagnostics/upstream-test`.
- [ ] Accept simple, image, and tool-call tests.
- [ ] Reuse routing selection and upstream forwarding helpers.
- [ ] Return structured success and failed-diagnostic results.
- [ ] Return JSON `400` for invalid test kinds.
- [ ] Keep diagnostic failures distinct from API transport/validation failures.

## Settings Shells

- [ ] Add live Settings root, tab, and API URL markers.
- [ ] Add accessible loading/status/retry region.
- [ ] Keep shared sidebar, tabs, headings, and normal links server-rendered.
- [ ] Replace server data rows/cards with loading mount points.
- [ ] Keep static form structures and HTML fallback actions.
- [ ] Add stable mount points for summaries, registries, editors, options, usage,
  diagnostics, storage, and retention.
- [ ] Add explicit empty and stale-data states.

## Settings Controller

- [ ] Fetch the current tab immediately.
- [ ] Abort superseded reads.
- [ ] Add event-delegated form and action handling.
- [ ] Prevent duplicate mutations.
- [ ] Disable and restore initiating controls during mutations.
- [ ] Refresh affected data after successful mutations.
- [ ] Keep the last successful rendering after read failures.
- [ ] Add Retry/Refresh behavior.
- [ ] Add `pushState`/`popstate` for filters and pagination.
- [ ] Reset pagination to page 1 when filters change.
- [ ] Refresh on safe visibility return.
- [ ] Do not add interval polling for Settings.

## State Preservation

- [ ] Track form dirty state from input/change events.
- [ ] Do not overwrite dirty editor forms.
- [ ] Preserve valid select values when options refresh.
- [ ] Preserve scroll position.
- [ ] Preserve focus and input selection when still applicable.
- [ ] Preserve selected provider/route rows.
- [ ] Preserve open pricing tier drawers.
- [ ] Keep confirmation and image modals outside live replacement regions.
- [ ] Clear dirty state only after success or explicit reset.
- [ ] Skip visibility refresh while dirty or mutating.

## Server Tab

- [ ] Save listener settings through REST.
- [ ] Save fallback/pass-through defaults through REST.
- [ ] Save compatibility fixes through REST.
- [ ] Run upstream diagnostics through REST.
- [ ] Refresh recent routes without navigation.
- [ ] Refresh retention preview without navigation.

## Routing Tab

- [ ] Render filtered/paginated route registry from JSON.
- [ ] Create and update editable routes through REST.
- [ ] Delete editable routes through REST confirmation.
- [ ] Keep startup routes locked.
- [ ] Keep route discovery preview/apply in place.
- [ ] Keep route simulation/sample rendering in place.
- [ ] Refresh registry, usage, summary, and provider options after mutations.

## Providers Tab

- [ ] Render filtered/paginated provider registry from JSON.
- [ ] Create and update providers through REST.
- [ ] Delete providers through REST confirmation.
- [ ] Run selected-provider health test in place.
- [ ] Run all-provider health checks in place.
- [ ] Refresh registry, usage, health, summary, and fallback options after mutations.

## Pricing Tab

- [ ] Render filtered/paginated prices and nested tiers from JSON.
- [ ] Create and update model prices through REST.
- [ ] Delete model prices through REST confirmation.
- [ ] Create and delete tiers through REST.
- [ ] Preserve open tier drawers after refresh.
- [ ] Keep catalog preview/apply in place.
- [ ] Refresh pricing registry and summary after catalog apply.

## Diagnostics Tab

- [ ] Run provider health checks in place.
- [ ] Run upstream simple/image/tool tests in place.
- [ ] Keep latest upstream result visible until replaced.
- [ ] Run route simulation and sample generation in place.
- [ ] Show diagnostic errors without discarding form values.

## Data Tab

- [ ] Render storage stats from JSON.
- [ ] Refresh retention preview in place.
- [ ] Trim through REST confirmation.
- [ ] Clear confirmation state after successful trim.
- [ ] Refresh storage and retention counts after trim.

## Requests, Runs, And Phase 1 Audit

- [ ] Confirm request filters/pagination/render modes remain REST-backed.
- [ ] Confirm run filters/pagination/actions/what-if remain REST-backed.
- [ ] Keep normal navigation for opening or creating resources.
- [ ] Confirm request/run polling remains one second.
- [ ] Confirm an open Phase 1 image modal survives request-detail polling.
- [ ] Confirm actual-size mode is not reset by polling.

## Accessibility And Feedback

- [ ] Announce loading, success, stale, and error states with `aria-live`.
- [ ] Keep validation errors adjacent to their forms.
- [ ] Add accessible Retry/Refresh controls.
- [ ] Preserve visible focus indicators.
- [ ] Keep destructive confirmation keyboard-accessible.
- [ ] Do not use color alone for status or errors.

## API Tests

- [ ] Test every Settings tab payload and unknown-tab `404`.
- [ ] Test payload top-level and tab-specific contracts.
- [ ] Test provider/route/pricing filters and pagination bounds.
- [ ] Test price create/list/update/delete.
- [ ] Test tier create/delete and validation.
- [ ] Test missing price, parent, and tier responses.
- [ ] Test simple, image, tool, invalid, and failed diagnostics.
- [ ] Test existing admin API compatibility.
- [ ] Test new admin routes remain outside public OpenAPI.

## UI Tests

- [ ] Test every Settings shell's live markers and mount points.
- [ ] Test HTML fallback actions remain present.
- [ ] Test read cancellation and duplicate-mutation guards.
- [ ] Test event delegation and history handling.
- [ ] Test dirty-form and visibility-refresh protection.
- [ ] Test loading, stale-data, error, and retry rendering.
- [ ] Test request/run in-page actions avoid reload paths.
- [ ] Test Phase 1 gallery/modal placement relative to live regions.

## Browser Verification

- [ ] Verify all six Settings tabs at desktop width.
- [ ] Verify all six Settings tabs at mobile width.
- [ ] Verify filter and pagination without document navigation.
- [ ] Verify provider, route, price, and tier mutations without reload.
- [ ] Verify health, diagnostics, simulation, catalog, and retention actions.
- [ ] Verify validation and failed requests preserve user input.
- [ ] Verify duplicate submissions are blocked.
- [ ] Verify dirty forms survive visibility changes.
- [ ] Verify scroll, focus, selection, and drawers survive refresh.
- [ ] Verify Requests/Runs and Phase 1 image preview remain stable.
- [ ] Refresh affected seeded screenshots from the demo harness only.

## Documentation

- [ ] Update `design.md` with REST-backed Settings behavior and state preservation.
- [ ] Update `README.md`.
- [ ] Update `README.pypi.md`.
- [ ] Update `docs/tests/README.md`.
- [ ] Keep PyPI documentation free of local screenshot references.

## Final Verification

- [ ] `.venv/bin/ruff check src tests scripts`
- [ ] `.venv/bin/python -m compileall -q src tests scripts`
- [ ] `.venv/bin/pytest -q`
- [ ] `git diff --check`
- [ ] Confirm no public API contract changes.
- [ ] Confirm no database migration or dependency change.
- [ ] Confirm Settings has no continuous poller.
- [ ] Confirm HTML POST compatibility handlers remain.
- [ ] Confirm record-only forwarding behavior is unchanged.
- [ ] Review the final branch diff for unrelated changes.
