# Phase 3 — Backend API

[← Back to Master Plan](../implementation_plan.md)

## Goal

Expose structured JSON API endpoints for provider CRUD, route CRUD, health checks,
usage aggregation, route simulation, and settings management. These APIs serve the
new tabbed UI (Phase 5) and can also be used by external tools.

## Scope

### 3.1 API Route Prefix

All new API endpoints go under `/admin/api/` to separate them from the existing
HTML-rendering admin routes. Existing HTML routes remain unchanged for backward
compatibility during migration.

```
/admin/api/settings/...      — settings summary and updates
/admin/api/providers/...     — provider CRUD + diagnostics
/admin/api/routes/...        — route CRUD + simulation
```

### 3.2 Settings API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/api/settings/summary` | Connection summary for all tabs |
| `POST` | `/admin/api/settings/listener` | Update port + expose-all-ips |
| `POST` | `/admin/api/settings/upstream-defaults` | Update upstream URL + default provider + default model |
| `POST` | `/admin/api/settings/compat-fixes` | Update default compatibility fixes |
| `GET` | `/admin/api/settings/retention-preview` | Preview trim count for given days |
| `POST` | `/admin/api/settings/trim` | Execute trim with confirmation |

#### GET `/admin/api/settings/summary`

Returns JSON used by the Connection Summary strip across all tabs:

```json
{
  "listener": { "host": "0.0.0.0", "port": 8080 },
  "client_base_url": "http://localhost:8080/v1",
  "upstream": {
    "url": "http://localhost:8000/v1",
    "default_provider_slug": "huggingface-router",
    "default_provider_name": "Hugging Face Router",
    "default_model": "Qwen 3.6 35B"
  },
  "stored_rows": 65,
  "active_routes": 8,
  "active_providers": 10,
  "retention_days": 30,
  "rows_older_than_retention": 0
}
```

### 3.3 Provider API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/api/providers` | List providers (with search, filter, pagination) |
| `POST` | `/admin/api/providers` | Create provider |
| `GET` | `/admin/api/providers/{slug}` | Get single provider |
| `PUT` | `/admin/api/providers/{slug}` | Update provider |
| `DELETE` | `/admin/api/providers/{slug}` | Delete provider |
| `POST` | `/admin/api/providers/{slug}/test` | Test provider connectivity |
| `POST` | `/admin/api/providers/health-checks` | Run health checks on all active providers |
| `GET` | `/admin/api/providers/usage` | Provider usage summary |

#### GET `/admin/api/providers` Query Parameters

- `search` — filter by name, slug, or base URL (substring match)
- `status` — `active`, `inactive`, or `all` (default: `all`)
- `currency` — filter by currency code
- `page` / `per_page` — pagination

#### POST `/admin/api/providers/{slug}/test`

Sends a minimal request (e.g. `/models` or tiny chat completion) to the provider's
base URL and returns:

```json
{
  "provider_slug": "huggingface-router",
  "status": "healthy",
  "latency_ms": 420,
  "auth_state": "valid",
  "message": "OK"
}
```

#### POST `/admin/api/providers/health-checks`

Runs health checks on all active providers in sequence. Returns array of results:

```json
[
  { "provider_slug": "huggingface-router", "latency_ms": 420, "auth_state": "valid", "status": "healthy" },
  { "provider_slug": "anthropic", "latency_ms": null, "auth_state": "missing_key", "status": "warning" }
]
```

**Implementation notes**:
- Use lightweight endpoint per provider (e.g. `GET /models` or `GET /` on base URL)
- Resolve API key from provider's `api_key_env`
- Timeout: 10 seconds per provider
- Do not make expensive inference calls
- Store results transiently (in-memory dict on `app.state` or lightweight table)

#### GET `/admin/api/providers/usage`

Aggregate from `RequestRecord` using `billing_provider_slug`:

```json
[
  {
    "provider_slug": "huggingface-router",
    "provider_name": "Hugging Face Router",
    "requests_today": 4512,
    "estimated_cost_usd": 12.48,
    "active_routes": 3
  }
]
```

### 3.4 Route API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/api/routes` | List routes (with search, filter, pagination) |
| `POST` | `/admin/api/routes` | Create route |
| `GET` | `/admin/api/routes/{id}` | Get single route |
| `PUT` | `/admin/api/routes/{id}` | Update route |
| `DELETE` | `/admin/api/routes/{id}` | Delete route |
| `POST` | `/admin/api/routes/simulate` | Simulate route resolution |
| `POST` | `/admin/api/routes/{id}/test` | Test route (send actual request) |
| `GET` | `/admin/api/routes/usage` | Route usage summary |

