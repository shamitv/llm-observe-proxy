# LLM Observe Proxy — Requests and Runs UI Design Spec

## 1. Purpose

This document describes the target UI/UX design for the **Requests**, **Run in Progress**, and responsive **mobile run dashboard** screens in `LLM Observe Proxy`.

It is intended for coding agents implementing frontend and backend changes. Use this document together with the generated mockup images:

1. **Request Browser v2 desktop mockup**
2. **Run in Progress desktop mockup**
3. **Run in Progress mobile mockup**

The design goal is to evolve the current admin UI from a capable request table into a polished LLM observability dashboard that helps users quickly answer:

- What is happening right now?
- Which run is active?
- Which requests are slow, failing, streaming, or using tools?
- Which model/provider/route was used?
- How many tokens and how much cost is being consumed?
- What would this run cost on another model/provider?
- Which requests should I inspect next?

---

## 2. Product Context

`LLM Observe Proxy` is an OpenAI-compatible proxy and observability layer. It captures traffic flowing through `/v1` endpoints and exposes an admin UI for:

- Browsing captured requests
- Inspecting request/response bodies
- Grouping requests into runs
- Measuring latency, throughput, token usage, and estimated cost
- Tracking streaming, image, and tool-call signals
- Comparing costs across model/provider pricing scenarios
- Debugging routing, provider, and compatibility behavior

The UI should be optimized for local/developer workflows, but it should still feel like a high-quality observability product.

---

## 3. Design Principles

### 3.1 Debug-first, not database-first

The UI should not merely display rows from a database. It should help users identify problems and answer debugging questions quickly.

Examples:

- Which requests failed?
- Which requests were slow?
- Which requests used tools?
- Which model/provider generated the cost?
- What was the semantic outcome of the request?
- Which route/provider was used?

### 3.2 Progressive disclosure

Default screens should be compact and easy to scan. Dense raw data such as headers, raw SSE chunks, pricing snapshots, and full JSON payloads should remain available but not dominate the primary view.

### 3.3 Live observability

Active runs should feel live. The UI should show whether data is updating, when the last activity happened, and whether the run is currently active.

### 3.4 Semantic summaries over raw fragments

List views should avoid raw SSE/JSON fragments where possible. Prefer semantic summaries:

- `Streaming response · Tool call: read_file`
- `Reasoning content detected · Tool call: search_web`
- `Server error 500 · Internal server error occurred`
- `Long response · 5.7k tokens · Includes detailed explanation`

Raw payloads belong in detail views.

### 3.5 Responsive by design

The desktop layout can be dense and multi-column. The mobile layout must remain readable and touch-friendly, using stacked cards and compact rows.

---

## 4. Visual System

### 4.1 Brand and Shell

Use the existing product identity:

- Logo: rounded square with `LO`
- Product name: `LLM Observe Proxy`
- Small upstream/base URL text beside product name when space allows
- Header nav:
  - Requests
  - Runs
  - Settings
  - Health
- Active nav item: teal/green outline or filled accent
- User/avatar circle on the right, for example `LA`

### 4.2 Colors

Suggested semantic palette:

| Purpose | Style |
|---|---|
| Primary accent | Teal/green |
| Success | Green |
| Warning / slow | Amber/orange |
| Error / danger | Red |
| Stream signal | Blue |
| Tool signal | Purple |
| Neutral background | Very light gray |
| Cards | White |
| Text primary | Dark navy / near black |
| Text secondary | Muted gray-blue |
| Borders | Pale gray |

### 4.3 Components

Common components:

- Rounded cards
- Stat/KPI tiles
- Pill badges
- Toggle/filter chips
- Compact tables
- Semantic preview rows
- Right-side inspector drawer on desktop
- Bottom/stacked sections on mobile
- Danger buttons for destructive actions
- Live status indicator with small green dot

### 4.4 Typography

- Use a clean sans-serif system font.
- Page titles should be large and bold.
- KPI values should be prominent.
- Labels should be smaller and muted.
- Tables should use readable but compact row height.
- Avoid tiny text in mobile layouts.

---

## 5. Current UI vs Target UI

### 5.1 Current Requests UI

Current strengths:

- Captures and displays important request dimensions.
- Supports endpoint, model, run, status, stream, image, and tool filters.
- Shows status, duration, TPS, token triplet, cost, signals, and preview.
- Has pagination.
- Request detail supports multiple response modes such as JSON, text, markdown, tool, and SSE.

