# Phase 4 — UI Foundation

[← Back to Master Plan](../implementation_plan.md)

## Goal

Build the app shell, CSS design system, and shared UI components that all tabs will use.
At the end of this phase, the Settings area should render with the new sidebar + tabs
layout showing placeholder content for each tab. No functional tab content yet.

## Reference Mockups

All three mockups share the same shell:
- Top header: logo, product name, main nav (Requests, Runs, **Settings**, Health), user avatar
- Left sidebar: Settings sub-nav (Server, Routing, Providers, Pricing, Diagnostics, Data)
- Environment card at sidebar bottom
- Connection Summary strip at top of content area
- Tab bar below connection summary (secondary nav)

## Scope

### 4.1 CSS Design System

**File**: [styles.css](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/static/styles.css)

Major redesign of the CSS. Key design tokens:

```css
/* Color palette — teal/green primary */
--color-primary: #0d9488;        /* teal-600 */
--color-primary-light: #14b8a6;  /* teal-500 */
--color-primary-dark: #0f766e;   /* teal-700 */
--color-primary-bg: #f0fdfa;     /* teal-50 */
--color-primary-border: #99f6e4; /* teal-200 */

/* Semantic colors */
--color-success: #16a34a;
--color-warning: #d97706;
--color-danger: #dc2626;
--color-info: #2563eb;

/* Surface colors */
--color-bg: #f8fafc;
--color-surface: #ffffff;
--color-border: #e2e8f0;
--color-text: #1e293b;
--color-text-muted: #64748b;

/* Shadows */
--shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
--shadow-card: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);

/* Spacing */
--radius: 8px;
--radius-lg: 12px;
```

**New component styles**:
- `.app-shell` — full-page grid layout
- `.sidebar` — left sidebar with nav items
- `.sidebar-nav-item` — nav link with icon + text + active state
- `.sidebar-env-card` — bottom environment card
- `.main-content` — right content area
- `.connection-summary` — top strip with summary cards
- `.summary-card` — individual card (icon, label, value, helper)
- `.tab-bar` — secondary tab row
- `.tab-item` — tab link with icon + active state
- `.card` — white card with shadow and rounded corners
- `.card-header` — card title row
- `.status-badge` — colored badge (active, inactive, healthy, warning, error)
- `.form-field` — label + input pair
- `.danger-zone` — red bordered card for destructive actions
- `.search-bar` — search input with icon
- `.filter-row` — row of filter dropdowns
- `.data-table` — styled table with zebra rows
- `.pagination` — page navigation
- `.button-primary`, `.button-danger`, `.button-ghost` — button variants

### 4.2 Base Template Redesign

**File**: [base.html](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/templates/base.html)

Redesign to support two layouts:
1. **Standard layout** — for Requests, Runs, etc. (no sidebar)
2. **Settings layout** — with sidebar (extends base)

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ page_title }} - LLM Observe Proxy</title>
  <link rel="stylesheet" href="{{ url_for('admin_static', path='/styles.css') }}">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/admin">
      <span class="brand-icon">U</span>
      <span class="brand-text">LLM Observe Proxy</span>
    </a>
    <nav class="main-nav">
      <a href="/admin" class="{{ 'active' if active_nav == 'requests' }}">Requests</a>
      <a href="/admin/runs" class="{{ 'active' if active_nav == 'runs' }}">Runs</a>
      <a href="/admin/settings" class="{{ 'active' if active_nav == 'settings' }}">Settings</a>
      <a href="/healthz" class="{{ 'active' if active_nav == 'health' }}">Health</a>
    </nav>
    <div class="user-avatar">S</div>
  </header>
  <div class="app-shell">
    {% block app_body %}
    <main class="page">
      {% block content %}{% endblock %}
    </main>
    {% endblock %}
  </div>
  <script src="{{ url_for('admin_static', path='/app.js') }}"></script>
</body>
</html>
```

### 4.3 Settings Base Template

**New file**: `templates/settings_base.html`

Extends `base.html`, overrides `app_body` to add sidebar:

```html
{% extends "base.html" %}
{% block app_body %}
<aside class="sidebar">
  <div class="sidebar-header">Settings</div>
  <nav class="sidebar-nav">
    <a href="/admin/settings/server" class="sidebar-nav-item {{ 'active' if settings_tab == 'server' }}">
      <span class="icon">⚙</span> Server
    </a>
    <a href="/admin/settings/routing" class="sidebar-nav-item {{ 'active' if settings_tab == 'routing' }}">
      <span class="icon">↗</span> Routing
    </a>
    <!-- ... Providers, Pricing, Diagnostics, Data -->
  </nav>
  <div class="sidebar-env-card">
    <div>Environment: Local Development</div>
    <div>Version: {{ app_version | default('v1.0.0') }}</div>
  </div>
</aside>
<main class="settings-content">
  {% block connection_summary %}
  <section class="connection-summary">
    {% block summary_cards %}{% endblock %}
  </section>
  {% endblock %}
  <div class="tab-bar">
    {% block tab_bar %}{% endblock %}
  </div>
  {% block settings_content %}{% endblock %}
