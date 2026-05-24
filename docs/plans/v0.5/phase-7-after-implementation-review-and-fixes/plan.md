# Phase 7 — After-Implementation Review & Fixes

[← Back to Master Plan](../implementation_plan.md)

## Goal

Close the v0.5 after-implementation audit gaps found on Linux Firefox and bring the
implemented Settings UI closer to the mockups without expanding scope beyond the
admin control-plane polish.

## Audit Evidence

- Environment: Linux desktop with Firefox `150.0.3`.
- Validation server: seeded demo database on `http://127.0.0.1:8091`.
- Existing local server also observed on `http://127.0.0.1:8080`.
- The fallback provider `<select>` controls render and can persist values, but the
  Routing and Providers fallback cards sit low in common Firefox viewports and submit
  back to `/admin/settings/server`, which makes the dropdown interaction feel broken.
- Settings pages rendered no SVG/icon components; mockup iconography was represented
  by initials such as `S`, `R`, `P`, and text-only action buttons.

## Key Changes

- Extract the repeated fallback-defaults form into a shared Jinja macro used by
  Server, Routing, and Providers.
- Add a validated `return_to` field so each fallback form redirects back to its
  originating tab.
- Add a dependency-free enhanced fallback provider menu that keeps the native select as
  the submitted form control and falls back cleanly with JavaScript disabled.
- Add a small server-rendered icon macro set and use it for Settings navigation,
  summary cards, provider badges, and mockup-style action controls.
- Keep the UI compact and server-rendered; do not add auth, cache serving, export,
  pagination, or provider-health automation.

## Implementation Notes

- Valid fallback redirect targets are `/admin/settings/server`,
  `/admin/settings/routing`, and `/admin/settings/providers`; invalid values fall back
  to `/admin/settings/server`.
- The enhanced provider menu opens upward when near the viewport bottom, supports
  click, arrow keys, Enter/Space selection, Escape close, and visible focus.
- Icons are inline SVGs emitted by Jinja macros, with accessible labels or visible text
  where needed.
- Provider badges use generic/local-safe glyphs keyed by provider slug, avoiding
  trademarked logo assets.

## Test Plan

- Add admin UI tests that fallback forms render provider options and `return_to`.
- Verify saving fallback defaults from Server, Routing, and Providers redirects to the
  same tab.
- Verify invalid `return_to` values redirect to Server.
- Verify Settings pages render SVG icons for sidebar, tabs, summaries, provider badges,
  and key action controls.
- Verify the enhanced fallback select markup exists and can sync back to the native
  select for form submission.
- Run:
  - `.venv/bin/ruff check src tests scripts`
  - `.venv/bin/python -m compileall -q src tests scripts`
  - `.venv/bin/pytest -q`

## Manual Validation

- Run a disposable seeded DB server on a non-8080 port if `8080` is occupied.
- In Firefox, test Server, Routing, and Providers fallback provider menus at
  `1440x900` and `1366x768`.
- Confirm the menu opens in view, selection persists, and the form returns to the same
  tab.
- Refresh the affected after-implementation screenshots if the visual audit artifacts
  are being updated in the same release pass.
