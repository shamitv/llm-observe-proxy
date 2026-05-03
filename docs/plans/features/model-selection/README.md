# Model Selection Feature Plan

## Goal

Allow multiple proxy-facing model names to be configured, each with its own upstream
base URL, optional injected API key, and optional upstream model name. When a request
arrives, the proxy should select the configured upstream from the request model before
forwarding it.

If the request has no model, or it uses a model that is not configured, the request falls
back to the existing global upstream configuration.

The proxy remains record-only: every request is forwarded to an upstream, and the
request/response pair is captured in SQLite.

## Example workflow

1. User configures these routes:
   - `local-qwen` -> `http://localhost:8000/v1`, upstream model `qwen3-coder-30b`
   - `openai-mini` -> `https://api.openai.com/v1`, upstream model `gpt-4.1-mini`
2. User sends an OpenAI-compatible request to the proxy:
   `{"model": "local-qwen", "messages": [...]}`
3. The proxy routes the request to `http://localhost:8000/v1/chat/completions`.
4. Before forwarding, the proxy rewrites the forwarded JSON model to
   `qwen3-coder-30b`.
5. If the route has an API key, the proxy injects `Authorization: Bearer <key>` for the
   upstream request.
6. The admin UI records the client-facing model, selected upstream URL, and upstream
   model used. It must not expose the injected API key.

## Configuration

Add a `ModelRoute` configuration object.

```text
model_routes
- model string
- upstream_url string
- upstream_model string nullable
- api_key string nullable
- api_key_env string nullable
```

Field behavior:

- `model`: the client-facing model name used for selection, matched exactly against the
  request payload's top-level `model`.
- `upstream_url`: the upstream `/v1` base URL for this model route.
- `upstream_model`: the model value sent to upstream. Defaults to `model` when omitted.
- `api_key_env`: environment variable name containing the upstream API key.
- `api_key`: direct API key value for local/dev use. Prefer `api_key_env` in docs and
  examples.

Recommended environment shape:

```json
[
  {
    "model": "local-qwen",
    "upstream_url": "http://localhost:8000/v1",
    "upstream_model": "qwen3-coder-30b"
  },
  {
    "model": "openai-mini",
    "upstream_url": "https://api.openai.com/v1",
    "upstream_model": "gpt-4.1-mini",
    "api_key_env": "OPENAI_API_KEY"
  }
]
```

Initial config inputs:

- `LLM_OBSERVE_MODELS_JSON`: JSON array of route objects.
- `LLM_OBSERVE_MODELS_FILE`: path to a JSON file with the same shape.
- CLI follow-up option: `--models-file`, which sets `LLM_OBSERVE_MODELS_FILE`.

Validation rules:

- Reject duplicate `model` values.
- Require absolute `http` or `https` upstream URLs ending in `/v1`.
- Reject routes that define both `api_key` and `api_key_env`.
- Treat missing or empty `upstream_model` as the client-facing `model`.
- Never log API key values.

## Routing behavior

For each request handled by `ANY /v1/{path:path}`:

1. Read the request body as the proxy does today.
2. Extract the requested model with the existing `extract_model()` helper.
3. Look up a configured `ModelRoute` by exact model name.
4. If a route exists:
   - use `route.upstream_url` as the upstream base;
   - build the final upstream URL from the request path and query string;
   - if the request body is a JSON object, forward a copy with `model` replaced by
     `route.upstream_model`;
   - inject `Authorization: Bearer <route api key>` when a key is configured.
5. If no route exists:
   - use `get_upstream_url(session, settings)` as today;
   - forward the original request body and headers as today.

Fallback cases:

- Unknown `model`: global upstream.
- Missing `model`: global upstream.
- Non-JSON body: global upstream unless a future endpoint-specific selector can identify
  a model safely.
- `GET /v1/models` and other generic requests without a body: global upstream for the
  initial version.

Header behavior:

- Continue dropping hop-by-hop headers.
- Preserve client headers by default.
- For configured routes with an API key, override the outgoing `Authorization` header.
- Do not store the injected authorization header in `RequestRecord.request_headers_json`;
  that field should continue to represent the client request.

Body behavior:

- Store the original client request body in SQLite.
- Forward a separate body when the model name must be rewritten.
- Keep stream detection based on the original client request payload.
- Preserve SSE streaming capture exactly as today after the routing decision is made.

## Data model

Keep `RequestRecord.model` as the client-facing requested model.

Add nullable routing metadata:

```text
request_records.upstream_model string nullable indexed
request_records.model_route string nullable indexed
```

Meanings:

- `upstream_model`: model value sent to upstream after route mapping.
- `model_route`: matched configured route name. Null means the global fallback was used.

Existing `request_records.upstream_url` already stores the final upstream endpoint URL.

