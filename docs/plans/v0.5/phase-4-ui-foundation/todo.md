# Phase 4 — UI Foundation — TODO

[← Phase 4 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## CSS Design System

- [ ] Define CSS custom properties (design tokens)
  - [ ] Primary palette (teal/green)
  - [ ] Semantic colors (success, warning, danger, info)
  - [ ] Surface colors (bg, surface, border, text, muted)
  - [ ] Shadows (sm, card)
  - [ ] Border radius (default, lg)
  - [ ] Font family (system or Inter/Roboto import)
- [ ] `.app-shell` grid layout (sidebar + content)
- [ ] `.sidebar` styles
  - [ ] Fixed left panel
  - [ ] Background color
  - [ ] Width and padding
- [ ] `.sidebar-header` styles (section heading)
- [ ] `.sidebar-nav` styles
- [ ] `.sidebar-nav-item` styles
  - [ ] Icon + text layout
  - [ ] Hover state
  - [ ] Active state (teal highlight + left border)
- [ ] `.sidebar-env-card` styles (bottom card)
- [ ] `.main-content` / `.settings-content` styles
- [ ] `.connection-summary` strip styles
  - [ ] Horizontal card row
  - [ ] Background and border
- [ ] `.summary-card` styles
  - [ ] Icon circle
  - [ ] Label, value, helper text
  - [ ] Highlighted variant (teal border)
- [ ] `.tab-bar` styles (secondary tab row)
- [ ] `.tab-item` styles (with icon + active underline)
- [ ] `.card` base styles (white, shadow, rounded)
- [ ] `.card-header` styles
- [ ] `.status-badge` variants
  - [ ] `.status-active` (green)
  - [ ] `.status-inactive` (gray)
  - [ ] `.status-healthy` (green)
  - [ ] `.status-warning` (amber)
  - [ ] `.status-error` (red)
  - [ ] `.status-missing-key` (amber)
- [ ] `.form-field` styles
- [ ] `.danger-zone` card styles (red border)
- [ ] `.search-bar` styles
- [ ] `.filter-row` styles
- [ ] `.data-table` styles (zebra rows, hover)
- [ ] `.pagination` styles
- [ ] Button variants (primary, danger, ghost)
- [ ] Responsive breakpoints
  - [ ] Desktop (≥1024px): sidebar visible
  - [ ] Tablet (768–1023px): sidebar collapsible
  - [ ] Mobile (<768px): sidebar hidden
- [ ] Preserve existing page styles (Requests, Runs, Detail)

## Base Template Redesign

- [ ] Update `base.html` with new header structure
  - [ ] Brand icon + text
  - [ ] Main nav with active state support
  - [ ] User avatar placeholder
- [ ] Add `active_nav` variable support
- [ ] Add `app_body` block for layout override
- [ ] Preserve backward compatibility for existing templates

## Settings Base Template

- [ ] Create `templates/settings_base.html`
  - [ ] Extend `base.html`
  - [ ] Override `app_body` with sidebar + content grid
  - [ ] Sidebar navigation with all 6 tabs
  - [ ] `settings_tab` variable for active state
  - [ ] Environment card at sidebar bottom
  - [ ] `connection_summary` block
  - [ ] `summary_cards` block
  - [ ] `tab_bar` block
  - [ ] `settings_content` block

## Shared Components (Jinja Macros)

- [ ] Create `templates/_connection_summary.html`
  - [ ] `summary_card(icon, label, value, helper, highlighted)` macro
- [ ] Create `templates/_status_badge.html`
  - [ ] `status_badge(status)` macro
  - [ ] Map status strings to CSS classes

## Tab Skeleton Templates

- [ ] Create `templates/settings_server.html`
  - [ ] Extend `settings_base.html`
  - [ ] Set `settings_tab = "server"`
  - [ ] Add server-specific summary cards
  - [ ] Placeholder content
- [ ] Create `templates/settings_routing.html`
  - [ ] Set `settings_tab = "routing"`
  - [ ] Add routing-specific summary cards
  - [ ] Placeholder content
- [ ] Create `templates/settings_providers.html`
  - [ ] Set `settings_tab = "providers"`
  - [ ] Add provider-specific summary cards
  - [ ] Placeholder content
- [ ] Create `templates/settings_pricing.html`
  - [ ] Set `settings_tab = "pricing"`
  - [ ] Placeholder content
- [ ] Create `templates/settings_diagnostics.html`
  - [ ] Set `settings_tab = "diagnostics"`
  - [ ] Placeholder content
- [ ] Create `templates/settings_data.html`
  - [ ] Set `settings_tab = "data"`
  - [ ] Placeholder content

## Tab Routes in admin.py

- [ ] Add `GET /admin/settings/server` route
- [ ] Add `GET /admin/settings/routing` route
- [ ] Add `GET /admin/settings/providers` route
- [ ] Add `GET /admin/settings/pricing` route
- [ ] Add `GET /admin/settings/diagnostics` route
- [ ] Add `GET /admin/settings/data` route
- [ ] Update existing `GET /admin/settings` to redirect to `/admin/settings/server`
- [ ] Pass `settings_tab` context variable in each route
- [ ] Pass `active_nav = "settings"` in each route
- [ ] Pass connection summary data in each route (via shared helper)

## JavaScript Updates

- [ ] Update `app.js` for sidebar toggle (mobile/tablet)
- [ ] Add sidebar collapse/expand behavior

## Tests — `tests/test_admin_ui.py`

- [ ] `test_settings_redirects_to_server_tab`
- [ ] `test_server_tab_renders`
- [ ] `test_routing_tab_renders`
- [ ] `test_providers_tab_renders`
- [ ] `test_pricing_tab_renders`
- [ ] `test_diagnostics_tab_renders`
- [ ] `test_data_tab_renders`
- [ ] `test_sidebar_shows_all_tabs`
- [ ] `test_active_tab_highlighted`
- [ ] `test_connection_summary_present`
- [ ] `test_existing_requests_page_unchanged`
- [ ] `test_existing_runs_page_unchanged`
- [ ] `test_existing_detail_page_unchanged`

## Verification

- [ ] `ruff check src tests` passes
- [ ] `python -m compileall -q src tests` passes
- [ ] `pytest tests/test_admin_ui.py -q` passes
- [ ] `pytest -q` full suite passes (no regressions)
- [ ] Manual visual check: start proxy and verify all tabs render
- [ ] Manual visual check: existing pages (Requests, Runs) unchanged
- [ ] Commit to `feature/v0.5-admin-ui` branch