Current issues:

| Area | Problem |
|---|---|
| Table width | Too many columns cause horizontal scrolling. |
| Preview | Streaming rows show raw SSE/JSON fragments instead of semantic summaries. |
| Signals | Useful but not clickable enough as quick filters. |
| Provider/route | Provider and route context are not prominent enough. |
| Cost cell | Cost and provider can visually collide. |
| Row actions | Only request ID is clearly clickable; full row should be selectable. |
| Active run | Banner exists but should become a mini-dashboard. |
| Detail navigation | Request detail is powerful but long and vertically stacked. |

### 5.2 Current Run UI

Current strengths:

- Shows active run state.
- Shows aggregate run metrics.
- Includes what-if cost comparison.
- Shows models, endpoints, status codes, signals, and run traffic.
- Live polling is available.

Current issues:

| Area | Problem |
|---|---|
| Vertical order | What-if cost can push live traffic too low, especially on narrow screens. |
| What-if table | Too many columns for default view. |
| Run health | Error and success-rate information should be visible at top. |
| Metric definitions | `Run open`, `LLM wall time`, and `Request duration` need clearer explanations. |
| Mobile | Dense desktop table patterns do not work well on mobile. |

### 5.3 Target UI

The target UI should provide:

- A debug-first Request Browser with compact semantic rows.
- Clickable summary chips for common filters.
- Provider and route filters.
- A right-side selected-request inspector on desktop.
- A polished Run in Progress dashboard with health, cost, models, signals, insights, and recent traffic.
- A mobile run dashboard that is fully usable without horizontal scrolling.

---

## 6. Request Browser v2 — Desktop Design

### 6.1 Page Purpose

The Request Browser is the main traffic exploration screen. It should help users scan all captured traffic and quickly narrow down to interesting requests.

### 6.2 Page Header

Top content:

```text
OPENAI-COMPATIBLE TRAFFIC
Request Browser
```

Right-aligned or below-title filter chips:

```text
2.97k Total
2.91k Streams
0 Images
2.94k Tools
2 Errors
184 Slow >10s
```

Requirements:

- Chips should be visually clickable.
- Clicking a chip applies the corresponding filter.
- Active chip should remain highlighted.
- Chips should be based on current data scope unless explicitly designed as global counters.

### 6.3 Active Run Mini-dashboard

When a run is active, show a concise run card:

```text
RUN IN PROGRESS
codegoropher deepseek

112 requests · 3h 12m open · 2 errors · 106 tool calls

Avg latency: 1.82s
Avg TPS: 58.47
Total tokens: 1.12M
Estimated cost: $0.0667

[End run]
```

Requirements:

- Keep this card compact.
- Show error count if non-zero.
- `End run` must be red/danger.
- Run name should link to the run detail page.
- If no run is active, show a compact `Start run` form.

### 6.4 Filter Bar

Fields:

| Field | Type | Notes |
|---|---|---|
| Endpoint | Input / datalist | Example `/v1/chat/completions` |
| Model | Select | Any model |
| Provider | Select | Any provider |
| Route | Select | Any route |
| Run | Select | Any run |
| Status | Select/input | Any status or specific HTTP status |

Quick filter chips:

- Stream
- Tool
- Image
- Error
- Slow >10s
- Large >10k tokens

Actions:

- `Filter`
- `Reset`

Requirements:

- Filters should update URL query parameters.
- Filters should work with live polling.
- Filter controls should not shift layout on refresh.
- Provider and route filters depend on provider/routing metadata being available.

### 6.5 Table Controls

Above the table, include:

```text
Columns ▾
```

Future column presets:

- Default
- Cost
- Tools
- Raw
- Performance

First implementation can show the button without implementing full customization, but it should not break layout.

### 6.6 Main Requests Table

Target columns:

| Column | Content |
|---|---|
| Request | Request ID, local date/time, method, endpoint |
| Model / Provider | Incoming model, provider, route/upstream if available |
| Run | Run badge |
| Status | HTTP status pill |
| Performance | Duration and TPS |
| Tokens | Input / Output / Total |
| Cost | Cost value, provider beneath |
| Signals | Stream / Tool / Image / Error / Slow badges |
| Summary | Semantic preview |

