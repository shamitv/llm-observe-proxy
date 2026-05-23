# Phase 1 — Data Model & Migrations — TODO

[← Phase 1 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## ModelProvider Expansion

- [ ] Add `api_key_env` column to `ModelProvider` (String(128), nullable)
- [ ] Add `active` column to `ModelProvider` (Boolean, default=True, index=True)
- [ ] Add `is_default_fallback` column to `ModelProvider` (Boolean, default=False)
- [ ] Add `capabilities_json` column to `ModelProvider` (Text, nullable)
- [ ] Write `_ensure_sqlite_model_provider_schema()` migration function
- [ ] Call migration from `init_db()`
- [ ] Update `upsert_model_provider()` to accept `api_key_env`, `active`, `is_default_fallback`, `capabilities`
- [ ] Add `get_default_fallback_provider()` helper
- [ ] Add `set_default_fallback_provider()` helper (clears other providers)
- [ ] Add `list_active_model_providers()` helper
- [ ] Update `DEFAULT_MODEL_PROVIDERS` seed with `api_key_env` values
- [ ] Add capabilities to seed data where known

## ModelRouteDB Table

- [ ] Define `ModelRouteDB` SQLAlchemy model class
- [ ] Add `incoming_model` column (String(256), indexed)
- [ ] Add `match_type` column (String(32), default="exact")
- [ ] Add `upstream_url` column (Text, required)
- [ ] Add `upstream_model` column (String(256), nullable)
- [ ] Add `provider_slug` column (String(64), nullable)
- [ ] Add `api_key_env` column (String(128), nullable)
- [ ] Add `compatibility_fixes_json` column (Text, nullable)
- [ ] Add `override_fallback` column (Boolean, default=False)
- [ ] Add `priority` column (Integer, default=50)
- [ ] Add `active` column (Boolean, default=True, indexed)
- [ ] Add `created_at` and `updated_at` columns
- [ ] Add unique constraint on `(incoming_model, match_type)`
- [ ] Add `VALID_MATCH_TYPES` constant to `config.py`

## Route CRUD Helpers

- [ ] Write `list_model_routes_db()` with active_only filter
- [ ] Write `get_model_route_db()` by ID
- [ ] Write `upsert_model_route_db()` with full validation
  - [ ] Validate `incoming_model` required
  - [ ] Validate `match_type` in VALID_MATCH_TYPES
  - [ ] Validate `upstream_url` via `normalize_upstream_url()`
  - [ ] Validate `priority` 1–100
  - [ ] Validate `provider_slug` if provided
  - [ ] Validate `compatibility_fixes_json` via `normalize_fix_ids()`
  - [ ] Enforce unique constraint on (incoming_model, match_type)
- [ ] Write `delete_model_route_db()` by ID

## Global Fallback Settings

- [ ] Add `get_default_provider_slug()` helper
- [ ] Add `set_default_provider_slug()` helper
- [ ] Add `get_default_model()` helper
- [ ] Add `set_default_model()` helper
- [ ] Add `is_fallback_enabled()` helper
- [ ] Add `get_fallback_summary()` helper (returns dict with provider name + model + URL)

## Migration from JSON Blob

- [ ] Write `_migrate_json_blob_routes()` function
- [ ] Parse existing `model_routes_json` from `app_settings`
- [ ] Insert routes into `ModelRouteDB` table
- [ ] Set `match_type="exact"`, `priority=50` for migrated routes
- [ ] Delete `model_routes_json` key after success
- [ ] Handle corrupt/empty JSON gracefully
- [ ] Call migration from `init_db()` after table creation
- [ ] Add logging for migration events

## Tests — `tests/test_database_models.py`

- [ ] `test_upsert_provider_with_new_fields`
- [ ] `test_upsert_provider_sets_active_default`
- [ ] `test_upsert_provider_capabilities_json_roundtrip`
- [ ] `test_set_default_fallback_provider_clears_others`
- [ ] `test_get_default_fallback_provider_returns_none_if_unset`
- [ ] `test_list_active_providers_excludes_inactive`
- [ ] `test_provider_migration_adds_missing_columns`
- [ ] `test_create_route_exact_match`
- [ ] `test_create_route_prefix_match`
- [ ] `test_create_route_invalid_match_type_raises`
- [ ] `test_create_route_priority_default`
- [ ] `test_create_route_priority_range_validation`
- [ ] `test_create_route_duplicate_pattern_raises`
- [ ] `test_update_route_preserves_id`
- [ ] `test_delete_route_returns_true`
- [ ] `test_delete_nonexistent_route_returns_false`
- [ ] `test_list_routes_active_only_filter`
- [ ] `test_list_routes_ordered_by_priority`
- [ ] `test_route_compatibility_fixes_roundtrip`
- [ ] `test_route_upstream_url_validation`
- [ ] `test_set_and_get_default_provider_slug`
- [ ] `test_set_and_get_default_model`
- [ ] `test_fallback_enabled_default_true`
- [ ] `test_get_fallback_summary_complete`
- [ ] `test_get_fallback_summary_when_unset`
- [ ] `test_migrate_json_blob_routes_to_table`
- [ ] `test_migrate_preserves_route_fields`
- [ ] `test_migrate_skipped_if_table_has_data`
- [ ] `test_migrate_removes_json_blob_after_success`
- [ ] `test_migrate_handles_empty_json_blob`
- [ ] `test_migrate_handles_corrupt_json_blob`

## Verification

- [ ] `ruff check src tests` passes
- [ ] `python -m compileall -q src tests` passes
- [ ] `pytest tests/test_database_models.py -q` passes
- [ ] `pytest -q` full suite passes (no regressions)
- [ ] Commit to `feature/v0.5-admin-ui` branch
