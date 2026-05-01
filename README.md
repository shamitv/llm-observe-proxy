# LLM Observe Proxy

`llm-observe-proxy` is an OpenAI-compatible, record-only proxy for inspecting LLM traffic.
It forwards requests to an upstream `/v1` API, stores requests and responses in SQLite,
and provides a local admin UI for browsing, pretty-printing, trimming, and changing the
upstream URL.

## Quick Start

```powershell
C:\Python\Python313\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\llm-observe-proxy.exe
```

By default, the proxy listens on `http://localhost:8080` and forwards requests to
`http://localhost:8000/v1`.

## Routes

- `ANY /v1/{path:path}`: OpenAI-compatible pass-through proxy.
- `GET /admin`: request browser.
- `GET /admin/requests/{id}`: request/response detail view.
- `GET /admin/settings`: upstream settings and retention tools.
- `POST /admin/settings/incoming`: update incoming host/port settings for next startup.
- `POST /admin/settings/upstream`: update upstream URL.
- `POST /admin/trim`: delete records older than `N` days.
- `GET /healthz`: health check.