#### Example row

```text
#2972
24 May 2026 10:56:30
POST /v1/chat/completions

Qwen/Qwen3.6-35B-A3B
DeepSeek

codegoropher deepseek

200

842 ms
42.76 TPS

1.24k IN
36 OUT
1.28k TOTAL

$0.000026
DeepSeek

Stream
Tool

Streaming response · Tool call: read_file
```

### 6.7 Row States

Use visual row states:

| State | Visual |
|---|---|
| Selected | Pale teal background |
| Error | Red status pill and/or red left accent |
| Slow | Orange duration text and slow badge |
| Streaming | Blue stream badge |
| Tool call | Purple tool badge |

Rows should be clickable. Clicking anywhere on the row should either:

1. Open the right-side inspector, or
2. Navigate to full request detail if no inspector is implemented.

Preferred desktop behavior:

- Single click: select row and update inspector.
- Double click or `View full details`: open detail page.

### 6.8 Semantic Preview Generation

The `Summary` column should prefer semantic summaries over raw text.

Suggested logic:

1. If request errored:
   - `Server error 500 · Internal server error occurred`
2. If tool calls detected:
   - `Streaming response · Tool call: read_file`
   - `Reasoning content detected · Tool call: search_web`
3. If natural language final response exists:
   - First useful sentence or first 120 characters
4. If streaming chunks exist but no final text:
   - `Streaming response · 423 chunks`
5. If raw preview only:
   - Show sanitized short preview

Avoid showing raw SSE fragments like:

```text
data: {"id": "...", "object": "chat.completion.chunk"...}
```

in the table.

### 6.9 Cost Cell

Render cost and provider on separate visual lines:

```text
$0.000042
DeepSeek
```

Do not concatenate:

```text
$0.000042DeepSeek
```

### 6.10 Pagination

Footer:

```text
Showing 1–50 of 2.97k · 50 per page
[Previous] [1] [2] [3] ... [60] [Next]
```

Requirements:

- Pagination should preserve filters.
- Live polling should not reset the user to page 1 unless filters change.
- Consider showing pagination at top and bottom for large datasets.

### 6.11 Right-side Request Inspector

Desktop-only or wide-screen behavior.

Header:

```text
Request #2974    200 OK    [X]
```

Tabs:

- Overview
- Route / Provider
- Tokens
- Preview

Overview fields:

| Field | Example |
|---|---|
| Time | 24 May 2026, 12:15:26 |
| Method | POST |
| Endpoint | `/v1/chat/completions` |
| Run | codegoropher deepseek |
| Duration | 2.97s |
| TPS | 49.56 |
| Status | 200 OK |
| Cost | $0.000042 (DeepSeek) |

Cards inside inspector:

- Signals
- Summary
- Quick stats

Footer action:

```text
[View full details →]
```

Requirements:

- The inspector should not force horizontal scrolling.
- On smaller desktop widths, it can collapse below the table or be hidden behind row click.
- The selected table row should be highlighted.

---

## 7. Run in Progress — Desktop Design

### 7.1 Page Purpose

The Run in Progress page is the main live dashboard for an active agent/model run. It should show run health, token/cost usage, model/provider behavior, and recent traffic in one scan.

### 7.2 Header

Top section:

```text
RUN IN PROGRESS
Run: codegoropher deepseek    LIVE

Started 24 May 2026, 09:12:40
Open for 3h 12m
Status active
2 errors

[End run]
```

Requirements:

- `LIVE` badge should be green.
- `2 errors` chip should be red/orange.
- `End run` button should be red and visually separate.
- Run title should be prominent.

### 7.3 Top KPI Strip

Show compact tiles:

| Metric | Example |
|---|---|
| Requests | 112 |
| Success | 110 / 98.2% |
| Errors | 2 / 1.8% |
| Run open | 3h 12m |
| LLM wall time | 2h 59m |
| Input tokens | 1.05M / 1,054,321 |
| Output tokens | 77.9k / 77,932 |
| Total tokens | 1.12M / 1,132,253 |
| Estimated cost | $0.0667 USD |
| Output tok/s | 114.04 avg |

Requirements:

- Show errors in top strip when non-zero.
- Use icons to improve scanability.
- Add tooltips or help text for ambiguous metrics.

Suggested definitions:

