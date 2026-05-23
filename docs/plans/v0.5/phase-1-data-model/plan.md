# Phase 1 — Data Model & Migrations

[← Back to Master Plan](../implementation_plan.md)

## Goal

Establish the database schema that all subsequent phases depend on. Expand the `ModelProvider`
table, create a proper `ModelRouteDB` table replacing JSON blob storage, and add global
fallback settings to `app_settings`.

## Scope

### 1.1 Expand `ModelProvider` Table

**File**: [database.py](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/database.py#L1150-L1168)

Add columns to the existing `ModelProvider` model:

| Column | Type | Default | Notes |
|---|---|---|---|
| `api_key_env` | `String(128)`, nullable | `None` | Env var name for provider auth (e.g. `HF_TOKEN`) |
| `active` | `Boolean` | `True` | Enable/disable provider |
| `is_default_fallback` | `Boolean` | `False` | Mark as default fallback provider |
| `capabilities_json` | `Text`, nullable | `None` | JSON: `{"text": true, "vision": false, "tool_calling": true}` |

**Migration**: Add columns via `ALTER TABLE` in `_ensure_sqlite_model_provider_schema()`,
following the same pattern as [_ensure_sqlite_request_record_schema](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/database.py#L1735-L1800).

**CRUD updates**:
- Update [upsert_model_provider](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/database.py#L1380-L1417) to accept new fields
- Add `get_default_fallback_provider(session)` helper
- Add `set_default_fallback_provider(session, slug)` helper (clears other providers' flag)
- Add `list_active_model_providers(session)` helper

### 1.2 Create `ModelRouteDB` Table

**File**: [database.py](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/database.py)

New SQLAlchemy model replacing the JSON blob approach:

```python
class ModelRouteDB(Base):
    __tablename__ = "model_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incoming_model: Mapped[str] = mapped_column(String(256), index=True)
    match_type: Mapped[str] = mapped_column(String(32), default="exact")  # exact, prefix
    upstream_url: Mapped[str] = mapped_column(Text)
    upstream_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    api_key_env: Mapped[str | None] = mapped_column(String(128), nullable=True)
    compatibility_fixes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
```

**Unique constraint**: `UniqueConstraint("incoming_model", "match_type", name="uq_route_model_match")`

### 1.3 Route CRUD Helpers

New functions in `database.py`:

- `list_model_routes_db(session, *, active_only=False) -> list[ModelRouteDB]`
- `get_model_route_db(session, route_id) -> ModelRouteDB | None`
- `upsert_model_route_db(session, *, incoming_model, match_type, upstream_url, ...) -> ModelRouteDB`
- `delete_model_route_db(session, route_id) -> bool`

**Validation**:
- `incoming_model` required, stripped
- `match_type` must be `"exact"` or `"prefix"`
- `upstream_url` validated via `normalize_upstream_url()`
- `priority` must be 1–100 (default 50)
- `provider_slug` validated if provided
- `compatibility_fixes_json` validated via `normalize_fix_ids()`
- Unique constraint on `(incoming_model, match_type)` — no duplicate patterns

### 1.4 Global Fallback Settings

New setting keys stored in `app_settings` (KV table):

| Key | Example Value | Notes |
|---|---|---|
| `default_provider_slug` | `huggingface-router` | FK to `model_providers.slug` |
| `default_model` | `Qwen 3.6 35B` | Free text — model name |
| `fallback_enabled` | `true` | Boolean string |

New helpers:
- `get_default_provider_slug(session) -> str | None`
- `set_default_provider_slug(session, slug)`
- `get_default_model(session) -> str | None`
- `set_default_model(session, model)`
- `is_fallback_enabled(session) -> bool`
- `get_fallback_summary(session) -> dict` — returns provider name + model + URL for display

### 1.5 Migration from JSON Blob Routes

When `init_db` runs, if the old `model_routes_json` key exists in `app_settings` but
the `model_routes` table is empty:

1. Parse the JSON blob via `parse_model_routes()`
2. Insert each route into `ModelRouteDB` with `match_type="exact"`, `priority=50`
3. Preserve `upstream_url`, `upstream_model`, `provider_slug`, `api_key_env`, `fixes`
4. Delete the `model_routes_json` setting key after successful migration
5. Log a message indicating migration occurred

Startup config routes (`settings.model_routes`) should remain supported separately as
they are today — they do not get inserted into the DB table. The resolution engine (Phase 2)
will merge both sources.

### 1.6 Seed Data Updates

Update [DEFAULT_MODEL_PROVIDERS](file:///d:/work/opeanai_proxy/src/llm_observe_proxy/database.py#L89-L150) seed data
to include the new fields with sensible defaults:

- All providers: `active=True`
- All providers: `is_default_fallback=False` (user chooses)
- Providers with known API: `api_key_env` set (e.g. `openai` → `OPENAI_API_KEY`)
- Capabilities: set based on known provider features

## Files Changed

| File | Change |
|---|---|
| `src/llm_observe_proxy/database.py` | `ModelProvider` expansion, `ModelRouteDB` model, CRUD helpers, migration, seed updates |
| `src/llm_observe_proxy/config.py` | Add `VALID_MATCH_TYPES` constant |
| `tests/test_database_models.py` | New test file for Phase 1 |

## Tests

All tests go in `tests/test_database_models.py` (new file).

### ModelProvider Tests

- `test_upsert_provider_with_new_fields` — create with `api_key_env`, `active`, `capabilities_json`
- `test_upsert_provider_sets_active_default` — active defaults to True
- `test_upsert_provider_capabilities_json_roundtrip` — JSON stored and retrieved correctly
- `test_set_default_fallback_provider_clears_others` — only one provider is default
- `test_get_default_fallback_provider_returns_none_if_unset`
- `test_list_active_providers_excludes_inactive`
- `test_provider_migration_adds_missing_columns` — simulate old DB without new columns

### ModelRouteDB Tests

- `test_create_route_exact_match` — basic create with match_type=exact
- `test_create_route_prefix_match` — basic create with match_type=prefix
- `test_create_route_invalid_match_type_raises` — only exact/prefix allowed
- `test_create_route_priority_default` — defaults to 50
- `test_create_route_priority_range_validation` — 1–100 enforced
- `test_create_route_duplicate_pattern_raises` — unique constraint on (incoming_model, match_type)
- `test_update_route_preserves_id` — upsert by ID
- `test_delete_route_returns_true`
- `test_delete_nonexistent_route_returns_false`
- `test_list_routes_active_only_filter`
- `test_list_routes_ordered_by_priority` — lower priority first
- `test_route_compatibility_fixes_roundtrip` — JSON stored, parsed back to tuple
- `test_route_upstream_url_validation` — must end in /v1

### Global Fallback Tests

- `test_set_and_get_default_provider_slug`
- `test_set_and_get_default_model`
- `test_fallback_enabled_default_true`
- `test_get_fallback_summary_complete` — returns provider name, model, URL
- `test_get_fallback_summary_when_unset` — returns None/empty values gracefully

### Migration Tests

- `test_migrate_json_blob_routes_to_table` — existing JSON blob converted to DB rows
- `test_migrate_preserves_route_fields` — all fields transferred correctly
- `test_migrate_skipped_if_table_has_data` — idempotent
- `test_migrate_removes_json_blob_after_success`
- `test_migrate_handles_empty_json_blob`
- `test_migrate_handles_corrupt_json_blob` — no crash, logs warning

## Verification

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe tests/test_database_models.py -q
.\.venv\Scripts\pytest.exe -q  # full suite still passes
```
