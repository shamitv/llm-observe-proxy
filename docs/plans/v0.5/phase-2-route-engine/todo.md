# Phase 2 — Route Resolution Engine — TODO

[← Phase 2 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## RoutingDecision Expansion

- [ ] Add `route_db` field to `RoutingDecision` (ModelRouteDB or None)
- [ ] Add `match_type` field ("exact" / "prefix" / None)
- [ ] Add `match_source` field ("startup" / "db" / "fallback" / "none")
- [ ] Add `fallback_used` field (bool)
- [ ] Add `fallback_provider_slug` field
- [ ] Add `fallback_model` field
- [ ] Update all existing properties to work with both `route` and `route_db`

## ResolvedRoute Intermediate Type

- [ ] Create `ResolvedRoute` dataclass that normalizes `ModelRoute` + `ModelRouteDB`
- [ ] Include fields: incoming_model, match_type, upstream_url, upstream_model, provider_slug, api_key_env, fixes, priority, active, source
- [ ] Write `_startup_route_to_resolved()` converter
- [ ] Write `_db_route_to_resolved()` converter

## Unified Route Loading

- [ ] Write `get_resolved_routes(session, settings)` function
- [ ] Load startup routes as priority=0, match_type="exact"
- [ ] Load DB routes with their stored priority and match_type
- [ ] Return sorted list (by priority, then match type, then specificity)

## Match Functions

- [ ] Write `_matches_exact(pattern, model)` helper
- [ ] Write `_matches_prefix(pattern, model)` helper
  - [ ] Handle `*` suffix stripping
  - [ ] Handle edge case: empty suffix after stripping
- [ ] Write `_match_route(route, model)` dispatcher by match_type

## Priority Sorting

- [ ] Write `_route_sort_key(route)` function
  - [ ] Primary: priority (ascending — lower number = higher priority)
  - [ ] Secondary: match_type ("exact" before "prefix")
  - [ ] Tertiary: pattern length (longer = more specific, desc)
  - [ ] Quaternary: stable tiebreaker (creation order / id)
- [ ] Apply sort to matching routes before returning best match

## Rewrite `select_model_route()`

- [ ] Accept session parameter for DB access
- [ ] Load resolved routes from startup + DB
- [ ] Filter to active routes only
- [ ] Match incoming model against all routes
- [ ] Sort matches by priority key
- [ ] Return best match as RoutingDecision
- [ ] If no match, proceed to fallback chain

## Fallback Chain

- [ ] Check `is_fallback_enabled(session)` from Phase 1 helpers
- [ ] Load `default_provider_slug` and `default_model`
- [ ] Resolve provider's `upstream_url` from ModelProvider table
- [ ] Load default compatibility fixes
- [ ] Return RoutingDecision with `fallback_used=True`
- [ ] If fallback not configured, return `match_source="none"`

## Route Simulator

- [ ] Define `RouteSimulationResult` dataclass
  - [ ] Fields: status, matched_route, match_type, upstream_url, upstream_model, provider_slug, provider_name, api_key_state, compatibility_fixes
- [ ] Write `simulate_route_resolution()` function
  - [ ] Use same resolution logic as `select_model_route()`
  - [ ] Detect and report API key state
  - [ ] Report provider name (not just slug)
  - [ ] No HTTP calls — pure resolution

## Proxy Integration Updates

- [ ] Update `proxy.py` to pass session to route resolution
- [ ] Use fallback fields when no route matches
- [ ] Apply default compat fixes on fallback
- [ ] Apply fallback upstream_url from provider

## Admin Integration Updates

- [ ] Update `test_upstream` in admin.py to use new resolution
- [ ] Update route display to include match_type information

## Backward Compatibility

- [ ] Verify startup config routes work unchanged
- [ ] Verify existing exact-match behavior preserved
- [ ] Ensure `get_effective_model_routes()` still works for callers

## Tests — `tests/test_route_engine.py`

### Exact Match
- [ ] `test_exact_match_single_route`
- [ ] `test_exact_match_no_match_returns_none`
- [ ] `test_exact_match_case_sensitive`
- [ ] `test_exact_match_from_startup_config`

### Prefix Match
- [ ] `test_prefix_match_simple`
- [ ] `test_prefix_match_star_required`
- [ ] `test_prefix_match_does_not_match_shorter`
- [ ] `test_prefix_match_empty_suffix_matches`
- [ ] `test_prefix_match_no_partial_word`

### Priority & Ordering
- [ ] `test_higher_priority_wins`
- [ ] `test_exact_beats_prefix_at_same_priority`
- [ ] `test_longer_prefix_beats_shorter`
- [ ] `test_stable_tiebreaker_by_id`
- [ ] `test_startup_routes_highest_priority`

### Active/Inactive
- [ ] `test_inactive_route_skipped`
- [ ] `test_all_routes_inactive_falls_to_fallback`
- [ ] `test_mixed_active_inactive_routes`

### Fallback Chain
- [ ] `test_fallback_used_when_no_match`
- [ ] `test_fallback_with_provider_url`
- [ ] `test_fallback_disabled_returns_no_match`
- [ ] `test_fallback_provider_not_found_returns_no_match`
- [ ] `test_fallback_model_used_in_decision`
- [ ] `test_default_compat_fixes_applied_on_fallback`

### Route Simulator
- [ ] `test_simulate_exact_match_found`
- [ ] `test_simulate_prefix_match_found`
- [ ] `test_simulate_fallback_result`
- [ ] `test_simulate_no_match_no_fallback`
- [ ] `test_simulate_disabled_route_skipped`
- [ ] `test_simulate_missing_api_key_detected`
- [ ] `test_simulate_returns_provider_name`
- [ ] `test_simulate_returns_compatibility_fixes`

### Integration
- [ ] `test_proxy_uses_prefix_route`
- [ ] `test_proxy_uses_fallback_when_no_match`
- [ ] `test_existing_proxy_tests_still_pass`

## Verification

- [ ] `ruff check src tests` passes
- [ ] `python -m compileall -q src tests` passes
- [ ] `pytest tests/test_route_engine.py -q` passes
- [ ] `pytest -q` full suite passes (no regressions)
- [ ] Commit to `feature/v0.5-admin-ui` branch
