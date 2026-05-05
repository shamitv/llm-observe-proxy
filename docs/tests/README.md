# Test Suite

The test suite verifies the proxy, SQLite capture layer, admin UI, renderers, and CLI.
Tests run with pytest and use a fake OpenAI-compatible upstream on `localhost:8080/v1`.

## Run Tests

```powershell
.\.venv\Scripts\pytest.exe -q
```

Optional checks:

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
```

The fake upstream requires port `8080` to be free. If another service is using that port,
the test session fails early with a clear message.

## Test Harness

- `tests/conftest.py` starts a session-scoped FastAPI upstream on `127.0.0.1:8080`.
- Each test gets a fresh SQLite database in pytest's temporary directory.
- Proxy tests point the app at `http://localhost:8080/v1`, matching the product plan.
- The upstream records received requests so tests can verify forwarded headers, paths, query
  strings, and bodies.

## Covered Scenarios

| Area | Scenario | Test |
| --- | --- | --- |
| Package/app | App factory exposes `/healthz`. | `test_app_factory_exposes_health_route` |
| CLI | `python -m llm_observe_proxy --help` works and exposes incoming bind and upstream options. | `test_module_cli_help_smoke` |
| CLI bind settings | CLI startup resolves saved incoming host/port settings when explicit bind args are omitted. | `test_cli_resolve_bind_uses_saved_incoming_settings` |
| Model route config | JSON/env/file model route configuration is parsed, normalized, and validated, including optional provider slugs. | `test_model_routes_parse_from_json_env`, `test_model_routes_file_wins_over_json_env`, `test_model_routes_reject_invalid_configuration` |
| Pricing seed data | SQLite initialization seeds editable provider/model pricing and does not overwrite existing edits. | `test_init_db_seeds_model_pricing_without_overwriting_edits` |
| Cost estimator | Cost estimation handles split input/output rates, aliases, unknown models, and missing usage. | `test_cost_estimator_handles_rates_aliases_unknowns_and_missing_usage` |
| Run what-if cost estimator | Run what-if estimates sum exact token usage, split input/output costs, and count requests with missing usage. | `test_run_cost_estimator_sums_usage_and_counts_missing_requests` |
| Routing helpers | Exact model selection rewrites forwarded JSON bodies and applies route-aware authorization policy. | `test_routing_selects_exact_model_and_rewrites_body`, `test_route_api_key_resolution_and_header_policy` |
| Non-streaming chat | `/v1/chat/completions` forwards to upstream and stores endpoint, model, status, request body, response body, and timing metadata. | `test_non_streaming_chat_completion_records_and_forwards_headers` |
| Header forwarding | Authorization and client request id headers are forwarded upstream. | `test_non_streaming_chat_completion_records_and_forwards_headers` |
| Cost snapshots | Non-streaming requests snapshot provider, billing model, usage tokens, rate snapshot, and total estimated cost. | `test_non_streaming_chat_completion_snapshots_estimated_cost` |
| Model route proxying | Configured and UI-managed model routes select their upstream, rewrite the forwarded model, inject route keys, preserve original captured bodies, and record route metadata. | `test_configured_model_route_rewrites_injects_key_and_records_metadata`, `test_ui_model_route_rewrites_injects_key_and_records_metadata` |
| Model route auth | Routes without keys preserve client authorization; routes with missing `api_key_env` drop client authorization. | `test_configured_model_route_without_key_preserves_client_authorization`, `test_configured_model_route_with_missing_key_env_drops_client_authorization` |
| Model route fallback | Unknown, missing, and non-JSON models use the global upstream fallback. | `test_unknown_missing_and_non_json_models_use_global_fallback` |
| Model route streaming | Streaming requests use configured routes and still capture raw SSE plus route metadata. | `test_streaming_request_uses_configured_model_route_and_captures_metadata` |
| Responses reasoning | `/v1/responses` records a payload containing `reasoning` data and shows it in the UI JSON view. | `test_responses_reasoning_payload_is_recorded_and_visible_in_ui` |
| Chat streaming | Chat Completions SSE streams are proxied and raw `text/event-stream` bytes are stored. | `test_chat_streaming_captures_raw_sse` |
| Streaming cost snapshots | Streaming requests with a final usage event snapshot estimated cost. | `test_streaming_request_snapshots_cost_when_usage_event_is_present` |
| Responses streaming tool call | Responses API streaming events containing a function call set `has_tool_calls` and render in tool mode. | `test_responses_streaming_tool_call_sets_tool_signal_and_ui_renderer` |
| Multiple images | One request with two images is captured: a data URL image and a remote image URL. Both are stored as image assets and shown in the UI. | `test_images_are_extracted_from_data_urls_and_remote_urls` |
| Non-streaming tool call | Chat Completions response with `tool_calls` sets `has_tool_calls` and renders as `chat.tool_call`. | `test_tool_calls_render_for_non_streaming_chat_response` |
| Generic passthrough | Generic `/v1/*` routes forward and log query strings. | `test_generic_v1_passthrough_records_query_string` |
| Admin browser | Request browser lists captured requests, token counts, and request TPS, and supports a model filter. | `test_request_browser_filters_and_markdown_renderer` |
| Markdown rendering | Markdown responses render as HTML in detail view. | `test_request_browser_filters_and_markdown_renderer` |
| Run lifecycle | Runs require names, show active state, end active runs, and auto-end the previous run when starting another. | `test_runs_require_name_and_manage_active_state` |
| Run request grouping | Requests made during an active run receive `task_run_id`; requests outside a run do not. | `test_requests_are_associated_with_active_task_run` |
| Run streaming grouping | A streaming request keeps the run assigned at request start even if the run ends before the stream finishes. | `test_streaming_request_keeps_task_run_after_run_ends` |
| Run filtering and detail | Request browser filters by run, run detail shows associated requests and aggregate token/cost stats, and request detail links back to the run. | `test_run_filter_detail_and_badges_show_associated_requests` |
| Run what-if pricing UI | Run detail shows default GPT-5.5/GPT-5.4 Mini comparisons, accepts repeated `what_if` params, ignores unknown/inactive prices, and preserves captured snapshots. | `test_run_detail_shows_default_what_if_costs_without_mutating_snapshots`, `test_run_detail_accepts_repeated_what_if_params`, `test_run_detail_ignores_unknown_and_inactive_what_if_prices` |
| SQLite run upgrade | Existing SQLite databases get the nullable `task_run_id` column and index without data loss. | `test_init_db_upgrades_existing_sqlite_request_records_with_route_metadata` |
| SQLite route upgrade | Existing SQLite databases get nullable route metadata columns and indexes without data loss. | `test_init_db_upgrades_existing_sqlite_request_records_with_route_metadata` |
| SQLite cost upgrade | Existing SQLite databases get nullable cost snapshot columns and indexes without data loss. | `test_init_db_upgrades_existing_sqlite_request_records_with_route_metadata` |
| Upstream settings | Admin UI accepts a valid `/v1` upstream URL and later proxy calls use it. | `test_settings_updates_upstream_url` |
| Model route settings | Settings renders startup routes read-only, manages UI routes, persists UI routes, validates route input, displays providers, and masks direct secret values. | `test_settings_renders_model_routes_without_secret_values`, `test_settings_manages_ui_model_routes`, `test_settings_validates_ui_model_routes_against_startup_config`, `test_ui_model_routes_persist_across_app_restart` |
| Provider and pricing settings | Settings renders seeded providers/prices and can add, validate, update, and delete provider and model price rows. | `test_settings_manages_model_providers_and_prices` |
| Route-aware upstream test | Admin upstream test uses startup/UI routes for matching models and global fallback for unknown models. | `test_settings_test_upstream_uses_configured_model_route`, `test_settings_test_upstream_uses_ui_model_route`, `test_settings_test_upstream_falls_back_for_unknown_model` |
| Route metadata UI | Request browser/detail pages show route and upstream-model metadata for routed requests. | `test_request_browser_and_detail_show_route_metadata` |
| Incoming settings | Admin UI shows `localhost:8080` by default and stores custom incoming port plus the `0.0.0.0` expose option. | `test_settings_updates_incoming_server` |
| Incoming validation | Admin UI rejects incoming ports outside `1..65535`. | `test_settings_rejects_invalid_incoming_port` |
| Upstream validation | Admin UI rejects invalid upstream URLs that do not point to `/v1`. | `test_settings_rejects_invalid_upstream_url` |
| Trim old records | Admin trim deletes rows older than `N` days. | `test_trim_deletes_records_older_than_requested_days` |
| Image cascade delete | Trimming an old request also deletes its stored image assets. | `test_trim_deletes_records_older_than_requested_days` |
| Renderer detection | Auto-rendering detects JSON, Markdown, tool calls, and SSE. | `test_renderer_modes_for_json_text_markdown_tool_and_sse` |

## Current Gaps

These behaviors are not explicitly covered yet:

- Multiple tool calls in the same response.
- Tool response messages such as `role: "tool"` with `tool_call_id`.
- Multiple conversation messages across user, assistant, and tool history.
- Streamed tool-call deltas that must be reconstructed across multiple chunks.
- Upstream non-200 error response logging.
- Upstream connection failure and timeout logging.
- Multi-upstream `/v1/models` synthesis or merging.
- Responses API `input_image` shapes beyond Chat Completions `image_url`.
- Pagination/date filtering in the admin request browser.
- Non-token cost components such as cache tiers, batch/flex/priority discounts, image/audio
  prices, tool fees, and regional or long-context premiums.
- Concurrent proxy requests.

## Adding New Tests

Prefer scenario-level tests that exercise the public routes:

- Use `proxy_client` for requests through the proxy and admin UI.
- Use `proxy_app.state.session_factory()` to assert stored SQLite records.
- Use `fake_upstream.last_request` to assert what was actually forwarded upstream.
- Add new fake upstream branches in `tests/conftest.py` only when a scenario needs a new
  upstream response shape.
