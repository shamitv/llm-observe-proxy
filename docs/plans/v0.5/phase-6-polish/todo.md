# Phase 6 — Polish & Remaining — TODO

[← Phase 6 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Pricing Tab

- [ ] Create `settings_pricing.html` extending `settings_base.html`
- [ ] Move pricing table HTML from old `settings.html`
- [ ] Add search input (provider, model, display name, alias)
- [ ] Add provider filter dropdown
- [ ] Add active status filter dropdown
- [ ] Add pagination
- [ ] Replace inline tier forms with collapsible drawers
- [ ] Add "Manage tiers" action button per row
- [ ] Tier drawer: list tiers + add tier form
- [ ] Wire to existing pricing POST endpoints
- [ ] Add pricing tab route handler in admin.py

## Diagnostics Tab

- [ ] Create `settings_diagnostics.html` extending `settings_base.html`
- [ ] Provider health overview table (read-only summary)
- [ ] "Run all health checks" button
- [ ] Route test form (select route, test type, message)
- [ ] Route simulator (incoming model, run simulation)
- [ ] Wire to health check and simulator APIs
- [ ] Add diagnostics tab route handler in admin.py

## Data Tab

- [ ] Create `settings_data.html` extending `settings_base.html`
- [ ] Storage stats section
  - [ ] Total stored rows
  - [ ] Database file size (if SQLite)
  - [ ] Oldest record date
  - [ ] Newest record date
- [ ] Data retention danger zone card
  - [ ] Retain days input
  - [ ] Confirmation checkbox
  - [ ] Trim records button (red, disabled until checked)
  - [ ] Refresh count button
  - [ ] Preview count
- [ ] Wire to trim endpoint
- [ ] Add data tab route handler in admin.py

## Confirmation Modals

- [ ] Create `templates/_confirm_modal.html` macro
  - [ ] Modal overlay
  - [ ] Modal card (title, message, actions)
  - [ ] Cancel button
  - [ ] Confirm button (danger or primary)
- [ ] Add modal CSS styles
  - [ ] Overlay (semi-transparent backdrop)
  - [ ] Modal card (centered, white, shadow)
  - [ ] Animation (fade in)
- [ ] Add modal JavaScript
  - [ ] Show modal function
  - [ ] Hide modal function
  - [ ] Focus trapping
  - [ ] Escape key to dismiss
  - [ ] Backdrop click to dismiss
  - [ ] Form submission on confirm
- [ ] Wire modals to destructive actions:
  - [ ] Delete provider
  - [ ] Delete route
  - [ ] Delete pricing entry
  - [ ] Delete pricing tier
  - [ ] Trim history

## Accessibility

- [ ] Add visible `<label>` for all inputs
- [ ] Add `aria-label` for icon-only buttons
- [ ] Add `scope="col"` to all `<th>` elements
- [ ] Ensure focus states are visible (outline/ring)
- [ ] Ensure tab order is logical
- [ ] Ensure Enter/Space activates all buttons
- [ ] Ensure modal focus trapping works
- [ ] Verify status badges have text (not color-only)
- [ ] Test with keyboard-only navigation

## Responsive Behavior

- [ ] Test at ≥1280px (desktop): full layout
- [ ] Test at 1024–1279px (laptop): sidebar visible, cards stack
- [ ] Test at 768–1023px (tablet): sidebar collapse, tables scroll
- [ ] Test at <768px (mobile): no sidebar, hamburger, full-width
- [ ] Fix horizontal overflow issues
- [ ] Fix form layout at narrow widths
- [ ] Fix table horizontal scroll

## Old Settings Page Cleanup

- [ ] Redirect `/admin/settings` to `/admin/settings/server`
- [ ] Keep old POST endpoints working (redirect to new tab URLs)
- [ ] Verify no broken links from Requests/Runs/Detail pages
- [ ] Remove or archive old `settings.html` template (or keep as legacy fallback)

## Documentation

- [ ] Update `README.md`
  - [ ] New Settings UI section with tab descriptions
  - [ ] Updated route list
  - [ ] Updated feature descriptions
- [ ] Update `README.pypi.md`
  - [ ] Align feature descriptions with README.md
  - [ ] No screenshots (PyPI rule)
- [ ] Update `docs/tests/README.md`
  - [ ] Add `test_database_models.py` to matrix
  - [ ] Add `test_route_engine.py` to matrix
  - [ ] Add `test_admin_api.py` to matrix
  - [ ] Update `test_admin_ui.py` entry

## Screenshot Regeneration

- [ ] Update `scripts/seed_demo_db.py`
  - [ ] Add routes with new fields (match_type, priority, active)
  - [ ] Add providers with new fields (api_key_env, active, capabilities)
  - [ ] Set default fallback provider
  - [ ] Set default model
- [ ] Update `scripts/capture_screenshots.py`
  - [ ] Update URLs for new tab structure
  - [ ] Capture Server tab
  - [ ] Capture Providers tab
  - [ ] Capture Routing tab
  - [ ] Capture Pricing tab
- [ ] Regenerate screenshots and commit to `docs/screenshots/`

## Tests — `tests/test_admin_ui.py`

### Pricing Tab
- [ ] `test_pricing_tab_renders`
- [ ] `test_pricing_tab_shows_pricing_table`
- [ ] `test_pricing_tab_create_price`
- [ ] `test_pricing_tab_delete_price`
- [ ] `test_pricing_tab_add_tier`
- [ ] `test_pricing_tab_delete_tier`

### Diagnostics Tab
- [ ] `test_diagnostics_tab_renders`
- [ ] `test_diagnostics_tab_shows_health_table`
- [ ] `test_diagnostics_tab_shows_test_form`

### Data Tab
- [ ] `test_data_tab_renders`
- [ ] `test_data_tab_shows_storage_stats`
- [ ] `test_data_tab_shows_retention_form`
- [ ] `test_data_tab_trim_works`

### Accessibility
- [ ] `test_all_inputs_have_labels`
- [ ] `test_buttons_have_text`
- [ ] `test_tables_have_scope_headers`
- [ ] `test_status_badges_have_text`

### Cleanup
- [ ] `test_old_settings_url_redirects`
- [ ] `test_old_post_endpoints_still_work`
- [ ] `test_no_broken_internal_links`

## Final Verification

- [ ] `ruff check src tests` passes
- [ ] `python -m compileall -q src tests` passes
- [ ] `pytest -q` full suite passes
- [ ] Release checks pass (`ruff check src tests scripts`, `compileall`, `publish --dry-run`)
- [ ] Manual visual check: all 6 tabs match mockup intent
- [ ] Manual test: confirmation modals work for all destructive actions
- [ ] Manual test: responsive behavior at all breakpoints
- [ ] Manual test: keyboard navigation works
- [ ] Screenshots regenerated and look correct
- [ ] README.md and README.pypi.md updated
- [ ] Final commit and merge to main
