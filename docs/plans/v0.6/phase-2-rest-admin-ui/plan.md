# Phase 2 — REST-Backed Admin UI

[← Back to Master Plan](../implementation_plan.md)

## Goal

Make all routine admin updates happen through REST calls and targeted DOM rendering
instead of full-document reloads. Keep normal navigation between pages, preserve the
dependency-free frontend, and avoid background polling that can disturb editable
Settings forms.

## Current State

Requests and Runs already use lightweight Jinja shells, JSON APIs, browser history, and
one-second polling. Their filters, pagination, render modes, and run lifecycle actions
update without reloading the current page.

Settings has a mixed implementation:

- route simulation, model lookup, generated-route discovery, provider health checks,
  and pricing catalog sync already use REST;
- listener, fallback, compatibility, provider, route, pricing, tier, diagnostics, and
  retention forms still have HTML POST flows that redirect and reload;
- most Settings registries and summary cards are rendered into the initial HTML rather
  than loaded from JSON; and
- model-price CRUD, price-tier mutations, and upstream diagnostics do not yet have
  complete admin JSON APIs.

## Implementation Changes

### 1. Settings Shells And Page Payloads

Keep these navigable HTML routes:

```text
/admin/settings/server
/admin/settings/routing
/admin/settings/providers
/admin/settings/pricing
/admin/settings/diagnostics
/admin/settings/data
```

Each route renders the shared Settings navigation, tab heading, accessible live status,
static form/control structure, and loading placeholders. Current tab data is fetched
from:

```text
GET /admin/api/settings/{tab}
```

Supported `tab` values are `server`, `routing`, `providers`, `pricing`, `diagnostics`,
and `data`. Unknown values return JSON `404`.

Every successful page response uses this top-level shape:

```json
{
  "tab": "providers",
  "summary": {},
  "data": {},
  "options": {},
  "pagination": null
}
```

- `summary` contains the tab's connection-summary values.
- `data` contains the primary records and current settings for the tab.
- `options` contains select/filter choices needed to render controls.
- `pagination` contains `page`, `per_page`, `total`, `total_pages`, `has_previous`,
  and `has_next` for registry tabs; it is `null` where pagination does not apply.

Accepted query parameters:

- all tabs: `days`, default `30`, range `1..3650`;
- Routing: `search`, `status`, `provider`, `page`, `per_page`;
- Providers: `search`, `status`, `currency`, `page`, `per_page`;
- Pricing: `search`, `status`, `provider`, `page`, `per_page`;
- `page` defaults to `1`; `per_page` defaults to `25` and is limited to `100`.

Tab payload contents:

- **Server**: listener, client base URL, pass-through upstream, fallback defaults,
  compatibility fixes and available fix options, recent model routes, retention
  preview, and registry counts.
- **Routing**: filtered/paginated startup and database routes, provider choices,
  route usage, fallback defaults, and generated-route metadata. Startup routes remain
  visibly locked.
- **Providers**: filtered/paginated providers, provider usage, fallback defaults, and
  the latest cached health results.
- **Pricing**: filtered/paginated model prices with nested tiers and provider choices.
- **Diagnostics**: providers, cached health results, route/fallback context, and default
  test form values. Test results remain client-session UI state after execution.
- **Data**: storage stats, retention preview, current database record range, and
  fallback summary.

Reuse existing row-formatting helpers so HTML fallback views and JSON views keep the
same labels, values, and validation behavior.

### 2. Complete Admin REST Operations

Keep existing admin endpoints for listener/defaults/compatibility, providers, routes,
health checks, catalog sync, retention, and run actions.

Add model-price endpoints:

```text
GET    /admin/api/model-prices
POST   /admin/api/model-prices
PUT    /admin/api/model-prices/{price_id}
DELETE /admin/api/model-prices/{price_id}
```

- List supports the same pricing filters and bounded pagination as the Pricing page.
- Create/update accepts provider, model, display name, aliases, scalar rates, active
  state, and notes.
