# LLM Observe Proxy API

The public API is served from the same process as the proxy:

- Base URL: `http://localhost:8080/api`
- Swagger UI: `http://localhost:8080/api/docs`
- OpenAPI JSON: `http://localhost:8080/api/openapi.json`

The project keeps the admin UI no-auth by default, so treat the API as a local
trusted interface unless you put the proxy behind your own access controls.

## Model Discovery

List routeable proxy-facing model names:

```bash
curl "http://localhost:8080/api/models?search=qwen&per_page=10"
```

Each item reports the model name an application should send to `/v1`, the matched
provider, upstream model, route status, and API key state:

```json
{
  "client_model": "qwen/qwen3.6-27b",
  "status": "active",
  "route": "qwen/qwen3.6-27b",
  "match_type": "exact",
  "provider_slug": "openrouter",
  "provider_name": "OpenRouter",
  "api_key_state": "configured",
  "upstream_model": "qwen/qwen3.6-27b@chutes/fp8"
}
```

Build a typeahead with bounded suggestions:

```bash
curl "http://localhost:8080/api/models/suggest?q=gemma&limit=10"
```

Look up exactly how a model will route:

```bash
curl "http://localhost:8080/api/models/lookup?model=gpt-5.4-mini"
curl "http://localhost:8080/api/models/lookup?model=gemma-4-26b"
curl "http://localhost:8080/api/models/lookup?model=qwen/qwen3.6-27b"
```

The lookup response includes `sample_request.curl`, `sample_request.python`, and a
sanitized upstream preview. Raw API keys are never returned; previews show env var
names such as `$OPENAI_API_KEY` or `$OPENROUTER_API_KEY`.

## Proxy Usage Capture

Applications can keep using the normal OpenAI-compatible `/v1` client base URL:

```python
from openai import OpenAI

client = OpenAI(api_key="local-dev-key", base_url="http://localhost:8080/v1")
stream = client.chat.completions.create(
    model="gpt-5.4-mini",
    messages=[{"role": "user", "content": "Stream a short answer"}],
    stream=True,
)
```

For OpenAI Chat Completions streaming requests, the proxy asks OpenAI for the final
usage chunk when the client omits `stream_options.include_usage`. This lets request
rows and run stats capture token and cost data for streams. If an application already
sends `stream_options.include_usage` as `true` or `false`, that explicit value is
preserved.

The proxy stores the original client request body in SQLite. Any default
`stream_options.include_usage=true` insertion is applied only to the upstream-forwarded
request. Older captured streams that did not include a usage event cannot be accurately
repriced from the stored SSE body alone.

## Run Lifecycle

Start a run:

```bash
curl -X POST "http://localhost:8080/api/runs/start" \
  -H "Content-Type: application/json" \
  -d '{"name":"Benchmark","notes":"Qwen vs Gemma"}'
```

Manage active runs:

```bash
curl -X POST "http://localhost:8080/api/runs/pause"
curl -X POST "http://localhost:8080/api/runs/1/resume"
curl -X POST "http://localhost:8080/api/runs/end"
```

List and inspect runs:

```bash
curl "http://localhost:8080/api/runs"
curl "http://localhost:8080/api/runs/1"
curl "http://localhost:8080/api/runs/1/stats"
curl "http://localhost:8080/api/runs/1/requests?page=1&per_page=50"
```

## Request Browsing

Browse captured proxy traffic:

```bash
curl "http://localhost:8080/api/requests?model=gpt-5.4-mini&per_page=25"
curl "http://localhost:8080/api/requests?provider=openrouter&route=qwen/qwen3.6-27b"
curl "http://localhost:8080/api/requests/123?mode=auto"
```

Request rows include model, route, upstream model, provider billing fields, token
usage, cost estimates, status, duration, stream/image/tool flags, and bounded
response previews. Detail responses keep the full captured body and rendered
payload modes.
