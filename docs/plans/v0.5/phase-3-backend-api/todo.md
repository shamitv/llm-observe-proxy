# Phase 3 — Backend API — TODO

[← Phase 3 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Settings API

- [ ] `GET /admin/api/settings/summary` endpoint
  - [ ] Return listener host + port
  - [ ] Return client_base_url
  - [ ] Return upstream URL + default provider + default model
  - [ ] Return stored_rows count
  - [ ] Return active_routes count
  - [ ] Return active_providers count
  - [ ] Return retention_days + rows_older_than_retention
- [ ] `POST /admin/api/settings/listener` endpoint
  - [ ] Accept port + expose_all_ips
  - [ ] Validate port range 1–65535
  - [ ] Call `set_incoming_server()`
- [ ] `POST /admin/api/settings/upstream-defaults` endpoint
  - [ ] Accept upstream_url + default_provider_slug + default_model
  - [ ] Validate upstream_url
  - [ ] Validate provider_slug exists if provided
  - [ ] Save all three settings
- [ ] `POST /admin/api/settings/compat-fixes` endpoint
  - [ ] Accept fix IDs (list or newline-separated)
  - [ ] Validate via `normalize_fix_ids()`
  - [ ] Save via `set_default_compat_fixes()`
- [ ] `GET /admin/api/settings/retention-preview` endpoint
  - [ ] Accept `days` query parameter
  - [ ] Return count of records older than cutoff
- [ ] `POST /admin/api/settings/trim` endpoint
  - [ ] Require `confirm=true` in request body
  - [ ] Delete records older than cutoff
  - [ ] Return deleted count

## Provider API

- [ ] `GET /admin/api/providers` endpoint
  - [ ] Query all providers
  - [ ] Implement search filter (name, slug, URL substring)
  - [ ] Implement status filter (active/inactive/all)
  - [ ] Implement currency filter
  - [ ] Implement pagination (page, per_page)
  - [ ] Include model count and route count per provider
- [ ] `POST /admin/api/providers` endpoint
  - [ ] Accept slug, name, upstream_url, currency, api_key_env, active, capabilities
  - [ ] Validate via `upsert_model_provider()`
  - [ ] Return created provider
- [ ] `GET /admin/api/providers/{slug}` endpoint
  - [ ] Return single provider with all fields
  - [ ] Return 404 if not found
- [ ] `PUT /admin/api/providers/{slug}` endpoint
  - [ ] Accept updated fields
  - [ ] Validate and save
  - [ ] Return updated provider
- [ ] `DELETE /admin/api/providers/{slug}` endpoint
  - [ ] Delete provider and cascade to prices
  - [ ] Return 404 if not found
  - [ ] Return confirmation with impact count (routes, prices affected)

## Provider Diagnostics API

- [ ] `POST /admin/api/providers/{slug}/test` endpoint
  - [ ] Resolve provider's base URL
  - [ ] Resolve API key from api_key_env
  - [ ] Send lightweight request (GET /models or similar)
  - [ ] Measure latency
  - [ ] Determine auth_state (valid / missing_key / invalid)
  - [ ] Return health result JSON
  - [ ] Handle connection errors gracefully
  - [ ] Timeout after 10 seconds
- [ ] `POST /admin/api/providers/health-checks` endpoint
  - [ ] Iterate all active providers
  - [ ] Run health check on each
  - [ ] Return array of results
  - [ ] Store results on app.state for caching

## Provider Usage API

- [ ] `GET /admin/api/providers/usage` endpoint
  - [ ] Write `get_provider_usage_summary()` in database.py
  - [ ] Aggregate requests_today from RequestRecord (billing_provider_slug)
  - [ ] Aggregate estimated_cost from billing_total_cost_usd
  - [ ] Count active routes per provider from ModelRouteDB
  - [ ] Return array of usage summaries

## Route API

- [ ] `GET /admin/api/routes` endpoint
  - [ ] Query all DB routes
  - [ ] Implement search filter (incoming_model, upstream_url, provider, upstream_model)
  - [ ] Implement status filter (active/inactive/all)
  - [ ] Implement provider filter
  - [ ] Implement pagination (page, per_page)
- [ ] `POST /admin/api/routes` endpoint
  - [ ] Accept incoming_model, match_type, upstream_url, etc.
  - [ ] Validate via `upsert_model_route_db()`
  - [ ] Return created route
- [ ] `GET /admin/api/routes/{id}` endpoint
  - [ ] Return single route with all fields
  - [ ] Return 404 if not found
- [ ] `PUT /admin/api/routes/{id}` endpoint
  - [ ] Accept updated fields
  - [ ] Validate and save
  - [ ] Return updated route
- [ ] `DELETE /admin/api/routes/{id}` endpoint
  - [ ] Delete route
  - [ ] Return 404 if not found

## Route Simulation API

- [ ] `POST /admin/api/routes/simulate` endpoint
  - [ ] Accept incoming_model and message_type
  - [ ] Call `simulate_route_resolution()` from Phase 2
  - [ ] Return simulation result JSON
  - [ ] Include matched_route, match_type, upstream info, provider info, api_key_state

## Route Test API

- [ ] `POST /admin/api/routes/{id}/test` endpoint
  - [ ] Load route by ID
  - [ ] Build test payload (simple/image/tools)
  - [ ] Send to route's upstream_url
  - [ ] Return status, duration, response summary

## Route Usage API

- [ ] `GET /admin/api/routes/usage` endpoint
  - [ ] Write `get_route_usage_summary()` in database.py
  - [ ] Aggregate requests_today from RequestRecord (model_route)
  - [ ] Get last_matched_at per route
  - [ ] Return array of usage summaries

## Tests — `tests/test_admin_api.py`

### Settings
- [ ] `test_get_settings_summary`
- [ ] `test_update_listener_valid`
- [ ] `test_update_listener_invalid_port`
- [ ] `test_update_upstream_defaults_valid`
- [ ] `test_update_upstream_defaults_invalid_url`
- [ ] `test_update_compat_fixes_valid`
- [ ] `test_update_compat_fixes_unknown_id`
- [ ] `test_retention_preview`
- [ ] `test_trim_requires_confirmation`
- [ ] `test_trim_deletes_old_records`

### Providers
- [ ] `test_list_providers`
- [ ] `test_list_providers_search_filter`
- [ ] `test_list_providers_status_filter`
- [ ] `test_create_provider`
- [ ] `test_create_provider_duplicate_slug`
- [ ] `test_get_provider`
- [ ] `test_get_provider_not_found`
- [ ] `test_update_provider`
- [ ] `test_delete_provider`
- [ ] `test_delete_provider_not_found`
- [ ] `test_test_provider_healthy`
- [ ] `test_test_provider_unhealthy`
- [ ] `test_health_checks_all_providers`
- [ ] `test_provider_usage_summary`

### Routes
- [ ] `test_list_routes`
- [ ] `test_list_routes_search_filter`
- [ ] `test_list_routes_status_filter`
- [ ] `test_create_route_exact`
- [ ] `test_create_route_prefix`
- [ ] `test_create_route_invalid_match_type`
- [ ] `test_get_route`
- [ ] `test_get_route_not_found`
- [ ] `test_update_route`
- [ ] `test_delete_route`
- [ ] `test_simulate_route_match`
- [ ] `test_simulate_route_fallback`
- [ ] `test_simulate_route_no_match`
- [ ] `test_test_route_sends_request`
- [ ] `test_route_usage_summary`

## Verification

- [ ] `ruff check src tests` passes
- [ ] `python -m compileall -q src tests` passes
- [ ] `pytest tests/test_admin_api.py -q` passes
- [ ] `pytest -q` full suite passes (no regressions)
- [ ] Commit to `feature/v0.5-admin-ui` branch