- Create returns the saved row and `201`; update returns the saved row and `200`.
- Delete returns `{"deleted": true}` or JSON `404`.
- Validation errors return `{"detail": "..."}` with `400` or FastAPI `422`.

Add tier endpoints:

```text
POST   /admin/api/model-prices/{price_id}/tiers
DELETE /admin/api/model-price-tiers/{tier_id}
```

- Creation accepts the existing bounds, rates, label, source metadata, and notes.
- Missing parent prices or tiers return JSON `404`.
- Successful creation returns the saved tier and `201`.

Add diagnostics:

```text
POST /admin/api/diagnostics/upstream-test
```

- Accept `test_kind`, `model`, and `prompt`.
- Reuse the existing routing selection and upstream-test implementation.
- Return the current structured test result, including success/error, status, route,
  upstream model, URL, duration, and response body.
- Invalid test kinds return JSON `400`; upstream failures remain successful API
  responses containing a failed diagnostic result, matching the current UI semantics.

Do not expose these routes in the public OpenAPI document or alter public `/api/*`
contracts.

### 3. Dependency-Free Settings Controller

Add a Settings controller in `static/app.js`, initialized from a root such as:

```html
data-live-page="settings"
data-settings-tab="providers"
data-api-url="/admin/api/settings/providers"
```

The controller:

- fetches the current page payload immediately;
- aborts a superseded read request;
- renders summary cards, registries, options, metadata, and empty states;
- uses event delegation from the Settings root instead of binding handlers to every
  re-rendered row;
- routes form submissions and actions to their admin REST endpoints;
- disables the initiating control while a mutation is in flight;
- prevents duplicate mutation submissions;
- re-fetches the current tab after successful mutations;
- preserves the last successful rendering when a read fails; and
- provides an explicit Retry/Refresh action.

Registry filters and pagination update `window.history` with `pushState`. `popstate`
restores controls from the URL and re-fetches the current tab. Filter changes return to
page 1.

Normal links between admin pages and Settings tabs continue using document navigation.
This phase is not a single-page application.

### 4. State Preservation

Before updating rendered regions, capture:

- window scroll position;
- active element identity and selection range where applicable;
- dirty form names and current values;
- selected provider or route identifier;
- open `<details>` tier drawers;
- current filter values and page;
- open confirmation or Phase 1 image modal state.

Rendering rules:

- never replace a dirty editor form with server data;
- update select options without discarding a still-valid selection;
- preserve selected rows when the record still exists;
- restore open tier drawers by stable price/tier identifiers;
- restore focus only when the user has not moved it elsewhere;
- restore scroll unless the action intentionally reveals a new validation/result area;
- keep modals outside replaceable live regions; and
- clear a form's dirty state only after its mutation succeeds or the user explicitly
  resets it.

A visibility return triggers a refresh only when the tab has no dirty form and no
mutation in flight.

### 5. Event-Driven Refresh And Feedback

Settings does not continuously poll.

Refresh occurs on:

- initial page load;
- successful save, delete, apply, test, or trim;
- explicit Retry/Refresh;
- browser `popstate`; and
- return to a visible tab when no form is dirty.

Use an `aria-live="polite"` status region for:

- initial loading;
- saving/deleting/testing states;
- concise success confirmation;
- stale-data warnings after failed refreshes; and
- actionable errors with Retry.

Validation errors remain near the relevant form and do not erase user input. Destructive
actions continue using the existing confirmation modal before the REST request.

### 6. Per-Tab Behavior

#### Server

- Save listener, fallback defaults, and compatibility fixes through existing REST
  endpoints.
- Run upstream diagnostics through the new diagnostics endpoint.
- Refresh recent-route and retention data in place.
- Replace retention count links with REST refresh actions.

#### Routing

- Load registry filters and pagination from the URL/API.
- Create/update/delete editable routes through existing route REST endpoints.
- Keep generated-route preview/apply and route simulation REST-backed.
- Refresh registry, summary, usage, and editor options after mutations.

#### Providers