| Metric | Definition |
|---|---|
| Run open | Clock time since the run started. |
| LLM wall time | Observed wall time spent in LLM calls, depending on backend metric semantics. |
| Request duration | Sum of individual request durations. |
| Output tok/s | Output tokens divided by observed generation time or request duration, depending on implementation. |

### 7.4 Tabs

Tabs:

- Overview
- Traffic
- Cost what-if
- Models
- Diagnostics

Default tab: `Overview`.

### 7.5 Overview Cards

#### Run Health

Fields:

- Success rate
- Stream count
- Tool calls
- Image requests
- Last activity

Example:

```text
Run health    98.2%

Success rate      98.2%
Stream count      106
Tool calls        106
Image requests    0
Last activity     Live · 2s ago
```

#### Top Models

Example:

```text
Qwen/Qwen3.6-35B-A3B    106
gpt-test                  6
```

#### Status Codes

Example:

```text
200    110
400      2
```

#### Signals

Example:

```text
Streams    106
Tools      106
Images       0
Errors       2
```

#### What-if Cost

The overview should show a compact what-if cost summary, not the full dense table.

Example:

```text
Current (DeepSeek)    $0.0667
GPT-5.4 Mini          $0.1524    +126.5%
GPT-5.5               $0.2141    +220.7%
```

Full detailed comparison should live in the `Cost what-if` tab.

#### Run Insights

Right-side card on desktop:

```text
Run insights       Live

Active routes
POST /v1/chat/completions    112

Top providers
DeepSeek    106
OpenAI        6

Avg latency (p50 / p95)
842 ms / 2.91 s

Busiest model
Qwen/Qwen3.6-35B-A3B
106 requests

Error rate
1.8%    2 / 112

Live updates every 1s
```

### 7.6 Recent Traffic

Show recent run traffic directly on Overview.

Columns:

| Column | Content |
|---|---|
| Request | ID and time |
| Model / Provider | Model and provider |
| Status | HTTP status |
| Performance | Duration and TPS |
| Tokens | Input / Output / Total |
| Cost | Amount and provider |
| Signals | Badges |
| Summary | Semantic preview |

Footer:

```text
Showing 1–6 of 112 requests
[View all traffic]
```

`View all traffic` should go to either:

- Run Traffic tab, or
- Request Browser filtered by `run=<id>`.

### 7.7 Traffic Tab

The Traffic tab should show the full request table for the run.

Requirements:

- Same compact table component as Request Browser.
- Run column can be omitted because all rows belong to the selected run.
- Include filters specific to this run:
  - Status
  - Model
  - Provider
  - Signals
  - Slow
  - Large token usage

### 7.8 Cost What-if Tab

The detailed what-if comparison table belongs here.

Default compact columns:

| Scenario | Provider / Model | Total cost | Delta | Missing usage |
|---|---|---:|---:|---:|

Expandable details:

- Input tokens
- Cached input tokens
- Output tokens
- Input / 1M
- Cached / 1M
- Output / 1M
- Input cost
- Output cost
- Included request count

### 7.9 Models Tab

Show model usage details:

- Requests by model
- Token usage by model
- Cost by model
- Error rate by model
- Average latency/TPS by model

### 7.10 Diagnostics Tab

Show operational diagnostics:

- Recent errors
- Slow requests
- Tool-call issues
- Missing usage rows
- Missing provider/pricing rows
- Route/provider mismatches
- Health check status if available

---

## 8. Mobile Run in Progress Design

### 8.1 Mobile Design Intent

Mobile should not be a squeezed desktop table. It should be a responsive run dashboard optimized for quick monitoring.

Primary mobile use cases:

- Check whether the run is still alive.
- Check error count and success rate.
- Check cost/tokens.
- Check recent traffic.
- End a run if necessary.

### 8.2 Mobile Header

Top:

```text
LO  LLM Observe Proxy           LA  menu
```

Avoid showing full upstream URL in mobile header unless there is enough space.

### 8.3 Mobile Run Header

```text
RUN IN PROGRESS
Run: codegoropher deepseek    LIVE

[End run]

Started 24 May 2026, 09:12:40
Open for 3h 12m
Status active
2 errors
```

Requirements:

- Metadata chips can wrap.
- `End run` should remain highly visible.
- If title is long, allow wrap to two lines.

### 8.4 Mobile KPI Grid

