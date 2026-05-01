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
| CLI | `python -m llm_observe_proxy --help` works and exposes upstream options. | `test_module_cli_help_smoke` |
| Non-streaming chat | `/v1/chat/completions` forwards to upstream and stores endpoint, model, status, request body, response body, and timing metadata. | `test_non_streaming_chat_completion_records_and_forwards_headers` |
| Header forwarding | Authorization and client request id headers are forwarded upstream. | `test_non_streaming_chat_completion_records_and_forwards_headers` |
| Responses reasoning | `/v1/responses` records a payload containing `reasoning` data and shows it in the UI JSON view. | `test_responses_reasoning_payload_is_recorded_and_visible_in_ui` |
| Chat streaming | Chat Completions SSE streams are proxied and raw `text/event-stream` bytes are stored. | `test_chat_streaming_captures_raw_sse` |
| Responses streaming tool call | Responses API streaming events containing a function call set `has_tool_calls` and render in tool mode. | `test_responses_streaming_tool_call_sets_tool_signal_and_ui_renderer` |
| Multiple images | One request with two images is captured: a data URL image and a remote image URL. Both are stored as image assets and shown in the UI. | `test_images_are_extracted_from_data_urls_and_remote_urls` |
| Non-streaming tool call | Chat Completions response with `tool_calls` sets `has_tool_calls` and renders as `chat.tool_call`. | `test_tool_calls_render_for_non_streaming_chat_response` |
| Generic passthrough | Generic `/v1/*` routes forward and log query strings. | `test_generic_v1_passthrough_records_query_string` |
| Admin browser | Request browser lists captured requests and supports a model filter. | `test_request_browser_filters_and_markdown_renderer` |
| Markdown rendering | Markdown responses render as HTML in detail view. | `test_request_browser_filters_and_markdown_renderer` |
| Upstream settings | Admin UI accepts a valid `/v1` upstream URL and later proxy calls use it. | `test_settings_updates_upstream_url` |
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
- Responses API `input_image` shapes beyond Chat Completions `image_url`.
- Pagination/date filtering in the admin request browser.
- Concurrent proxy requests.

## Adding New Tests

Prefer scenario-level tests that exercise the public routes:

- Use `proxy_client` for requests through the proxy and admin UI.
- Use `proxy_app.state.session_factory()` to assert stored SQLite records.
- Use `fake_upstream.last_request` to assert what was actually forwarded upstream.
- Add new fake upstream branches in `tests/conftest.py` only when a scenario needs a new
  upstream response shape.
