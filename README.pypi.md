# LLM Observe Proxy

`llm-observe-proxy` is an OpenAI-compatible, record-only-by-default proxy for inspecting
LLM traffic. It forwards requests to an upstream `/v1` API, stores requests and responses
in SQLite, and provides a polished local admin UI for browsing, pretty-printing,
trimming, grouping task runs, and changing runtime settings.

It is useful when you want LiteLLM-style observability without introducing a full gateway
or external database.

Project repository: https://github.com/shamitv/llm-observe-proxy

Current release includes editable scalar and tiered model pricing, catalog sync for
router providers, cached-token cost snapshots, router fallback seed data, and run
what-if comparisons.

## Features

- OpenAI-compatible passthrough route: `ANY /v1/{path:path}`.
- SQLite capture for request/response headers, bodies, status, timing, model, endpoint,
  streaming state, tool-call signals, image assets, provider token usage, cost snapshots,
  and errors.
- Live-updating admin UI for searching and browsing captured traffic, including
  per-request output TPS and estimated cost.
- Runs for grouping all requests made during a task, benchmark, or repro workflow.
- Live run detail pages with request counts, LLM wall time, token totals, cost totals,
  tokens/sec, model and endpoint breakdowns, and signal/error counts.
- Run what-if pricing for comparing captured usage against other configured scalar or
  tiered model prices.
- Pricing catalog preview/apply for Hugging Face Router and OpenRouter model/provider
  combinations.
- Detail pages with response render modes for JSON, plain text, Markdown, tool calls,
  and raw SSE streams.
- Request image gallery for data URL and remote image references.
- Settings UI with Server, Routing, Providers, Pricing, Diagnostics, and Data tabs for
  upstream fallback defaults, editable exact/prefix routes, provider health checks, price
  tiers, response compatibility fixes, incoming host/port preferences, all-IPs exposure,
  route simulation, and retention trimming.
- Config-driven model routes for sending selected proxy-facing model names to different
  upstream `/v1` endpoints with optional upstream model rewrites, provider selection,
  and API key injection.
- Opt-in response compatibility fixes for known upstream quirks, with raw upstream
  response audit storage when a rewrite or warning occurs.
- No authentication by default, intended for local or trusted development networks.

## Install

From PyPI with `pip`:

```powershell
python -m pip install llm-observe-proxy
llm-observe-proxy
```

From PyPI with `uv`:

```powershell
uv tool install llm-observe-proxy
llm-observe-proxy
```

Run it once without installing:

```powershell
uvx llm-observe-proxy
```

By default, the proxy listens on:

```text
http://localhost:8080
```

and forwards requests to:

```text
http://localhost:8000/v1
```

Open the admin UI:

```text
http://localhost:8080/admin
```

## Usage

Point an OpenAI-compatible client at the proxy:

```python
from openai import OpenAI

client = OpenAI(
    api_key="local-dev-key",
    base_url="http://localhost:8080/v1",
)

response = client.chat.completions.create(
    model="gpt-demo",
    messages=[{"role": "user", "content": "Hello through the proxy"}],
)
print(response.choices[0].message.content)
```

Run on a different port:

```powershell
llm-observe-proxy --port 8090
```

Expose on all interfaces:

```powershell
llm-observe-proxy --expose-all-ips
```

Set the upstream from the CLI:

```powershell
llm-observe-proxy --upstream-url http://localhost:8000/v1
```

Load model-specific upstream routes from a JSON file:

```powershell
llm-observe-proxy --models-file .\models.json
```

You can also change the upstream URL, fallback provider/model, model upstream routes,
response compatibility fixes, model provider pricing, and next-start incoming host/port
settings from `/admin/settings/server` and the other Settings tabs.

The Providers tab includes a seeded `Local LLM` provider pointing at
`http://localhost:8000/v1` with no API key requirement. Select it as the fallback
provider and set the fallback model name to route unmatched traffic to a local
OpenAI-compatible server.

## Model Routes

Model routes let one proxy endpoint send different client-facing models to different
OpenAI-compatible upstreams. Routes match the request payload's top-level `model` by
exact value or by a suffix-`*` prefix pattern. Startup routes have first priority, then
SQLite-managed routes are resolved by priority and specificity. Unknown models, requests
without a JSON model, and generic calls such as `GET /v1/models` use the global upstream
fallback when a default provider/model is enabled.

