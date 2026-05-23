# Phase 5 — Tab Implementations — TODO

[← Phase 5 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Server Tab — `settings_server.html`

### Connection Summary
- [ ] Proxy listener summary card (host:port)
- [ ] Client base URL summary card (http://host:port/v1)
- [ ] Global upstream summary card (provider / model) — highlighted
- [ ] Stored rows summary card (count + older than N days)

### Proxy Listener Card
- [ ] Port number input (min=1, max=65535, required)
- [ ] "Expose on LAN / all interfaces" checkbox
- [ ] Helper text: "Allow connections from other devices on your network."
- [ ] Warning text when exposed: "Network exposed. Use only on trusted networks."
- [ ] "Save listener settings" button
- [ ] Wire form POST to `/admin/settings/incoming`

### Global Upstream Fallback Defaults Card
- [ ] Global upstream URL input (required)
- [ ] Default provider dropdown (populated from providers)
- [ ] Default model input (text or dropdown)
- [ ] Dynamic helper text showing current fallback behavior
- [ ] "Save upstream defaults" button
- [ ] Wire form POST to `/admin/api/settings/upstream-defaults`

### Compatibility Fixes Card
- [ ] Render checkboxes for each fix from `compatibility_fix_rows()`
- [ ] Show fix ID as bold label
- [ ] Show description below each checkbox
- [ ] "Advanced manual edit (JSON)" collapsible textarea
- [ ] "Save fixes" button
- [ ] Wire form to collect checked IDs into hidden field
- [ ] POST to `/admin/settings/compat-fixes`

### Model Routes Summary Card
- [ ] Compact route table with columns from mockup
- [ ] "Showing X of Y routes" footer text
- [ ] Edit icon per row (links to Routing tab with route selected)
- [ ] Delete icon per row (with confirmation)
- [ ] "+ Add route" button (links to Routing tab)

### Test Route / Diagnostics Card
- [ ] Select route dropdown (populated from routes)
- [ ] Test type dropdown (Simple message, Image message, Function call)
- [ ] Message textarea with default prompt
- [ ] Route preview panel (Upstream URL, Send as model, Provider)
- [ ] Result panel (status badge, duration, response body)
- [ ] Error panel for failed tests
- [ ] "Run test" button
- [ ] Wire to test-upstream endpoint

### Data Retention (Danger Zone) Card
- [ ] Red danger-zone border styling
- [ ] "Retain for" days input with "days" label
- [ ] "I understand this will permanently delete older records" checkbox
- [ ] "Trim records" button (red, disabled until checkbox checked)
- [ ] "Refresh count" button
- [ ] Preview count: "Current preview: X rows will be deleted."
- [ ] Wire to trim endpoint

## Providers Tab — `settings_providers.html`

### Connection Summary
- [ ] Active providers count card
- [ ] Default provider card — highlighted
- [ ] Default model family card
- [ ] Stored rows card

### Provider Registry Card
- [ ] Search input with search icon
- [ ] Status filter dropdown (All status, Active, Inactive)
- [ ] Currency filter dropdown (All currencies + unique values)
- [ ] "+ Add provider" button
- [ ] Provider table with all columns from mockup
  - [ ] Provider name (with icon placeholder)
  - [ ] Slug
  - [ ] Base URL
  - [ ] Currency
  - [ ] Status badge
  - [ ] Models / Routes count
  - [ ] Actions (edit pencil, delete trash)
- [ ] Pagination (page numbers, prev/next)
- [ ] Row click → populate selected provider card
- [ ] Client-side search filtering
- [ ] "Showing X to Y of Z providers" text

### Selected Provider Card
- [ ] Provider name input
- [ ] Slug input
- [ ] Base URL input
- [ ] Currency dropdown
- [ ] API key env var input
- [ ] "Default for fallback" toggle
- [ ] Supported capabilities chips (Text, Vision, Tool calling)
- [ ] Info text about fallback behavior
- [ ] "Save provider" button (teal)
- [ ] "Test provider" button (outline)
- [ ] Wire save to provider API
- [ ] Wire test to provider test API

### Fallback Defaults Card
- [ ] Default provider dropdown
- [ ] Default model dropdown/input
- [ ] Resolution rule display
- [ ] Info text explaining fallback

### Provider Health / Diagnostics Card
- [ ] "Run health checks" button
- [ ] Results table (Provider, Last check, Latency, Auth, Result)
- [ ] Status badges for each result
- [ ] Loading state during health check
- [ ] Wire to `/admin/api/providers/health-checks`

### Recent Provider Usage Card
- [ ] Usage table (Provider, Requests today, Estimated cost, Active routes)
- [ ] "View full usage analytics →" link
- [ ] Wire to `/admin/api/providers/usage`

## Routing Tab — `settings_routing.html`

### Connection Summary
- [ ] Active routes count card
- [ ] Default provider card — highlighted
- [ ] Default model family card
- [ ] Stored rows card

### Route Registry Card
- [ ] Search input with search icon
- [ ] Status filter dropdown
- [ ] Provider filter dropdown
- [ ] "+ Add route" button
- [ ] Route table with all columns from mockup
  - [ ] Incoming model
  - [ ] Match type
  - [ ] Route upstream URL
  - [ ] Send as model
  - [ ] Provider
  - [ ] Fallback (Yes/No)
  - [ ] Status badge
  - [ ] Actions (edit, delete)
- [ ] Pagination
- [ ] Row click → populate selected route card
- [ ] Client-side search filtering
- [ ] "Showing X to Y of Z routes" text

### Selected Route Card
- [ ] Incoming model input
- [ ] Match type dropdown (Exact match, Prefix match)
- [ ] Route upstream URL input
- [ ] Send as model input
- [ ] Provider dropdown
- [ ] API key env var input
- [ ] Compatibility fixes chips/tags display
- [ ] Override fallback toggle
- [ ] Route priority dropdown (1–100)
- [ ] Enabled toggle
- [ ] Dynamic info text based on current values
- [ ] "Save route" button (teal)
- [ ] "Test route" button (outline)
- [ ] Wire save to route API
- [ ] Wire test to route test API

### Fallback Routing Behavior Card
- [ ] Default provider dropdown
- [ ] Default model dropdown/input
- [ ] Resolution rule display
- [ ] Info text explaining fallback

### Route Simulator / Diagnostics Card
- [ ] Incoming model to test input
- [ ] Message type dropdown
- [ ] Matched route preview (route, URL, model, provider)
- [ ] Result badge (Match found, No match, Fallback)
- [ ] "Run simulation" button
- [ ] Wire to `/admin/api/routes/simulate`

### Recent Route Usage Card
- [ ] Usage table (Route, Requests today, Last matched)
- [ ] "View full routing analytics →" link
- [ ] Wire to `/admin/api/routes/usage`

## JavaScript — `app.js`

- [ ] Table row selection (click to highlight + populate editor)
- [ ] Client-side search filtering for tables
- [ ] Provider health check fetch + render
- [ ] Route simulator fetch + render
- [ ] Collapsible sections (Advanced manual edit)
- [ ] Delete confirmation dialogs
- [ ] Form submit button disable-after-click
- [ ] Connection summary refresh after save
- [ ] Checkbox compat fixes → hidden field collector
- [ ] Compatibility fixes chip rendering

## Admin Route Handlers

- [ ] Update server tab handler with full context data
- [ ] Update providers tab handler with full context data
- [ ] Update routing tab handler with full context data
- [ ] Shared context builder for connection summary data

## Tests — `tests/test_admin_ui.py`

### Server Tab
- [ ] `test_server_tab_shows_listener_form`
- [ ] `test_server_tab_shows_upstream_form`
- [ ] `test_server_tab_shows_compat_fixes`
- [ ] `test_server_tab_shows_routes_summary`
- [ ] `test_server_tab_shows_test_form`
- [ ] `test_server_tab_shows_danger_zone`
- [ ] `test_server_tab_save_listener`
- [ ] `test_server_tab_save_upstream_defaults`
- [ ] `test_server_tab_save_compat_fixes_checkboxes`
- [ ] `test_server_tab_trim_requires_confirmation`

### Providers Tab
- [ ] `test_providers_tab_shows_registry`
- [ ] `test_providers_tab_shows_add_form`
- [ ] `test_providers_tab_shows_fallback_defaults`
- [ ] `test_providers_tab_create_provider`
- [ ] `test_providers_tab_delete_provider`
- [ ] `test_providers_tab_update_provider`
- [ ] `test_providers_tab_health_checks_endpoint`
- [ ] `test_providers_tab_usage_endpoint`

### Routing Tab
- [ ] `test_routing_tab_shows_registry`
- [ ] `test_routing_tab_shows_add_form`
- [ ] `test_routing_tab_shows_fallback_behavior`
- [ ] `test_routing_tab_shows_simulator`
- [ ] `test_routing_tab_create_route_exact`
- [ ] `test_routing_tab_create_route_prefix`
- [ ] `test_routing_tab_delete_route`
- [ ] `test_routing_tab_update_route`
- [ ] `test_routing_tab_simulate_match`
- [ ] `test_routing_tab_simulate_fallback`
- [ ] `test_routing_tab_usage_endpoint`

## Verification

- [ ] `ruff check src tests` passes
- [ ] `python -m compileall -q src tests` passes
- [ ] `pytest tests/test_admin_ui.py -q` passes
- [ ] `pytest -q` full suite passes (no regressions)
- [ ] Manual visual comparison against mockups
- [ ] Commit to `feature/v0.5-admin-ui` branch
