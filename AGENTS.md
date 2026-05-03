# AGENTS.md

Guidance for AI coding agents working on `llm-observe-proxy`.

## Project Snapshot

`llm-observe-proxy` is a Python 3.13 package that runs an OpenAI-compatible,
record-only proxy with SQLite capture and a server-rendered admin UI.

- Package name: `llm-observe-proxy`
- Import package: `llm_observe_proxy`
- CLI: `llm-observe-proxy`
- Default incoming server: `http://localhost:8080`
- Default upstream base: `http://localhost:8000/v1`
- Admin UI: `/admin`
- Settings UI: `/admin/settings`
- Proxy route: `ANY /v1/{path:path}`

## Environment

Use the requested Python install for the virtual environment:

```powershell
C:\Python\Python313\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

Run commands from the repository root, currently `D:\work\opeanai_proxy`.

## Git Workflow

Use feature branches for meaningful work:

```powershell
git switch -c feature/<short-name>
git add <files>
git commit -m "<type>: <summary>"
git switch main
git merge --no-ff feature/<short-name> -m "merge: <summary>"
```

Keep `main` clean after merges. Do not overwrite unrelated user changes. If a file is
already modified before your work, inspect the diff and preserve the user's intent.

Commit early and commit often. Once a meaningful small change is complete and verified,
commit that focused change before moving on to the next one. Keep each commit scoped to a
single coherent unit of work and avoid bundling unrelated edits together.

## Common Commands

Quality checks:

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\pytest.exe -q
```

Release checks:

```powershell
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe scripts\publish_pypi.py --dry-run
```

Publish to PyPI after setting `PYPI_TOKEN` in `.env` or the process environment:

```powershell
.\.venv\Scripts\python.exe scripts\publish_pypi.py
```

Run the proxy:

```powershell
.\.venv\Scripts\llm-observe-proxy.exe
```

Useful overrides:

```powershell
.\.venv\Scripts\llm-observe-proxy.exe --host localhost --port 8080
.\.venv\Scripts\llm-observe-proxy.exe --expose-all-ips
.\.venv\Scripts\llm-observe-proxy.exe --upstream-url http://localhost:8000/v1
```

## Code Map

- `src/llm_observe_proxy/app.py`: FastAPI app factory, lifespan setup, router mounting.
- `src/llm_observe_proxy/cli.py`: CLI args and incoming host/port binding resolution.
- `src/llm_observe_proxy/config.py`: defaults and environment-derived settings.
- `src/llm_observe_proxy/database.py`: SQLAlchemy models, SQLite setup, app settings helpers.
- `src/llm_observe_proxy/proxy.py`: `/v1/*` forwarding, request/response capture, streaming capture.
- `src/llm_observe_proxy/admin.py`: admin UI routes and settings actions.
- `src/llm_observe_proxy/rendering.py`: response pretty-printing and tool/Markdown/SSE rendering.
- `src/llm_observe_proxy/templates/`: Jinja templates.
- `src/llm_observe_proxy/static/`: admin UI CSS/JS.
- `tests/`: pytest suite with a fake upstream on `localhost:8080/v1`.
- `docs/tests/README.md`: detailed test coverage map.
- `docs/publishing.md`: PyPI release checklist and name-check notes.
- `scripts/seed_demo_db.py`: create a demo SQLite DB for screenshots.
- `scripts/capture_screenshots.py`: capture admin UI screenshots from the demo DB.
- `scripts/publish_pypi.py`: build, check, and publish distributions with dotenv-loaded tokens.

## Behavioral Rules

- The proxy is record-only. Do not add cache-hit serving unless explicitly requested.
- Always forward to upstream and then store request/response data in SQLite.
- Generic `/v1/*` endpoints should pass through; richer parsing belongs to known OpenAI shapes.
- Preserve support for non-streaming and SSE streaming responses.
- Keep admin UI no-auth unless the user asks for auth.
- Settings for incoming port and expose-all-IPs are persisted for the next process startup.
  Changing them in the UI does not rebind the currently running process.

## Defaults And Ports

Current defaults in `config.py`:

- `DEFAULT_INCOMING_HOST = "localhost"`
- `DEFAULT_INCOMING_PORT = 8080`
- `EXPOSED_INCOMING_HOST = "0.0.0.0"`
- `DEFAULT_UPSTREAM_URL = "http://localhost:8000/v1"`

Tests intentionally use `localhost:8080/v1` as their fake upstream. This is separate from
the runtime default upstream and matches the original test requirement. If you change ports,
update tests and docs deliberately.

## Testing Notes

Run the full test suite before committing code changes:

```powershell
.\.venv\Scripts\pytest.exe -q
```

The tests require port `8080` to be free because `tests/conftest.py` starts the fake
upstream there. If a local proxy is running on 8080, stop it before running tests.

For UI or settings changes, add or update tests in `tests/test_admin_ui.py`.
For proxy capture behavior, use `tests/test_proxy_capture.py`.
For renderer or CLI changes, use `tests/test_rendering_and_cli.py`.

## User-Facing Documentation

- `README.md` is the GitHub/developer README and may include local screenshot references
  under `docs/screenshots/`.
- `README.pypi.md` is the PyPI long description configured in `pyproject.toml`. Keep it
  screenshot-free; do not use relative `docs/screenshots/...` image references because
  they render as broken images on PyPI.
- When adding or changing user-facing features, update both `README.md` and
  `README.pypi.md` so install, usage, routes, settings, and feature descriptions stay
  aligned.
- If UI screenshots need refreshing, regenerate them only from the seeded demo harness
  (`scripts/seed_demo_db.py` and `scripts/capture_screenshots.py`), not from real local
  traffic or private data.

## UI Guidance

Keep the UI professional and operational:

- Prefer compact panels, dense tables, clear labels, and predictable controls.
- Avoid marketing-page patterns.
- Keep Jinja templates defensive for settings values that may be absent from older app
  contexts; for example, the settings template falls back to `localhost:8080`.
- Do not add heavy frontend dependencies unless the user specifically asks.

## SQLite And Persistence

SQLite is initialized automatically at startup. The default local DB file is ignored by git:

```text
llm_observe_proxy.sqlite3
```

When adding settings, store simple values in `app_settings` using helpers in
`database.py`. Keep validation in the admin route and fallback parsing in database helpers.

## Known Gaps

See `docs/tests/README.md` for the current coverage matrix. Notable gaps include:

- Multiple tool calls in one response.
- Tool response messages using `role: "tool"` and `tool_call_id`.
- Streamed tool-call delta reconstruction.
- Upstream connection failure and timeout logging.
- Concurrent proxy requests.