- Create/update/delete providers through existing provider REST endpoints.
- Run selected-provider and all-provider health checks without navigation.
- Refresh registry, fallback options, usage, health, and summary after mutations.

#### Pricing

- Load and paginate prices through JSON.
- Create/update/delete prices and create/delete tiers through the new endpoints.
- Preserve open tier drawers after data refresh.
- Keep catalog preview/apply in place and refresh pricing data after apply.

#### Diagnostics

- Run provider health, upstream tests, route simulation, and sample generation in place.
- Keep the latest upstream test result visible until replaced or the page is left.

#### Data

- Refresh storage and retention previews through JSON.
- Trim through the existing REST endpoint after confirmation.
- Clear confirmation state and refresh all counts after successful trimming.

### 7. Requests, Runs, And Phase 1 Audit

- Keep one-second polling on request and run list/detail pages.
- Confirm filters, pagination, render-mode changes, run actions, and what-if updates do
  not reload the current document.
- Preserve normal navigation when opening a request/run or after creating a run.
- Confirm Phase 1's image gallery identity and modal live outside replaceable request
  detail regions so polling cannot close the preview or reset actual-size mode.

### 8. Compatibility And Documentation

- Keep current HTML POST handlers and redirects as compatibility fallbacks.
- Keep existing endpoint validation shared between HTML and JSON flows where practical.
- Do not change SQLite schema, proxy capture, forwarding, routing precedence, pricing
  math, retention semantics, or authentication behavior.
- Update `design.md`, `README.md`, `README.pypi.md`, and `docs/tests/README.md`.
- Refresh affected seeded Settings screenshots only through the demo harness.

## Test Plan

### API Tests

Extend `tests/test_admin_api.py`:

- verify every Settings tab payload and unknown-tab `404`;
- verify filter and pagination bounds for providers, routes, and pricing;
- verify page payload top-level keys and tab-specific data;
- cover price create/list/update/delete and missing-price `404`;
- cover tier create/delete, validation, and missing-parent/tier `404`;
- cover simple, image, tool, invalid, and failed upstream diagnostics;
- verify existing settings/provider/route/catalog/retention APIs remain compatible; and
- verify new admin APIs stay absent from the public OpenAPI document.

### Shell And Controller Tests

Extend `tests/test_admin_ui.py`:

- each Settings page is a live shell with tab and API markers;
- loading, status, retry, registry, editor, and result mount points are present;
- forms retain HTML fallback actions;
- the controller contains read cancellation, duplicate-mutation guards, event
  delegation, history handling, dirty-form protection, visibility refresh rules, and
  accessible status updates;
- request/run controllers continue using REST without reload-based update paths; and
- Phase 1 modal/gallery state is outside request-detail replacement regions.

### Seeded Browser Verification

At desktop and mobile widths:

1. Load every Settings tab and confirm data appears after the shell.
2. Filter and paginate without document navigation.
3. Save and delete providers, routes, prices, and tiers without reload.
4. Run health checks, upstream diagnostics, simulation, catalog apply, and retention
   preview/trim without reload.
5. Confirm success/error feedback, retry, validation preservation, and duplicate-submit
   prevention.
6. Edit a form, trigger visibility return, and confirm dirty values are not overwritten.
7. Confirm scroll, focus, selected rows, and open tier drawers survive refresh.
8. Confirm Requests/Runs still live-update and an open image preview survives polling.

### Verification Commands

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/python -m compileall -q src tests scripts
.venv/bin/pytest -q
git diff --check
```

## Acceptance Criteria

- No filter, pagination, save, delete, diagnostic, catalog, retention, or refresh action
  reloads its current admin page.
- All Settings content is sourced from admin JSON page payloads.
- Dirty forms and interaction state survive safe re-renders.
- Failures keep the last successful data visible and offer Retry.
- Settings refreshes are event-driven, not continuously polled.
- Existing HTML POST handlers remain functional fallbacks.
- Requests/Runs retain one-second REST polling and Phase 1's modal remains stable.
- No public API, database schema, dependency, or proxy behavior changes.