Example route file:

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
    "provider_slug": "openai",
    "api_key_env": "OPENAI_API_KEY"
  }
]
```

The same file can use an object form when you want default-upstream fixes as well as
route-specific fixes:

```json
{
  "default_fixes": [],
  "model_routes": [
    {
      "model": "local-qwen",
      "upstream_url": "http://localhost:8000/v1",
      "upstream_model": "qwen3-coder-30b",
      "fixes": ["qwen-tagged-tool-call-rewrite"]
    }
  ]
}
```

Run with the file:

```powershell
$env:OPENAI_API_KEY = "sk-..."
llm-observe-proxy --models-file .\models.json
```

You can also set `LLM_OBSERVE_MODELS_JSON` to the same JSON array. If both
`LLM_OBSERVE_MODELS_FILE` and `LLM_OBSERVE_MODELS_JSON` are set, the file wins.

You can add, update, simulate, and delete UI-managed model routes from
`/admin/settings/routing`. UI-managed routes are stored in SQLite and take effect
immediately. Routes loaded from `--models-file`, `LLM_OBSERVE_MODELS_FILE`, or
`LLM_OBSERVE_MODELS_JSON` remain read-only in the UI, and duplicate startup model names
are rejected.

SQLite also seeds default exact routes from active model pricing rows, including aliases,
so common provider model IDs can route without a separate `models.json` file. The Routing
tab can preview or apply missing default routes for all providers or one provider. Seeded
routes are marked as generated, use priority `90`, and stop being overwritten once you edit
them. Hugging Face Router provider suffixes are forwarded as model IDs, while OpenRouter
endpoint rows such as `model@provider-tag` are forwarded as `model` with provider pinning
and fallbacks disabled.

When a route has an API key, the proxy injects `Authorization: Bearer <key>` for the
upstream request. Captured request headers remain the original client headers; injected
keys are not stored or shown in the admin UI. UI-managed routes store only `api_key_env`;
prefer `api_key_env` for shared configs.

## Response Compatibility Fixes

Compatibility fixes are ordered, opt-in response transformations for known
model/provider quirks. The first built-in fix is `qwen-tagged-tool-call-rewrite`, which
can promote a complete Qwen-style `<tool_call>` block from Chat Completions
`reasoning_content` or `reasoning` into structured OpenAI-compatible `tool_calls`.

The Qwen fix runs only on `/v1/chat/completions` when the request declares tools. It
does not execute tools. Malformed or ambiguous blocks pass through unchanged and are
recorded as warnings. When a fix rewrites or warns, the request detail page stores and
shows both the client-visible response and the raw upstream response.

Configure fixes from `/admin/settings/server`, per model route, or with environment
variables:

```powershell
$env:LLM_OBSERVE_DEFAULT_FIXES_JSON = '["qwen-tagged-tool-call-rewrite"]'
```

## Cost Estimates

Cost estimates are snapshotted when a response is captured. The proxy stores the billing
provider, billing model, token counts, input/output rate snapshot, and estimated USD cost
on the request row. Existing estimated costs are not overwritten when pricing changes.
The Pricing tab can preview and apply current Hugging Face Router and OpenRouter catalog
rows, then fill only captured requests that are still missing estimated cost. You can
also run `llm-observe-proxy --backfill-cached-costs` to reprice older rows that already
report cached input tokens and lack cached-pricing snapshot metadata. Those rows are
repriced with the current configured cached-input rates and marked with
`historical_cost_backfill` in the pricing snapshot.

Token counts are extracted from OpenAI-compatible `usage` objects, including the shapes
used by OpenAI, vLLM, SGLang, and LM Studio. When standard usage is absent, the proxy can
also read llama.cpp `timings` and Ollama-style `prompt_eval_count` / `eval_count` fields
if those metrics are present in captured `/v1` responses or stream events.

The estimator uses separate input, cached-input, and output token rates per 1M tokens:

```text
cost = (uncached_input_tokens * input_rate
      + cached_input_tokens * cached_input_rate
      + output_tokens * output_rate) / 1,000,000
