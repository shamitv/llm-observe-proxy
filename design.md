# LLM Observe Proxy Design Guide

## Product Intent

LLM Observe Proxy is a local, developer-focused observability console for
OpenAI-compatible traffic. The UI should feel like an operational debugging
surface: compact, fast to scan, live-updating, and safe around configuration or
destructive actions.

The default presentation should answer:

- What is happening right now?
- Which run is active or failing?
- Which requests are slow, expensive, streaming, tool-heavy, or errored?
- Which provider, route, model, and fallback behavior produced the result?
- What did the traffic cost, and how would that cost change on another model?

Raw JSON, headers, SSE chunks, and pricing snapshots should remain available,
but they should not dominate the first screen.

## Visual System

- Use the existing `LO` mark, `LLM Observe Proxy` name, and top navigation:
  Requests, Runs, Settings, Health.
- Keep the UI light, utilitarian, and dashboard-oriented: white panels, pale
  gray page background, subtle borders/shadows, compact tables, and clear labels.
- Use teal/green as the primary accent, green for healthy/success states, red for
  danger/error, amber for warnings/slow requests, blue for stream signals, and
  purple for tool signals.
- Cards should have modest radius and never feel like a marketing landing page.
- Dense controls are acceptable, but text must not overlap or require guessing.

## Requests And Runs

- Requests are live REST-driven views. Preserve URL filters, pagination, and
  selected context during polling.
- Request Browser defaults to debug-first columns: Request, Model/Provider, Run,
  Status, Performance, Tokens, Cost, Signals, Summary.
- Summary text should be semantic whenever possible. Avoid raw SSE fragments in
  list views; keep raw payloads in detail views.
- Cost and provider must render on separate visual lines.
- Long run names and model names should clamp with a title tooltip, not stretch
  table rows.
- Desktop request rows may select a right-side inspector; mobile taps should open
  the full request detail.
- Run Detail defaults to Overview with health, top models, status codes, signals,
  compact what-if cost, insights, and recent traffic. Full traffic and detailed
  what-if comparison live behind tabs.
- Run metrics must keep the current meanings:
  `Run open` is clock time since run start, `LLM wall time` is first request to
  latest completed request, and `Output tok/s` uses output tokens over observed
  request duration.

## Settings

- Settings use the tabbed admin shell: Server, Routing, Providers, Pricing,
  Diagnostics, Data.
- Keep provider, route, pricing, fallback, diagnostics, and retention workflows
  operational and compact.
- Never display raw API key values. Show environment variable names only.
- Network exposure and destructive actions must use clear warnings and explicit
  confirmation.

## Responsive And Accessibility

- Wide desktop can use multi-column dashboards and a persistent request inspector.
- Mobile must not require page-level horizontal scrolling. Use stacked cards,
  compact traffic rows, and horizontally scrollable tabs only when needed.
- Tables may retain horizontal scrolling only inside raw/detail contexts.
- All interactive controls need visible focus states, labels or accessible names,
  keyboard access, and text labels in addition to color-coded status.

## Mockups And Screenshots

- Phase-specific mockups under `docs/plans/` are visual references, not
  pixel-perfect contracts.
- Prefer preserving existing backend behavior and shared components while moving
  presentation toward the mockups.
- Refresh screenshots only from the seeded demo harness, never from private local
  traffic.