Compatibility note: add a small SQLite schema upgrade during `init_db()` to create the
new nullable columns and indexes for existing databases, following the current
`task_run_id` upgrade pattern.

## Backend changes

### `config.py`

- Add `ModelRoute` dataclass.
- Add `model_routes: tuple[ModelRoute, ...]` to `Settings`.
- Add parsing helpers for `LLM_OBSERVE_MODELS_JSON` and `LLM_OBSERVE_MODELS_FILE`.
- Reuse upstream URL validation behavior from admin settings or move shared validation
  to a small common helper to avoid drift.

### New `routing.py`

- Add a small routing module so selection logic is testable outside FastAPI.
- Suggested types/functions:
  - `RoutingDecision`
  - `select_model_route(request_payload, settings)`
  - `build_forward_body(request_body, request_payload, decision)`
  - `build_forward_headers(headers, decision)`
- Keep the module free of database sessions. Global fallback URL resolution can still
  happen in `proxy.py` because the persisted global upstream lives in `app_settings`.

### `proxy.py`

- Replace the single `get_upstream_url()` lookup with model-route selection.
- Resolve global fallback from `app_settings` only when no route matches.
- Use the forwarded body and forwarded headers for the upstream call.
- Record:
  - client-facing model in `RequestRecord.model`
  - final upstream endpoint in `RequestRecord.upstream_url`
  - selected route in `RequestRecord.model_route`
  - upstream model in `RequestRecord.upstream_model`
- Pass the forwarded body and headers into both non-streaming and streaming paths.
- Keep request capture, response capture, error capture, and task-run assignment behavior
  unchanged.

### `admin.py`

- Show configured model routes on `/admin/settings` as read-only operational context.
- Mask API key state as `configured`, `missing`, or `not configured`; never render values.
- Update the upstream test form so entering a model uses the same routing decision as
  real proxy traffic.
- Keep the existing global upstream form as the fallback upstream.

### Templates and CSS

- Add a compact model-routes panel to `settings.html`.
- Add optional columns or detail metadata for route and upstream model:
  - request table: route badge only when a configured route was used;
  - request detail: client model, upstream model, route, and final upstream URL.
- Keep the UI dense and operational.

## Tests

Add focused coverage in `tests/test_proxy_capture.py`:

- Configured model routes to its own upstream.
- Configured model rewrites the forwarded JSON `model` to `upstream_model`.
- Configured model injects API key and overrides the client `Authorization` header.
- Configured model without API key preserves current header forwarding.
- Unknown model falls back to the global upstream.
- Missing model falls back to the global upstream.
- Streaming requests use the selected route and remain captured.
- Captured request body remains the original client body after upstream model rewrite.
- `RequestRecord.upstream_model`, `model_route`, and `upstream_url` are recorded.

Add coverage in `tests/test_rendering_and_cli.py` or a new config test module:

- JSON config parsing.
- File config parsing.
- Duplicate model rejection.
- Invalid upstream URL rejection.
- `api_key_env` resolution and masked display state.

Add admin UI coverage in `tests/test_admin_ui.py`:

- Settings page renders configured routes.
- Settings page does not render secret values.
- Upstream test uses the configured route for the entered model.
- Upstream test falls back to the global upstream for an unknown model.

## Documentation

Update:

- `README.md` with model-route examples.
- CLI help for `--models-file`.
- `docs/tests/README.md` with the new routing coverage map.
- `docs/publishing.md` only if release notes need to call out environment variables.

Example README snippet:

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:LLM_OBSERVE_MODELS_JSON = @'
[
  {
    "model": "openai-mini",
    "upstream_url": "https://api.openai.com/v1",
    "upstream_model": "gpt-4.1-mini",
    "api_key_env": "OPENAI_API_KEY"
  }
]
'@
.\.venv\Scripts\llm-observe-proxy.exe
```

## Phasing

Phase 1: configuration and routing core.

- Add model route config parsing.
- Add routing helper tests.
- Integrate proxy selection, API key injection, and upstream model rewrite.
- Record route metadata.

Phase 2: admin visibility and test upstream.

- Show routes in settings.
- Mask secret state.
- Make the test-upstream action route-aware.

Phase 3: docs and polish.

- Update README and test docs.
- Add CLI `--models-file`.
- Add request browser/detail route metadata.

## Open questions

- Should `/v1/models` return the configured proxy-facing model list, proxy the global
  upstream, or merge results from all configured upstreams?
- Should model matching remain exact, or should routes support aliases and pattern
  matching later?
- Should admin settings eventually edit model routes, or should routes stay config-only
  because they may reference secrets?
- Should direct `api_key` values be supported at all, or should the first implementation
  require `api_key_env` only?