Use a 2-column, 3-column, or horizontal-scroll grid depending on actual viewport.

Do not require horizontal scrolling for the whole page.

Required KPIs:

- Requests
- Success
- Errors
- Run open
- LLM wall time
- Input tokens
- Output tokens
- Total tokens
- Estimated cost
- Output tok/s

Mobile layout options:

1. 2-column card grid for narrow phones.
2. 3-column grid for larger phones.
3. Horizontal KPI carousel only if clearly indicated by dots.

### 8.5 Mobile Tabs

Tabs:

```text
Overview | Traffic | Cost what-if | Models | Diagnostics
```

Behavior:

- Horizontal scroll is acceptable for tabs.
- Active tab uses teal underline.
- Keep tab labels short.

### 8.6 Mobile Overview Cards

The generated mockup uses a two-column card grid. This is acceptable on large mobile widths. For smaller phones, stack cards vertically.

Cards:

- Run health
- Top models
- Status codes
- Signals
- What-if cost
- Run insights

Requirements:

- Each card should be readable without zooming.
- Avoid tiny labels.
- Keep content concise.
- Use pills and badges for counts.

### 8.7 Mobile Recent Traffic

Use compact rows rather than a full table.

Each row should show:

```text
#29743
24 May 12:15:26

gpt-test
OpenAI

200

5 / 147 / 152

$0.000042
DeepSeek

Stream
>
```

Better mobile row structure:

```text
#29743 · 24 May 12:15:26        200
gpt-test · OpenAI
2.97s · 49.56 TPS
5 in · 147 out · 152 total
$0.000042 · DeepSeek        Stream
```

Requirements:

- Entire row should be tappable.
- Status and signal badges should be touch-readable.
- Show only 3–5 recent rows on Overview.
- `View all traffic` opens the Traffic tab or Request Browser filtered by run.

### 8.8 Mobile Bottom Status

Footer:

```text
Showing 1–5 of 112 requests
Live updates every 1s
```

Use a small live/lightning indicator.

---

## 9. Request Detail Design Direction

Although this document focuses on Request Browser and Runs, request detail should align with this direction.

Target detail structure:

```text
Request #2974
Status 200 · 2.97s · 49.56 TPS · 152 tokens · Stream

Tabs:
Overview | Request | Response | Tools | Cost | Headers | Routing
```

Overview should show:

- Route/provider
- Upstream URL
- Model and upstream model
- Performance
- Tokens
- Cost
- Signals
- Semantic summary

Request/Response tabs should provide:

- Copy button
- Pretty/raw toggle
- Wrap toggle
- Collapse large fields
- Mode tabs: auto/json/text/markdown/tool/sse

Tool tab should summarize:

- Tool call count
- Unique tools
- Malformed arguments
- Valid/invalid tool call cards

---

## 10. Data Requirements

### 10.1 Request Row Data

Each request row should ideally have:

```json
{
  "id": 2974,
  "created_at": "2026-05-24T12:15:26Z",
  "method": "POST",
  "endpoint": "/v1/chat/completions",
  "model": "gpt-test",
  "upstream_model": "deepseek-chat",
  "provider_name": "DeepSeek",
  "route_name": "global fallback",
  "task_run": {
    "id": 4,
    "name": "codegoropher deepseek"
  },
  "status": 200,
  "duration_ms": 2970,
  "tokens_per_second": 49.56,
  "tokens": {
    "input": 5,
    "output": 147,
    "total": 152,
    "cached_input": 0
  },
  "cost_usd": 0.000042,
  "signals": {
    "stream": true,
    "tool": false,
    "image": false,
    "error": false,
    "slow": false
  },
  "semantic_summary": "你好！有什么可以帮助你的吗？ 😊"
}
```

### 10.2 Run Summary Data

```json
{
  "id": 4,
  "name": "codegoropher deepseek",
  "is_active": true,
  "started_at": "2026-05-24T09:12:40Z",
  "open_duration_ms": 11520000,
  "request_count": 112,
  "success_count": 110,
  "error_count": 2,
  "success_rate": 0.982,
  "llm_wall_time_ms": 10740000,
  "total_request_duration_ms": 683000,
  "tokens": {
    "input": 1054321,
    "output": 77932,
    "total": 1132253
  },
  "estimated_cost_usd": 0.0667,
  "output_tokens_per_second": 114.04,
  "signals": {
    "streams": 106,
    "tools": 106,
    "images": 0,
    "errors": 2
  }
}
```

