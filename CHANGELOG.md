# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses semantic versioning.

## Unreleased

### Added

- Task Runs in the admin UI for grouping requests made during a named task,
  benchmark, or repro workflow.
- Run detail pages with LLM wall time, request count, token totals, tokens/sec,
  model/endpoint/status breakdowns, and stream/image/tool/error counts.
- Request browser filtering by run, plus run badges on request rows and detail pages.
- Per-request TPS column in admin request tables, computed from output tokens and
  request duration when usage data is available.
- Settings UI support for adding, updating, deleting, and immediately using
  SQLite-persisted model upstream routes.
- SQLite compatibility upgrade for adding run associations to existing databases.

## [0.1.1] - 2026-05-01

### Added

- Token usage columns in the admin request grid for input, output, and total token counts.

### Changed

- Lowered the minimum supported Python version from 3.13 to 3.10.

### Documentation

- Added a direct PyPI package reference in the README.
- Added install and run instructions for `pip`, `uv tool install`, and `uvx`.
- Refreshed the request browser and settings screenshots to match the current admin UI.

## [0.1.0] - 2026-05-01

### Added

- OpenAI-compatible `ANY /v1/{path:path}` record-only proxy.
- SQLite storage for request metadata, request bodies, response metadata, response bodies,
  stream bodies, image assets, timings, errors, model names, and tool-call signals.
- Admin UI for browsing captured requests, filtering by model/endpoint/status/signals,
  viewing detail pages, previewing request images, and rendering responses as JSON, text,
  Markdown, tool calls, or raw SSE.
- Settings UI for upstream `/v1` URL, incoming host/port preferences, all-IPs exposure,
  and retention trimming.
- CLI entrypoint: `llm-observe-proxy`.
- Test suite covering non-streaming requests, streaming, reasoning responses, images,
  tool calls, generic passthrough, UI rendering, settings, trimming, and CLI behavior.

### Packaging

- First PyPI-ready package metadata.
- Dependency lower bounds refreshed to current stable releases available during release prep.
- Python 3.13 support.
- MIT license.