```

If cached input tokens are present but the matched model price has no cached-input rate,
those tokens fall back to the standard input rate. Cache-write token counts from router
responses are preserved in pricing snapshots for audit/debugging, but v0.4 does not bill a
separate cache-write dimension.

Billing identity is resolved from the routed upstream model when a model route rewrites
the request, otherwise from the upstream response model when present, otherwise from the
client request model. Provider-specific router rows are matched when HF Router model
suffixes are preserved or when OpenRouter requests pin exactly one endpoint with
fallbacks disabled. Provider identity comes from a route's optional `provider_slug`, then
falls back to a provider whose configured upstream URL exactly matches the active
upstream base. Historical cached-cost backfills can also infer the provider when a stored
upstream request URL starts with a configured provider URL.

SQLite is seeded with editable standard paid text rates for legacy OpenAI, Anthropic, and
Google Gemini rows plus a broader current catalog checked on May 23, 2026. The v0.4 seed
catalog includes first-party rows for Alibaba/Qwen, DeepSeek, xAI, Z.ai, Moonshot/Kimi,
and Mistral where suitable API pricing is published. OpenRouter and Hugging Face Router
rows are seeded as router-provider fallbacks and endpoint-specific options when available.
Seeded rows include source metadata, aliases, cached-input rates only where cache-hit or
cache-read pricing is published, and Qwen-style request-size tiers. Seeds are inserted only
when missing, and older seed-owned rows can be refreshed without overwriting UI edits.
The provider catalog also seeds `Local LLM` as an editable no-key local endpoint for
fallback routing.

Catalog sync uses the configured provider API key environment variables when present:
`HF_TOKEN` for Hugging Face Router and `OPENROUTER_API_KEY` for OpenRouter. OpenRouter
per-token catalog prices are converted to this app's USD-per-1M-token rows. Cache-write,
image, fixed request, discount, and other non-text-token prices are stored in notes but
are not included in cost math.

Tier ranges use `[min_input_tokens, max_input_tokens)`, and tier selection happens per
captured request. Run what-if comparisons estimate each request independently and then sum
the results; when a run spans multiple tiers, rate columns show `Mixed tiers`. Estimates
still ignore non-token charges such as batch/flex/priority discounts, separate cache-write
fees, tool fees, image/audio prices, and regional premiums.

Run detail pages include what-if cost comparisons. By default they compare captured run
usage against GPT-5.5 and GPT-5.4 Mini when those prices are active. You can add or
remove other active model prices from a compact typeahead on the run page; those
selections stay in the current browser session.

What-if comparisons use stored request token counts and do not change captured request
cost snapshots.

## Runs

Use **Runs** when you want to measure or review LLM usage for one bounded task, such as
processing a video, comparing local and cloud models, or reproducing an agent issue.

1. Open `/admin/runs` or use the run control on `/admin`.
2. Enter a required run name and choose **Start run**.
3. Run your application or benchmark through the proxy.
4. Choose **Pause** to keep recording traffic outside the run, **Resume** to attach
   new traffic to that run again, or **End run** when the task is complete.

Starting a new run automatically ends any existing active run. Paused runs remain open
and resumable, but only one run can be active at a time. Requests made while a run is
active are linked to that run; requests outside a run, including while all runs are
paused, are still captured normally.

The request browser can filter by run, and request rows link back to their run. The run
detail page reports LLM wall time from the first request start to the last response
completion, plus token totals, cost totals, and tokens/sec metrics. The request table's
**TPS** column shows per-request output tokens per second when token usage and duration
are available. Run-level **Output tok/s** uses output tokens divided by summed request
duration, matching the total request duration shown on the page.

Request and run list/detail pages load their data from local REST endpoints and poll once
per second while visible, so new requests, pending request completion, active-run counts,
and run metrics update without manually refreshing the browser.

Screenshots and the full developer README are available in the project repository:
https://github.com/shamitv/llm-observe-proxy

## Routes

- `ANY /v1/{path:path}`: OpenAI-compatible pass-through proxy.
- `GET /admin`: request browser.
- `GET /admin/requests/{id}`: request/response detail view.
- `GET /admin/runs`: run browser and active run controls.
- `GET /admin/runs/{id}`: run metrics, what-if cost comparison, and associated request list.
- `POST /admin/runs/start`: start a named run, ending any active run first.
- `POST /admin/runs/pause`: pause the active run.
- `POST /admin/runs/{id}/resume`: resume an open paused run.
- `POST /admin/runs/end`: end the active run.
- `GET /admin/api/requests`: request browser JSON data with filters and pagination.
- `GET /admin/api/requests/{id}`: request detail JSON data and rendered payload modes.
- `GET /admin/api/runs`: run browser JSON data and active-run summary.
- `GET /admin/api/runs/{id}`: run detail JSON metrics and associated request rows.
- `POST /admin/api/runs/start`: start a run through JSON.
- `POST /admin/api/runs/pause`: pause the active run through JSON.
- `POST /admin/api/runs/{id}/resume`: resume an open paused run through JSON.
- `POST /admin/api/runs/end`: end the active run through JSON.
- `GET /admin/settings`: redirects to the Server settings tab.
- `GET /admin/settings/server`: listener, upstream fallback, default fixes, route summary, test, and retention controls.
- `GET /admin/settings/routing`: editable exact/prefix routes, fallback behavior, simulator, and usage summary.
- `GET /admin/settings/providers`: provider registry, capabilities, fallback provider, health checks, and usage summary.
- `GET /admin/settings/pricing`: model pricing registry, tiers, aliases, and active-state controls.
- `GET /admin/settings/diagnostics`: provider health, upstream test, route simulator, and latest test result.
- `GET /admin/settings/data`: storage stats, retention trimming, and data-management placeholders.
- `GET /admin/api/settings/summary`: listener/upstream/route/provider/storage JSON summary.
- `GET/POST /admin/api/providers`: provider registry JSON list/create endpoints.
- `GET/PUT/DELETE /admin/api/providers/{slug}`: provider JSON read/update/delete endpoints.
- `POST /admin/api/providers/health-checks`: run lightweight provider health checks.
- `GET/POST /admin/api/routes`: route registry JSON list/create endpoints.
- `GET/PUT/DELETE /admin/api/routes/{route_id}`: route JSON read/update/delete endpoints.
- `POST /admin/api/routes/defaults/preview`: preview generated default routes from active prices.
- `POST /admin/api/routes/defaults/apply`: insert missing or refresh generated default routes.
- `POST /admin/api/routes/sample-request`: return proxy request snippets and sanitized upstream preview.
- `POST /admin/api/routes/simulate`: simulate route resolution for a model name.
- `POST /admin/api/pricing/catalog/preview`: preview current HF Router or OpenRouter pricing rows.
- `POST /admin/api/pricing/catalog/apply`: apply selected catalog pricing rows and optionally fill missing cost estimates.
- `POST /admin/settings/incoming`: update incoming host/port settings for next startup.
- `POST /admin/settings/upstream`: update upstream URL.
- `POST /admin/settings/upstream-defaults`: update upstream fallback provider/model behavior.
- `POST /admin/settings/compat-fixes`: update default-upstream compatibility fixes.
- `POST /admin/settings/model-routes`: create or update a UI-managed model route.
- `POST /admin/settings/model-routes/delete`: delete a UI-managed model route.
- `POST /admin/settings/providers`: create or update a model provider.
- `POST /admin/settings/providers/delete`: delete a model provider and its prices.
- `POST /admin/settings/model-prices`: create or update model token pricing.
- `POST /admin/settings/model-prices/delete`: delete model token pricing.
- `POST /admin/settings/model-price-tiers`: create a request-size price tier.
- `POST /admin/settings/model-price-tiers/delete`: delete a request-size price tier.
- `POST /admin/trim`: delete records older than `N` days.
- `GET /healthz`: health check.

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_OBSERVE_DATABASE_URL` | `sqlite:///./llm_observe_proxy.sqlite3` | SQLite SQLAlchemy URL. |
| `LLM_OBSERVE_INCOMING_HOST` | `localhost` | Bind host when not exposing all IPs. |
| `LLM_OBSERVE_INCOMING_PORT` | `8080` | Bind port. |
| `LLM_OBSERVE_EXPOSE_ALL_IPS` | `false` | Bind to `0.0.0.0` when true. |
| `LLM_OBSERVE_UPSTREAM_URL` | `http://localhost:8000/v1` | Upstream OpenAI-compatible `/v1` base URL. |
| `LLM_OBSERVE_MODELS_JSON` | unset | JSON array of model route objects, or an object with `default_fixes` and `model_routes`. |
| `LLM_OBSERVE_MODELS_FILE` | unset | Path to a JSON file containing model routes or model config. Wins over `LLM_OBSERVE_MODELS_JSON`. |
| `LLM_OBSERVE_DEFAULT_FIXES_JSON` | unset | JSON array of default-upstream compatibility fix IDs when no model config object supplies `default_fixes`. |
| `LLM_OBSERVE_LOG_LEVEL` | `INFO` | Uvicorn log level. |

Incoming host/port settings saved in the UI are used on the next process startup; they do
not rebind a currently running process.

## Tests

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe -q
```

The test suite starts its fake upstream on a free temporary loopback port, so a local
proxy can keep running on `8080` while tests execute.

## Publishing

See the repository publishing guide for name checks, build commands, and the pre-publish
checklist.

## License

MIT.
