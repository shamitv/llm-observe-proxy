# Phase 2 — Route Resolution Engine

[← Back to Master Plan](../implementation_plan.md)

## Goal

Replace the current exact-match-only router with a full resolution engine that supports
prefix matching, priority-based ordering, deterministic tie-breaking, and a fallback chain.
Also implement a route simulator function that resolves without making HTTP calls.

## Scope

### 2.1 Rewrite `select_model_route()`

**File**: [routing.py](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/routing.py#L39-L52)

The current implementation does a simple exact-match loop:

```python
for route in routes:
    if route.model == requested_model:
        return RoutingDecision(requested_model=requested_model, route=route)
```

**New implementation** must:

1. Accept both `ModelRoute` (startup config) and `ModelRouteDB` (DB table) routes
2. Filter to active routes only
3. For each route, check if the incoming model matches:
   - **Exact**: `route.incoming_model == requested_model`
   - **Prefix**: `requested_model.startswith(route.incoming_model.rstrip("*"))`
     where the pattern uses `*` as wildcard suffix (e.g. `qwen-*` matches `qwen-chat`)
4. Sort matching routes deterministically:
   - Higher priority first (lower number = higher priority)
   - Exact match before prefix match at same priority
   - Longer/more-specific prefix pattern before shorter pattern at same priority
   - Stable tie-breaker (creation order / DB id)
5. Return the best match wrapped in an updated `RoutingDecision`

### 2.2 Update `RoutingDecision` Dataclass

**File**: [routing.py](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/routing.py#L13-L37)

Expand to include resolution metadata:

```python
@dataclass(frozen=True)
class RoutingDecision:
    requested_model: str | None
    route: ModelRoute | None = None
    route_db: ModelRouteDB | None = None  # DB route if matched from table
    match_type: str | None = None         # "exact" / "prefix" / None
    match_source: str = "none"            # "startup" / "db" / "fallback" / "none"
    fallback_used: bool = False
    fallback_provider_slug: str | None = None
    fallback_model: str | None = None
```

### 2.3 Fallback Chain

When no route matches, the engine must:

1. Check if fallback is enabled (`is_fallback_enabled(session)`)
2. If enabled, load `default_provider_slug` and `default_model` from settings
3. Resolve the provider's `upstream_url` from `ModelProvider`
4. Return a `RoutingDecision` with `fallback_used=True` and fallback fields populated
5. If no fallback configured, return a decision with `match_source="none"`

The caller (proxy and test-upstream) uses the decision to determine whether to proceed
or return a configuration error.

### 2.4 Unified Route Source

Create a function to merge startup routes + DB routes into a single sorted list:

```python
def get_resolved_routes(
    session: Session,
    settings: Settings,
) -> list[ResolvedRoute]:
    """Merge startup config routes and DB routes into a priority-sorted list."""
```

Where `ResolvedRoute` is a normalized intermediate type that unifies `ModelRoute` and
`ModelRouteDB` fields.

### 2.5 Route Simulator Function

Create a function for dry-run route resolution (no HTTP call):

```python
def simulate_route_resolution(
    incoming_model: str,
    session: Session,
    settings: Settings,
) -> RouteSimulationResult:
    """Predict which route/fallback will be used for an incoming model name."""
```

Returns:

```python
@dataclass(frozen=True)
class RouteSimulationResult:
    status: str  # "matched", "fallback", "no_match", "route_disabled", "missing_api_key"
    matched_route: str | None         # incoming_model pattern
    match_type: str | None            # "exact" / "prefix"
    upstream_url: str | None
    upstream_model: str | None
    provider_slug: str | None
    provider_name: str | None
    api_key_state: str | None         # "configured" / "missing" / "not_configured"
    compatibility_fixes: tuple[str, ...]
```

### 2.6 Update Proxy Integration

Update [proxy.py](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/proxy.py) to use the
new resolution engine:

- Pass `session` to `select_model_route()` for DB route access
- Use fallback fields from `RoutingDecision` when no route matches
- Apply fallback `upstream_url`, `default_model` from decision
- Apply default compatibility fixes when using fallback

### 2.7 Backward Compatibility

- Startup config routes (`settings.model_routes`) continue to work exactly as before
- Startup routes are treated as `match_type="exact"`, `priority=0` (highest priority)
- Existing tests must continue to pass without modification

## Files Changed

| File | Change |
|---|---|
| `src/llm_observe_proxy/routing.py` | Major rewrite: match types, priority sort, fallback chain, simulator |
| `src/llm_observe_proxy/proxy.py` | Update to use new RoutingDecision fields |
| `src/llm_observe_proxy/admin.py` | Update test_upstream to use new resolution |
| `tests/test_route_engine.py` | New test file for Phase 2 |

## Tests

All tests go in `tests/test_route_engine.py` (new file).

### Exact Match Tests

- `test_exact_match_single_route` — basic exact match works
- `test_exact_match_no_match_returns_none` — unmatched model
- `test_exact_match_case_sensitive` — "Qwen" ≠ "qwen"
- `test_exact_match_from_startup_config` — startup routes still work

### Prefix Match Tests

- `test_prefix_match_simple` — `qwen-*` matches `qwen-chat`
- `test_prefix_match_star_required` — pattern must end with `*` for prefix
- `test_prefix_match_does_not_match_shorter` — `qwen-chat` does not match `qwen-chat-pro-*`
- `test_prefix_match_empty_suffix_matches` — `qwen-*` matches `qwen-` (edge case)
- `test_prefix_match_no_partial_word` — `gpt-*` matches `gpt-4` but behavior with `gpt` alone is defined

### Priority & Ordering Tests

- `test_higher_priority_wins` — priority=10 beats priority=50
- `test_exact_beats_prefix_at_same_priority` — exact match wins tie
- `test_longer_prefix_beats_shorter` — `qwen-chat-*` beats `qwen-*` at same priority
- `test_stable_tiebreaker_by_id` — DB id used as final tiebreaker
- `test_startup_routes_highest_priority` — startup config routes priority=0

### Active/Inactive Tests

- `test_inactive_route_skipped` — active=False routes not matched
- `test_all_routes_inactive_falls_to_fallback`
- `test_mixed_active_inactive_routes`

### Fallback Chain Tests

- `test_fallback_used_when_no_match` — fallback_used=True, correct provider/model
- `test_fallback_with_provider_url` — upstream_url from provider
- `test_fallback_disabled_returns_no_match`
- `test_fallback_provider_not_found_returns_no_match`
- `test_fallback_model_used_in_decision`
- `test_default_compat_fixes_applied_on_fallback`

### Route Simulator Tests

- `test_simulate_exact_match_found`
- `test_simulate_prefix_match_found`
- `test_simulate_fallback_result`
- `test_simulate_no_match_no_fallback`
- `test_simulate_disabled_route_skipped`
- `test_simulate_missing_api_key_detected`
- `test_simulate_returns_provider_name`
- `test_simulate_returns_compatibility_fixes`

### Integration Tests

- `test_proxy_uses_prefix_route` — end-to-end prefix routing through proxy
- `test_proxy_uses_fallback_when_no_match` — fallback applied in proxy
- `test_existing_proxy_tests_still_pass` — backward compatibility

## Verification

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe tests/test_route_engine.py -q
.\.venv\Scripts\pytest.exe -q  # full suite still passes
```