### 10.3 What-if Cost Data

Overview summary:

```json
[
  {
    "label": "Current (DeepSeek)",
    "total_cost_usd": 0.0667,
    "delta_percent": 0
  },
  {
    "label": "GPT-5.4 Mini",
    "total_cost_usd": 0.1524,
    "delta_percent": 126.5
  },
  {
    "label": "GPT-5.5",
    "total_cost_usd": 0.2141,
    "delta_percent": 220.7
  }
]
```

Detailed tab data should include token counts, pricing rates, input/output costs, included requests, and missing usage counts.

---

## 11. API Requirements

The UI can reuse existing endpoints where possible, but the following API shapes are useful.

### 11.1 Requests List API

Supports:

- Pagination
- Endpoint filter
- Model filter
- Provider filter
- Route filter
- Run filter
- Status filter
- Stream/image/tool/error filters
- Slow threshold filter
- Large-token threshold filter

Response:

```json
{
  "stats": {
    "total": {"value": 2970, "display": "2.97k"},
    "streams": {"value": 2910, "display": "2.91k"},
    "images": {"value": 0, "display": "0"},
    "tools": {"value": 2940, "display": "2.94k"},
    "errors": {"value": 2, "display": "2"},
    "slow": {"value": 184, "display": "184"}
  },
  "items": [],
  "pagination": {}
}
```

### 11.2 Run Detail API

Supports:

- Live polling
- Pagination for recent traffic
- Optional tab-specific payloads

Response:

```json
{
  "run": {},
  "stats": {},
  "overview": {
    "run_health": {},
    "top_models": [],
    "status_codes": [],
    "signals": {},
    "what_if_cost": [],
    "insights": {}
  },
  "items": [],
  "pagination": {}
}
```

### 11.3 Request Detail API

Supports render mode:

- auto
- json
- text
- markdown
- tool
- sse
- raw

Should include a semantic summary and routing/provider data.

---

## 12. Interaction Requirements

### 12.1 Live Polling

- Active run pages should update every 1 second by default.
- Do not poll while document is hidden.
- Abort in-flight poll if a newer refresh supersedes it.
- Preserve pagination and filters across refreshes.
- Show small live state:
  - `Live`
  - `Update failed; showing last data`
  - `Paused while tab hidden`

### 12.2 Row Click

- Desktop Request Browser:
  - Click row: select request and update inspector.
  - `View full details`: open full detail page.
- Mobile:
  - Tap row: open full request detail.

### 12.3 Filter Chips

- Clicking a summary chip applies/removes a filter.
- Active filters should be visually obvious.
- Reset clears all filters.

### 12.4 End Run

- `End run` is destructive.
- Require confirmation.
- After success:
  - Update status to completed.
  - Hide or disable `End run`.
  - Stop live active-run behavior if applicable.

Suggested confirmation text:

```text
End run "codegoropher deepseek"?
New requests will no longer be grouped into this run.
```

---

## 13. Accessibility Requirements

- All buttons and chips must be keyboard-accessible.
- Status colors must have text labels.
- Tables should use semantic headers.
- Cards should have meaningful headings.
- Focus states should be visible.
- Danger actions require confirmation.
- Inspector drawer should trap focus if implemented as modal; if persistent side panel, it should not trap focus.
- Mobile tap targets should be at least 44px high where possible.

---

## 14. Responsive Breakpoints

Suggested behavior:

### Wide desktop

- Header nav full width.
- Request Browser:
  - Table plus right-side inspector.
- Run page:
  - KPI strip single row.
  - Overview cards in multi-column layout.
  - Insights card on the right.

### Medium desktop / tablet

- Inspector may collapse.
- KPI strip wraps to two rows.
- Overview cards use two columns.
- Tables still scroll horizontally if needed, but default columns should minimize this.

### Mobile

- Header collapses.
- No desktop right-side inspector.
- KPI grid becomes 2 or 3 columns.
- Overview cards stack or use two columns if width permits.
- Recent traffic becomes list rows.
- Full table can appear only inside Traffic tab, with horizontal scroll as fallback.

---

## 15. Implementation Plan

### Phase 1: Low-risk polish

