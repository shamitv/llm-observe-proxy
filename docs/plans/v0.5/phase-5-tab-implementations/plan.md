# Phase 5 — Tab Implementations

[← Back to Master Plan](../implementation_plan.md)

## Goal

Implement the three primary settings tabs — **Server**, **Providers**, and **Routing** —
with full functional content matching the mockup designs. Each tab should be fully
interactive with forms, tables, search/filter, and API-driven diagnostics.

## Scope

### 5.1 Server Tab

**Template**: `templates/settings_server.html`

#### Connection Summary (Server variant)
- Proxy listener: `0.0.0.0:8080` (Admin/proxy port)
- Client base URL: `http://localhost:8080/v1` (Public endpoint for clients)
- Global upstream: `HF Router / Qwen 3.6 35B` (Used when no route matches) — highlighted
- Stored rows: `65` (X older than 30 days)

#### Proxy Listener Card
- Port input (number, 1–65535)
- "Expose on LAN / all interfaces" checkbox with helper text
- Warning text when enabled: "Network exposed. Use only on trusted networks."
- "Save listener settings" button (teal primary)
- POST to existing `/admin/settings/incoming`

#### Global Upstream Fallback Defaults Card
- Global upstream URL input (required)
- Default provider dropdown (populated from provider registry)
- Default model input (text, or dropdown if provider has pricing entries)
- Helper text: "When no route matches a request, the proxy will use {model} from {provider}..."
- "Save upstream defaults" button
- POST to `/admin/api/settings/upstream-defaults`

#### Compatibility Fixes Card
- Checkboxes for each known fix (from `compatibility_fix_rows()`)
  - Fix ID as label
  - Description text
- "Advanced manual edit (JSON)" collapsible section
- "Save fixes" button
- POST to existing `/admin/settings/compat-fixes`

#### Model Routes Summary Card
- Compact table: Incoming model, Route upstream URL, Send as model, Provider, API key env var, Compatibility fixes, Status, Actions
- "Showing X of Y routes" text
- "+ Add route" button linking to Routing tab
- Edit/Delete action icons per row

#### Test Route / Diagnostics Card
- Select route dropdown
- Test type dropdown (Simple message, Image message, Function call)
- Message textarea
- Route preview panel: Upstream URL, Send as model, Provider
- Result panel: Status badge, Duration, Response
- "Run test", "Image message", "Function call" buttons

#### Data Retention (Danger Zone) Card
- Red danger-zone styling
- "Retain for" days input
- "I understand this will permanently delete older records" checkbox
- "Trim records" button (disabled until checkbox checked)
- "Refresh count" button
- Preview count text

### 5.2 Providers Tab

**Template**: `templates/settings_providers.html`

#### Connection Summary (Providers variant)
- Active providers: `10` (Across all environments)
- Default provider: `Hugging Face Router` (Used for fallback) — highlighted
- Default model family: `Qwen 3.6 35B` (Used when no route matches)
- Stored rows: `65` (X older than 30 days)

#### Provider Registry Card
- Search input: "Search providers..."
- Status filter dropdown: All status
- Currency filter dropdown: All currencies
- "+ Add provider" button
- Table columns: Provider (with icon), Slug, Base URL, Currency, Status (badge), Models/Routes, Actions (edit/delete icons)
- Pagination with page numbers
- Row click selects provider and populates editor

#### Selected Provider Card
- Provider name input
- Slug input (read-only after creation)
- Base URL input
- Currency dropdown
- Authentication: API key env var input
- Default for fallback: toggle
- Supported capabilities: Text, Vision, Tool calling toggles/chips
- Info text when default: "When no route matches, the proxy can use this provider..."
- "Save provider" button (teal)
- "Test provider" button (outline)

#### Fallback Defaults Card
- Default provider dropdown
- Default model dropdown/input
- Resolution rule dropdown
- Info text explaining fallback behavior

#### Provider Health / Diagnostics Card
- "Run health checks" button
- Results table: Provider (with icon), Last check, Latency, Auth, Result (badge)
- Fetches from `/admin/api/providers/health-checks`

#### Recent Provider Usage Card
- Table: Provider, Requests today, Estimated cost, Active routes
- "View full usage analytics →" link
- Fetches from `/admin/api/providers/usage`

### 5.3 Routing Tab

**Template**: `templates/settings_routing.html`

#### Connection Summary (Routing variant)
- Active routes: `8` (Across all environments)
- Default provider: `Hugging Face Router` (Used for fallback) — highlighted
- Default model family: `Qwen 3.6 35B` (Used when no route matches)
- Stored rows: `65` (X older than 30 days)

#### Route Registry Card
- Search input: "Search routes..."
- Status filter dropdown: All status
- Provider filter dropdown: All providers
- "+ Add route" button
- Table columns: Incoming model, Match type, Route upstream URL, Send as model, Provider, Fallback, Status (badge), Actions (edit/delete)
- Pagination with page numbers
- Row click selects route and populates editor