</main>
{% endblock %}
```

### 4.4 Connection Summary Component

**New file**: `templates/_connection_summary.html` (Jinja macro or include)

Reusable summary card component:

```html
{% macro summary_card(icon, label, value, helper="", highlighted=false) %}
<div class="summary-card {{ 'highlighted' if highlighted }}">
  <div class="summary-icon">{{ icon }}</div>
  <div class="summary-body">
    <span class="summary-label">{{ label }}</span>
    <span class="summary-value">{{ value }}</span>
    <span class="summary-helper">{{ helper }}</span>
  </div>
</div>
{% endmacro %}
```

### 4.5 Status Badge Component

```html
{% macro status_badge(status) %}
<span class="status-badge status-{{ status | lower }}">{{ status }}</span>
{% endmacro %}
```

Supported statuses: `Active`, `Inactive`, `Healthy`, `Warning`, `Error`, `Missing key`,
`Valid`, `Success`.

### 4.6 Tab Skeleton Templates

Create placeholder templates for each settings tab:

- `templates/settings_server.html`
- `templates/settings_routing.html`
- `templates/settings_providers.html`
- `templates/settings_pricing.html`
- `templates/settings_diagnostics.html`
- `templates/settings_data.html`

Each extends `settings_base.html` and shows placeholder content:

```html
{% extends "settings_base.html" %}
{% block summary_cards %}
  {{ summary_card("🖥", "Proxy listener", "0.0.0.0:8080", "Admin/proxy port") }}
  <!-- etc -->
{% endblock %}
{% block settings_content %}
<div class="card">
  <div class="card-header"><h2>Server</h2></div>
  <p>Server tab content coming in Phase 5.</p>
</div>
{% endblock %}
```

### 4.7 Settings Tab Routes

**File**: [admin.py](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/admin.py)

Add routes for each tab:

```python
@router.get("/settings/server", response_class=HTMLResponse)
@router.get("/settings/routing", response_class=HTMLResponse)
@router.get("/settings/providers", response_class=HTMLResponse)
@router.get("/settings/pricing", response_class=HTMLResponse)
@router.get("/settings/diagnostics", response_class=HTMLResponse)
@router.get("/settings/data", response_class=HTMLResponse)
```

The existing `/admin/settings` route should redirect to `/admin/settings/server`.

### 4.8 Responsive Sidebar

CSS rules for sidebar behavior:
- **Desktop (≥1024px)**: Fixed sidebar, content takes remaining width
- **Tablet (768–1023px)**: Collapsible sidebar, toggle button
- **Mobile (<768px)**: Sidebar hidden, full-width content, hamburger menu

### 4.9 Preserve Existing Pages

The existing Requests, Runs, and Detail pages must continue to work unchanged.
They use `base.html` directly (no sidebar) and should not be affected.

## Files Changed

| File | Change |
|---|---|
| `src/llm_observe_proxy/static/styles.css` | Major redesign — new design system |
| `src/llm_observe_proxy/templates/base.html` | New app shell with nav highlighting |
| `src/llm_observe_proxy/templates/settings_base.html` | **New** — sidebar + tab layout |
| `src/llm_observe_proxy/templates/_connection_summary.html` | **New** — summary card macro |
| `src/llm_observe_proxy/templates/_status_badge.html` | **New** — badge macro |
| `src/llm_observe_proxy/templates/settings_server.html` | **New** — skeleton |
| `src/llm_observe_proxy/templates/settings_routing.html` | **New** — skeleton |
| `src/llm_observe_proxy/templates/settings_providers.html` | **New** — skeleton |
| `src/llm_observe_proxy/templates/settings_pricing.html` | **New** — skeleton |
| `src/llm_observe_proxy/templates/settings_diagnostics.html` | **New** — skeleton |
| `src/llm_observe_proxy/templates/settings_data.html` | **New** — skeleton |
| `src/llm_observe_proxy/admin.py` | Tab routes + redirect |

## Tests

Add to `tests/test_admin_ui.py` (existing file).

### Shell & Navigation Tests

- `test_settings_redirects_to_server_tab` — `/admin/settings` → `/admin/settings/server`
- `test_server_tab_renders` — `/admin/settings/server` returns 200
- `test_routing_tab_renders` — `/admin/settings/routing` returns 200
- `test_providers_tab_renders` — `/admin/settings/providers` returns 200
- `test_pricing_tab_renders` — `/admin/settings/pricing` returns 200
- `test_diagnostics_tab_renders` — `/admin/settings/diagnostics` returns 200
- `test_data_tab_renders` — `/admin/settings/data` returns 200
- `test_sidebar_shows_all_tabs` — sidebar contains all 6 nav items
- `test_active_tab_highlighted` — correct sidebar item has active class
- `test_connection_summary_present` — summary strip renders on all tabs
- `test_existing_requests_page_unchanged` — `/admin` still works
- `test_existing_runs_page_unchanged` — `/admin/runs` still works
- `test_existing_detail_page_unchanged` — `/admin/requests/1` still works

## Verification

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe tests/test_admin_ui.py -q
.\.venv\Scripts\pytest.exe -q  # full suite still passes
```

Manual visual verification:
- Start proxy: `.\.venv\Scripts\llm-observe-proxy.exe`
- Open `http://localhost:8080/admin/settings`
- Verify sidebar renders with all tabs
- Verify each tab link loads correctly
- Verify Connection Summary strip is visible
- Verify Requests and Runs pages are unchanged