1. Separate cost and provider lines in request table.
2. Add clickable stat chips.
3. Add errors and slow request chips.
4. Add provider and route filters if backend data is available.
5. Add semantic summary field to request row API.
6. Add row selected state.
7. Add whole-row click behavior.

### Phase 2: Request Browser v2

1. Redesign table columns into compact debug-first layout.
2. Add right-side request inspector on desktop.
3. Add column/view control.
4. Add semantic summary fallback logic.
5. Improve pagination placement and preserve filters.

### Phase 3: Run in Progress v2

1. Redesign run header and KPI strip.
2. Add Overview tabs.
3. Add Run health, Top models, Status codes, Signals, What-if cost, and Run insights cards.
4. Replace full what-if table on Overview with compact summary.
5. Move detailed cost comparison into `Cost what-if` tab.
6. Add recent traffic compact table.

### Phase 4: Mobile responsive implementation

1. Create mobile header behavior.
2. Convert KPI strip into responsive grid.
3. Convert overview cards into stacked/two-column cards.
4. Convert traffic table into mobile list rows.
5. Hide desktop inspector on mobile.
6. Test touch targets and text wrapping.

---

## 16. Acceptance Criteria

### Request Browser

- User can see total, stream, image, tool, error, and slow request counts as clickable chips.
- User can filter by endpoint, model, provider, route, run, status, and signal.
- User can scan request rows without horizontal scrolling on normal desktop width.
- Cost and provider are visually separated.
- Streaming/tool previews are semantic, not raw SSE by default.
- Errors and slow requests are visually prominent.
- Selecting a row opens/updates a request inspector on desktop.
- Pagination preserves filters.

### Run in Progress

- User can immediately see run status, error count, success rate, tokens, cost, and live state.
- User can distinguish `Run open`, `LLM wall time`, and request duration via labels/tooltips.
- Overview tab summarizes health, models, status codes, signals, what-if cost, and insights.
- Recent traffic is visible without excessive scrolling on desktop.
- What-if cost is compact on Overview and detailed in its own tab.
- End run requires confirmation.

### Mobile

- Mobile screen has no page-level horizontal scrolling.
- Key run health and cost information is visible near the top.
- KPI cards are readable and touch-friendly.
- Overview cards stack cleanly.
- Recent traffic rows are readable and tappable.
- End run button is visible and usable.
- Live update status is visible.

---

## 17. Notes for Coding Agents

1. Do not chase pixel-perfect parity with generated images.
2. Preserve existing functionality while improving layout.
3. Prefer incremental refactors using shared components.
4. Keep backend response fields stable where possible.
5. Add new fields like `provider_name`, `route_name`, and `semantic_summary` without breaking existing consumers.
6. Keep raw JSON/SSE available in detail views.
7. Avoid hiding important debug information permanently; move it into tabs, drawers, or expandable details.
8. Test with large datasets, long model names, long run names, and high-frequency live updates.
9. Test with local llama.cpp, DeepSeek/OpenAI-style providers, streaming responses, and tool-calling responses.
10. Optimize for the actual workflow: watching coding agents generate many streaming tool-calling requests.

---

## 18. Suggested File/Component Structure

This depends on the existing app architecture, but a coding agent may consider:

```text
templates/
  index.html
  run_detail.html
  request_detail.html
  partials/
    _app_header.html
    _stat_chip.html
    _kpi_tile.html
    _request_table.html
    _request_row.html
    _run_overview_cards.html
    _mobile_request_item.html

static/
  app.js
  live.js
  filters.js
  request-inspector.js
  responsive.css
```

If staying with the current template structure, keep the changes localized:

- Update request table partial.
- Update run detail template.
- Extend live rendering JS.
- Add CSS classes for compact rows, inspector drawer, KPI grid, and mobile layout.

---

## 19. Open Questions

Agents should verify these details before finalizing backend changes:

1. What exactly is the definition of `LLM wall time`?
2. Should `Output tok/s` use total output tokens divided by request duration, generation duration, or LLM wall time?
3. Should `Errors` include only HTTP 5xx, or also 4xx?
4. Should slow threshold default to 10 seconds, or be configurable?
5. Should semantic summaries be computed at capture time or render time?
6. Should provider/route filters use captured request metadata or current route/provider configuration?
7. Should live polling pause if the user is interacting with filters or the inspector?
8. Should mobile show the full nav row or collapse into a menu?

