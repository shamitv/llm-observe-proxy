# LLM Observe Proxy

`llm-observe-proxy` is an OpenAI-compatible, record-only proxy for inspecting LLM
traffic. It forwards requests to an upstream `/v1` API, stores requests and responses in
SQLite, and provides a polished local admin UI for browsing, pretty-printing, trimming,
grouping task runs, and changing runtime settings.

It is useful when you want LiteLLM-style observability without introducing a full gateway
or external database.

Published package: https://pypi.org/project/llm-observe-proxy/

## Features

- OpenAI-compatible passthrough route: `ANY /v1/{path:path}`.
- SQLite capture for request/response headers, bodies, status, timing, model, endpoint,
  streaming state, tool-call signals, image assets, cost snapshots, and errors.
- Admin UI for searching and browsing captured traffic, including per-request output TPS
  and estimated cost.
- Runs for grouping all requests made during a task, benchmark, or repro workflow.
- Run detail pages with request counts, LLM wall time, token totals, cost totals,
  tokens/sec, model and endpoint breakdowns, and signal/error counts.
- Detail pages with response render modes for JSON, plain text, Markdown, tool calls,
  and raw SSE streams.
- Request image gallery for data URL and remote image references.
- Settings UI for upstream URL, model upstream routes, model provider/pricing config,
  incoming host/port preferences, all-IPs exposure, and retention trimming.
- Config-driven model routes for sending selected proxy-facing model names to different
  upstream `/v1` endpoints with optional upstream model rewrites, provider selection,
  and API key injection.
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

For local development from this repository:

```powershell
C:\Python\Python313\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\llm-observe-proxy.exe
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

You can also change the upstream URL, model upstream routes, model provider pricing,
and next-start incoming host/port settings from `/admin/settings`.

## Model Routes

Model routes let one proxy endpoint send different client-facing models to different
OpenAI-compatible upstreams. Routes match the request payload's top-level `model`
exactly. Unknown models, requests without a JSON model, and generic calls such as
`GET /v1/models` use the global upstream fallback.

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

Run with the file:

```powershell
$env:OPENAI_API_KEY = "sk-..."
llm-observe-proxy --models-file .\models.json
```

You can also set `LLM_OBSERVE_MODELS_JSON` to the same JSON array. If both
`LLM_OBSERVE_MODELS_FILE` and `LLM_OBSERVE_MODELS_JSON` are set, the file wins.

You can add, update, and delete UI-managed model routes from `/admin/settings`.
UI-managed routes are stored in SQLite and take effect immediately. Routes loaded from
`--models-file`, `LLM_OBSERVE_MODELS_FILE`, or `LLM_OBSERVE_MODELS_JSON` remain read-only
in the UI, and duplicate model names are rejected.

When a route has an API key, the proxy injects `Authorization: Bearer <key>` for the
upstream request. Captured request headers remain the original client headers; injected
keys are not stored or shown in the admin UI. UI-managed routes store only `api_key_env`;
prefer `api_key_env` for shared configs.

## Cost Estimates

Cost estimates are snapshotted when a response is captured. The proxy stores the billing
provider, billing model, token counts, input/output rate snapshot, and estimated USD cost
on the request row. Historical rows are not recalculated when pricing changes.

The estimator uses separate input and output token rates per 1M tokens:

```text
cost = (input_tokens * input_rate + output_tokens * output_rate) / 1,000,000
```

Billing identity is resolved from the routed upstream model when a model route rewrites
the request, otherwise from the upstream response model when present, otherwise from the
client request model. Provider identity comes from a route's optional `provider_slug`,
then falls back to a provider whose configured upstream URL exactly matches the active
upstream base.

SQLite is seeded with editable standard paid text rates for common OpenAI, Anthropic,
and Google Gemini models. Those seed values were checked against official pricing pages
on May 3, 2026. They are inserted only when missing, so UI edits are preserved. V1 cost
estimates intentionally ignore cache, batch/flex/priority tiers, tool fees, image/audio
pricing, regional premiums, and long-context premiums.

## Runs

Use **Runs** when you want to measure or review LLM usage for one bounded task, such as
processing a video, comparing local and cloud models, or reproducing an agent issue.

1. Open `/admin/runs` or use the run control on `/admin`.
2. Enter a required run name and choose **Start run**.
3. Run your application or benchmark through the proxy.
4. Choose **End run** when the task is complete.

Starting a new run automatically ends any existing active run. Requests made while a run
is active are linked to that run; requests outside a run are still captured normally.

The request browser can filter by run, and request rows link back to their run. The run
detail page reports LLM wall time from the first request start to the last response
completion, plus token totals, cost totals, and tokens/sec metrics. The request table's
**TPS** column shows per-request output tokens per second when token usage and duration
are available.

## Screenshots

Screenshots are generated from a seeded demo database and stored in `docs/screenshots`.

| Request browser | Tool calls |
| --- | --- |
| ![Request browser](docs/screenshots/requests.png) | ![Tool-call detail](docs/screenshots/tool-calls.png) |

| Images | Settings |
| --- | --- |
| ![Image request detail](docs/screenshots/images.png) | ![Settings](docs/screenshots/settings.png) |

Additional screenshots:

- [Simple request detail](docs/screenshots/simple-request.png)
- [Streaming SSE detail](docs/screenshots/streaming.png)

Regenerate screenshots:

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo_db.py .tmp\screenshots.sqlite3
.\.venv\Scripts\python.exe scripts\capture_screenshots.py --database .tmp\screenshots.sqlite3 --output docs\screenshots
```

## Routes

- `ANY /v1/{path:path}`: OpenAI-compatible pass-through proxy.
- `GET /admin`: request browser.
- `GET /admin/requests/{id}`: request/response detail view.
- `GET /admin/runs`: run browser and active run controls.
- `GET /admin/runs/{id}`: run metrics and associated request list.
- `POST /admin/runs/start`: start a named run, ending any active run first.
- `POST /admin/runs/end`: end the active run.
- `GET /admin/settings`: upstream settings and retention tools.
- `POST /admin/settings/incoming`: update incoming host/port settings for next startup.
- `POST /admin/settings/upstream`: update upstream URL.
- `POST /admin/settings/model-routes`: create or update a UI-managed model route.
- `POST /admin/settings/model-routes/delete`: delete a UI-managed model route.
- `POST /admin/settings/providers`: create or update a model provider.
- `POST /admin/settings/providers/delete`: delete a model provider and its prices.
- `POST /admin/settings/model-prices`: create or update model token pricing.
- `POST /admin/settings/model-prices/delete`: delete model token pricing.
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
| `LLM_OBSERVE_MODELS_JSON` | unset | JSON array of model route objects. |
| `LLM_OBSERVE_MODELS_FILE` | unset | Path to a JSON file containing model routes. Wins over `LLM_OBSERVE_MODELS_JSON`. |
| `LLM_OBSERVE_LOG_LEVEL` | `INFO` | Uvicorn log level. |

Incoming host/port settings saved in the UI are used on the next process startup; they do
not rebind a currently running process.

## Tests

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe -q
```

The test suite starts a fake upstream on `localhost:8080/v1`, so stop any local process
using port `8080` before running tests. See [docs/tests/README.md](docs/tests/README.md)
for the full coverage matrix.

## Publishing

See [docs/publishing.md](docs/publishing.md) for name checks, build commands, and the
pre-publish checklist.

## License

MIT. See [LICENSE](LICENSE).