#### GET `/admin/api/routes` Query Parameters

- `search` — filter by incoming_model, upstream_url, upstream_model, provider
- `status` — `active`, `inactive`, or `all`
- `provider` — filter by provider_slug
- `page` / `per_page` — pagination

#### POST `/admin/api/routes/simulate`

Request body:

```json
{
  "incoming_model": "qwen-chat",
  "message_type": "simple"
}
```

Response (uses `simulate_route_resolution()` from Phase 2):

```json
{
  "status": "matched",
  "matched_route": "qwen-*",
  "match_type": "prefix",
  "upstream_url": "https://router.huggingface.co/v1",
  "upstream_model": "Qwen 3.6 35B",
  "provider_slug": "huggingface-router",
  "provider_name": "Hugging Face Router",
  "api_key_state": "configured",
  "compatibility_fixes": ["qwen-tagged-tool-call-rewrite", "strip-reasoning-tags"]
}
```

#### GET `/admin/api/routes/usage`

Aggregate from `RequestRecord` using `model_route`:

```json
[
  { "route": "qwen-*", "requests_today": 3104, "last_matched_at": "2026-05-23T12:00:00Z" },
  { "route": "gpt-*", "requests_today": 1882, "last_matched_at": "2026-05-23T12:01:00Z" }
]
```

### 3.5 Usage Aggregation Queries

New functions in `database.py`:

```python
def get_provider_usage_summary(session: Session) -> list[dict]:
    """Aggregate today's requests, costs, active route count per provider."""

def get_route_usage_summary(session: Session) -> list[dict]:
    """Aggregate today's requests, last matched time per route pattern."""
```

These query `RequestRecord` filtering by `created_at >= today_start` and grouping by
`billing_provider_slug` or `model_route`.

## Files Changed

| File | Change |
|---|---|
| `src/llm_observe_proxy/admin.py` | New API routes under `/admin/api/` |
| `src/llm_observe_proxy/database.py` | Usage aggregation queries, health check result storage |
| `tests/test_admin_api.py` | New test file for Phase 3 |

## Tests

All tests go in `tests/test_admin_api.py` (new file).

### Settings API Tests

- `test_get_settings_summary` — returns complete summary JSON
- `test_update_listener_valid` — port and expose flag saved
- `test_update_listener_invalid_port` — rejects out-of-range port
- `test_update_upstream_defaults_valid` — saves URL + provider + model
- `test_update_upstream_defaults_invalid_url` — rejects bad URL
- `test_update_compat_fixes_valid` — saves fix IDs
- `test_update_compat_fixes_unknown_id` — rejects unknown fix
- `test_retention_preview` — returns correct count
- `test_trim_requires_confirmation` — rejects without confirm flag
- `test_trim_deletes_old_records` — actually deletes

### Provider API Tests

- `test_list_providers` — returns paginated list
- `test_list_providers_search_filter` — name/slug/url substring
- `test_list_providers_status_filter` — active/inactive
- `test_create_provider` — valid provider created
- `test_create_provider_duplicate_slug` — conflict error
- `test_get_provider` — returns single provider
- `test_get_provider_not_found` — 404
- `test_update_provider` — modifies fields
- `test_delete_provider` — removes from DB
- `test_delete_provider_not_found` — 404
- `test_test_provider_healthy` — returns health result (mock upstream)
- `test_test_provider_unhealthy` — handles connection error
- `test_health_checks_all_providers` — runs checks on multiple providers
- `test_provider_usage_summary` — aggregates from request records

### Route API Tests

- `test_list_routes` — returns paginated list
- `test_list_routes_search_filter` — filters by incoming_model, provider
- `test_list_routes_status_filter` — active/inactive
- `test_create_route_exact` — valid exact route created
- `test_create_route_prefix` — valid prefix route created
- `test_create_route_invalid_match_type` — rejects bad match type
- `test_get_route` — returns single route
- `test_get_route_not_found` — 404
- `test_update_route` — modifies fields
- `test_delete_route` — removes from DB
- `test_simulate_route_match` — returns matched route
- `test_simulate_route_fallback` — returns fallback when no match
- `test_simulate_route_no_match` — returns no_match status
- `test_test_route_sends_request` — actually hits upstream (mock)
- `test_route_usage_summary` — aggregates from request records

## Verification

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe tests/test_admin_api.py -q
.\.venv\Scripts\pytest.exe -q  # full suite still passes
```