#### Selected Route Card
- Incoming model input
- Match type dropdown (Exact match, Prefix match)
- Route upstream URL input
- Send as model input
- Provider dropdown
- API key env var input
- Compatibility fixes chips/tags
- Override fallback toggle
- Route priority dropdown/input (1–100)
- Enabled toggle
- Info text: "Requests with models matching {pattern} will be sent to {provider}..."
- "Save route" button (teal)
- "Test route" button (outline)

#### Fallback Routing Behavior Card
- Default provider dropdown
- Default model dropdown/input
- Resolution rule dropdown
- Info text explaining fallback behavior

#### Route Simulator / Diagnostics Card
- Incoming model to test input
- Message type dropdown
- "Run simulation" button
- Matched route preview panel: Matched route, Upstream URL, Send as model, Provider
- Result badge: Match found / No match, fallback / No match
- Fetches from `/admin/api/routes/simulate`

#### Recent Route Usage Card
- Table: Route, Requests today, Last matched
- "View full routing analytics →" link
- Fetches from `/admin/api/routes/usage`

### 5.4 Client-Side JavaScript

**File**: [app.js](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/static/app.js)

New JavaScript functionality:

- **Table row selection**: Click row → highlight + populate editor panel
- **Search/filter**: Client-side filtering of table rows (for small datasets) + server-side for large
- **Provider health checks**: Fetch API call, render results
- **Route simulator**: Fetch API call, render matched route preview
- **Collapsible sections**: Advanced manual edit, tier forms
- **Confirmation dialogs**: Delete confirmation before form submit
- **Form auto-submit prevention**: Disable buttons after click
- **Connection summary refresh**: Update summary cards after save operations
- **Checkbox-based compat fixes**: Collect checked IDs into hidden field

## Files Changed

| File | Change |
|---|---|
| `src/llm_observe_proxy/templates/settings_server.html` | Full Server tab content |
| `src/llm_observe_proxy/templates/settings_providers.html` | Full Providers tab content |
| `src/llm_observe_proxy/templates/settings_routing.html` | Full Routing tab content |
| `src/llm_observe_proxy/static/app.js` | Interactive features |
| `src/llm_observe_proxy/admin.py` | Tab route handlers with context data |
| `tests/test_admin_ui.py` | Tab-specific tests |

## Tests

Add to `tests/test_admin_ui.py`.

### Server Tab Tests

- `test_server_tab_shows_listener_form` — port input and expose checkbox present
- `test_server_tab_shows_upstream_form` — URL, provider dropdown, model input present
- `test_server_tab_shows_compat_fixes` — checkboxes for known fixes
- `test_server_tab_shows_routes_summary` — model routes table visible
- `test_server_tab_shows_test_form` — test route form with route dropdown
- `test_server_tab_shows_danger_zone` — trim form with confirmation checkbox
- `test_server_tab_save_listener` — POST updates listener settings
- `test_server_tab_save_upstream_defaults` — POST updates fallback settings
- `test_server_tab_save_compat_fixes_checkboxes` — checkbox form saves fix IDs
- `test_server_tab_trim_requires_confirmation` — trim fails without checkbox

### Provider Tab Tests

- `test_providers_tab_shows_registry` — provider table with all columns
- `test_providers_tab_shows_add_form` — add provider button/form present
- `test_providers_tab_shows_fallback_defaults` — fallback card present
- `test_providers_tab_create_provider` — POST creates provider
- `test_providers_tab_delete_provider` — DELETE removes provider
- `test_providers_tab_update_provider` — PUT modifies provider
- `test_providers_tab_health_checks_endpoint` — health check API works
- `test_providers_tab_usage_endpoint` — usage API returns data

### Routing Tab Tests

- `test_routing_tab_shows_registry` — route table with all columns
- `test_routing_tab_shows_add_form` — add route button/form present
- `test_routing_tab_shows_fallback_behavior` — fallback card present
- `test_routing_tab_shows_simulator` — simulator form present
- `test_routing_tab_create_route_exact` — POST creates exact route
- `test_routing_tab_create_route_prefix` — POST creates prefix route
- `test_routing_tab_delete_route` — DELETE removes route
- `test_routing_tab_update_route` — PUT modifies route
- `test_routing_tab_simulate_match` — simulator returns match result
- `test_routing_tab_simulate_fallback` — simulator returns fallback result
- `test_routing_tab_usage_endpoint` — usage API returns data

## Verification

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe tests/test_admin_ui.py -q
.\.venv\Scripts\pytest.exe -q  # full suite still passes
```

Manual visual verification:
- Start proxy with demo DB (seed_demo_db.py)
- Verify Server tab matches mockup layout
- Verify Providers tab matches mockup layout
- Verify Routing tab matches mockup layout
- Test interactive features: search, filter, selection, health checks, simulator
