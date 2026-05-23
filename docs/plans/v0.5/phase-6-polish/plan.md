# Phase 6 — Polish & Remaining

[← Back to Master Plan](../implementation_plan.md)

## Goal

Complete the remaining tabs (Pricing, Diagnostics, Data), add confirmation modals,
audit accessibility, test responsive behavior, update documentation, and prepare
for release.

## Scope

### 6.1 Pricing Tab

**Template**: `templates/settings_pricing.html`

Move existing pricing UI from old settings page into a dedicated tab.

#### Content
- Connection summary with pricing-specific cards
- Searchable pricing registry table
  - Columns: Provider, Model, Display name, Input/1M, Cached Input/1M, Output/1M, Aliases, Tiers, Active, Actions
- Search by provider, model, display name, alias
- Filter by provider and active status
- Tier management via expandable drawer per row (not inline forms)
- Add new price form
- Add new tier form (within drawer)

#### Changes from current settings page
- Extract pricing table HTML from `settings.html` into `settings_pricing.html`
- Replace inline tier forms with collapsible drawers or modal
- Add search and filter controls
- Add pagination
- Preserve all existing POST endpoints

### 6.2 Diagnostics Tab

**Template**: `templates/settings_diagnostics.html`

Consolidated view of testing and health across providers and routes.

#### Content
- Provider health overview table (from providers tab, read-only)
- "Run all health checks" button
- Route test form (simplified version of server tab test form)
- Route simulator (simplified version of routing tab simulator)
- Recent test results log (last 10 test-upstream calls if logged)

### 6.3 Data Tab

**Template**: `templates/settings_data.html`

Data management and retention.

#### Content
- Storage stats:
  - Total stored rows
  - Database file size (if SQLite)
  - Oldest record date
  - Newest record date
- Data retention card (moved from server tab danger zone):
  - Retain days input
  - Confirmation checkbox
  - Trim records button (danger)
  - Refresh count button
  - Preview count
- Export options (future — placeholder for now)

### 6.4 Confirmation Modals

**New file**: `templates/_confirm_modal.html` (Jinja macro)

Reusable confirmation modal component:

```html
{% macro confirm_modal(id, title, message, confirm_text="Delete", danger=true) %}
<div class="modal-overlay" id="{{ id }}" hidden>
  <div class="modal">
    <h3>{{ title }}</h3>
    <p>{{ message }}</p>
    <div class="modal-actions">
      <button class="button ghost" data-dismiss-modal>Cancel</button>
      <button class="button {{ 'danger' if danger else 'primary' }}" data-confirm-modal>{{ confirm_text }}</button>
    </div>
  </div>
</div>
{% endmacro %}
```

**Operations requiring confirmation** (per requirements §6.3):
- Delete provider → "Delete provider {name}? This may affect X routes and Y pricing entries."
- Delete route → "Delete route {pattern}? This route currently receives traffic."
- Delete pricing entry → "Delete pricing for {provider}/{model}?"
- Delete pricing tier → "Delete tier {label} for {model}?"
- Trim history → "Delete X records older than Y days? This cannot be undone."

**JavaScript additions to `app.js`**:
- Modal show/hide logic
- Focus trapping within modal
- Escape key to dismiss
- Backdrop click to dismiss
- Form submission on confirm

### 6.5 Accessibility Audit

Per requirements §16:

- [ ] All interactive controls keyboard accessible (tab order, Enter/Space activation)
- [ ] Inputs have visible `<label>` elements (not just placeholder text)
- [ ] Buttons have discernible text (no icon-only buttons without aria-label)
- [ ] Status colors accompanied by text labels (badges already have text)
- [ ] Focus states visible (outline or ring on focus)
- [ ] Tables use `<th scope="col">` for headers
- [ ] Confirmation modals trap focus while open
- [ ] Color alone not relied upon for state indication

### 6.6 Responsive Behavior Testing

