# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses semantic versioning.

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