- Desktop (≥1280px): Full sidebar, multi-column dashboard, all tables visible
- Laptop (1024–1279px): Sidebar visible, cards may stack to 2 columns
- Tablet (768–1023px): Sidebar collapsible, cards stack, tables scroll horizontally
- Mobile (<768px): No sidebar, full-width content, hamburger menu, tables scroll

### 6.7 Old Settings Page Cleanup

- Remove or redirect old `/admin/settings` combined page
- Ensure no broken links from existing pages
- Keep old POST endpoints working (they redirect to new tab URLs)

### 6.8 Documentation Updates

- Update `README.md`:
  - New Settings UI section with tab descriptions
  - Updated screenshots (after regeneration)
  - Updated route list (/admin/settings/server, etc.)
- Update `README.pypi.md`:
  - Align features and route descriptions
  - No screenshots (per AGENTS.md rule)
- Update `docs/tests/README.md`:
  - Add new test files to coverage matrix
- Regenerate screenshots:
  - Update `scripts/seed_demo_db.py` with v0.5 data (routes, providers with new fields)
  - Update `scripts/capture_screenshots.py` for new tab URLs

## Files Changed

| File | Change |
|---|---|
| `src/llm_observe_proxy/templates/settings_pricing.html` | Full Pricing tab content |
| `src/llm_observe_proxy/templates/settings_diagnostics.html` | Full Diagnostics tab content |
| `src/llm_observe_proxy/templates/settings_data.html` | Full Data tab content |
| `src/llm_observe_proxy/templates/_confirm_modal.html` | **New** — modal macro |
| `src/llm_observe_proxy/static/styles.css` | Modal styles, responsive tweaks |
| `src/llm_observe_proxy/static/app.js` | Modal logic, focus trapping |
| `src/llm_observe_proxy/admin.py` | Tab handlers for pricing, diagnostics, data |
| `src/llm_observe_proxy/templates/settings.html` | Remove or redirect |
| `README.md` | Updated Settings UI docs |
| `README.pypi.md` | Updated feature descriptions |
| `docs/tests/README.md` | Updated test coverage map |
| `scripts/seed_demo_db.py` | Updated demo data |
| `scripts/capture_screenshots.py` | Updated screenshot URLs |
| `tests/test_admin_ui.py` | Additional tests |

## Tests

Add to `tests/test_admin_ui.py`.

### Pricing Tab Tests

- `test_pricing_tab_renders` — returns 200
- `test_pricing_tab_shows_pricing_table` — table with expected columns
- `test_pricing_tab_create_price` — POST creates price entry
- `test_pricing_tab_delete_price` — POST deletes price entry
- `test_pricing_tab_add_tier` — POST adds tier to price
- `test_pricing_tab_delete_tier` — POST deletes tier

### Diagnostics Tab Tests

- `test_diagnostics_tab_renders` — returns 200
- `test_diagnostics_tab_shows_health_table` — health table present
- `test_diagnostics_tab_shows_test_form` — test form present

### Data Tab Tests

- `test_data_tab_renders` — returns 200
- `test_data_tab_shows_storage_stats` — stats section present
- `test_data_tab_shows_retention_form` — retention form present
- `test_data_tab_trim_works` — trim endpoint works from data tab

### Accessibility Tests

- `test_all_inputs_have_labels` — no orphaned inputs
- `test_buttons_have_text` — no empty buttons
- `test_tables_have_scope_headers` — th elements have scope
- `test_status_badges_have_text` — badges not color-only

### Redirect/Cleanup Tests

- `test_old_settings_url_redirects` — `/admin/settings` → `/admin/settings/server`
- `test_old_post_endpoints_still_work` — existing POST routes return redirects
- `test_no_broken_internal_links` — all href/action values resolve

## Verification

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe -q  # full suite passes
```

Release checks:
```powershell
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe scripts\publish_pypi.py --dry-run
```

Manual verification:
- Visual comparison of all 6 tabs against mockups
- Test confirmation modals for all destructive actions
- Test responsive behavior at all breakpoints
- Test keyboard navigation through all interactive elements
- Regenerate and verify screenshots
