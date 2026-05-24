# LLM Observe Proxy UI Review: Runs and Request Browser

## Purpose

This document captures a usability review of the updated **Runs** and **Request Browser** sections of `llm-observe-proxy`.

It is intended to be handed to a coding agent together with the screenshots so the agent can plan UI and backend changes. The review focuses on the live run dashboard, request browser table, request detail experience, and cost/traffic observability workflows.

Repository: `https://github.com/shamitv/llm-observe-proxy`

---

## 1. Overall Verdict

The updated **Runs** and **Requests** UI is a solid step forward. The app has moved from a mostly static request table toward a **live observability dashboard**.

The strongest improvements are visible in the run detail page:

- Live polling
- Strong run summary header
- What-if cost comparison
- Model / endpoint / status / signal breakdowns
- Embedded run traffic table
- Per-request token, cost, status, and signal information

The main remaining issue is **horizontal and vertical density**. The UI is now functionally rich, but Requests and Run Traffic still feel table-heavy and require horizontal scrolling. That is acceptable for a raw debug mode, but the default view should help answer key operational questions faster:

- What happened?
- Was the run healthy?
- Which requests failed?
- Which requests were slow?
- Which model/provider/route was used?
- Did tool calling work?
- What did this run cost?
- What would this run have cost on another model?

---

## 2. What Is Working Well

### 2.1 Run detail page is much more useful

The run summary at the top is strong. It shows:

- Requests
- LLM wall time
- Run open duration
- Total request duration
- Input tokens
- Output tokens
- Total tokens
- Estimated cost
- Output tokens per second

This is exactly the right direction. For agent runs, aggregate metrics matter more than individual request rows at first glance.

### 2.2 What-if cost is a valuable feature

The **What-if cost** panel is a strong differentiator.

It lets users compare the observed run usage against alternative pricing scenarios such as:

- GPT-5.5
- GPT-5.4 Mini
- Other configured model/provider pricing rows

This turns the proxy into a cost analysis tool, not just a request logger.

The current what-if table captures important fields:

- Scenario
- Input tokens
- Cached input
- Output tokens
- Input / 1M
- Cached / 1M
- Output / 1M
- Input cost
- Output cost
- Total cost
- Included requests
- Missing usage

This is analytically useful, but should be made more compact in the default view.

### 2.3 Live updates are useful

The live run page is much better for monitoring active coding-agent runs. Live refresh is particularly useful when CodeGopher, Cline, Qwen Code, or another agent is continuously sending requests.

Good behavior visible in the UI:

- Run dashboard updates while active
- Run Traffic table updates
- Active run state is clearly shown
- Pagination works with live data
- Request counts and cost summaries remain visible

### 2.4 Request rows contain the right raw data

The request table includes the right core fields:

- Time
- Endpoint
- Model
- Run
- Status
- Duration
- TPS
- Tokens
- Cost
- Signals
- Preview

This is a good foundation for an LLM observability tool.

---

## 3. Biggest Usability Issues

### 3.1 Run page becomes too vertically long on narrow screens

On narrower screens, the run page becomes a long vertical sequence:

1. Run summary
2. What-if cost
3. Models
4. Endpoints
5. Status Codes
6. Signals
7. Run Traffic

This is readable, but it pushes the live request traffic too far down.

For a live run, the priority should be:

```text
Run health → cost/tokens → anomalies → recent traffic
```

Current order:

```text
Run summary → What-if cost → Models → Endpoints → Status Codes → Signals → Requests
```

Recommended order for narrow screens:

```text
Run summary
Run traffic
Breakdowns: Models / Status / Signals
What-if cost
```

For desktop-wide layouts, What-if cost can stay high. For narrow layouts, it should be collapsible or moved lower.

---

### 3.2 What-if cost table is horizontally heavy

The what-if table has too many columns for a default dashboard view.

Current visible detail is useful, but dense:

```text
Scenario
Input tokens
Cached input
Output tokens
Input / 1M
Cached / 1M
Output / 1M
Input cost
Output cost
Total cost
Included
Missing usage
```

Recommended compact default:

| Scenario | Provider / Model | Total Cost | Delta vs Current | Missing Usage |
|---|---|---:|---:|---:|
| GPT-5.5 | OpenAI / gpt-5.5 | $7.57 | +$7.50 | 2 |
| GPT-5.4 Mini | OpenAI / gpt-5.4-mini | $1.13 | +$1.06 | 2 |
| Current | DeepSeek / current | $0.0667 | Baseline | 0 |

Then expand a row to show:

- Input tokens
- Cached input tokens
- Output tokens
- Input / 1M
- Cached / 1M
- Output / 1M
- Input cost
- Output cost

This would preserve analytical power while improving scanability.

---

### 3.3 Request table still requires horizontal scrolling

The request table remains too wide, especially because the **Preview** column sits at the far right and often gets clipped.

Current columns:

```text
Time
Endpoint
Model
Run
Status
Duration
TPS
Tokens
Cost
Signals
Preview
```

Recommended default columns:

| Column | Content |
|---|---|
| Request | Request ID, time, method, endpoint |
| Model / Provider | Incoming model, upstream model, provider, route |
| Status | HTTP status and error state |
| Performance | Duration and TPS |
| Tokens | Input / output / total |
| Cost | Amount and billing provider |
| Signals | Stream / Tool / Image / Error |
| Summary | Semantic preview |

This reduces horizontal pressure while preserving the same information.

---

### 3.4 Preview is still too raw for streaming rows

For streaming rows, the Preview column often contains raw SSE JSON such as:

```text
data: {"id":"...", "object":"chat.completion.chunk"...}
```

That is useful in detail view, but not in the table.

The table preview should be semantic:

```text
Assistant: 你好！有什么可以帮你的吗？
Tool call: read_file(...)
Streaming response · 42 chunks
Reasoning content detected
```

Recommended derived fields:

- `summary_preview`
- `first_text_preview`
- `tool_call_summary`
- `stream_chunk_count`
- `reasoning_detected`
- `final_finish_reason`

The raw SSE should remain available in Request Detail.

---

### 3.5 Cost/provider text visually collides

In the request table, cost and provider sometimes visually merge:

```text
$0.000042DeepSeek
```

Recommended rendering:

```text
$0.000042
DeepSeek
```

CSS suggestion:

```css
.cost-provider {
  display: block;
  margin-top: 2px;
}
```

Or render the provider as a separate muted line below the cost.

---

### 3.6 Long run names consume too much row space

The run badge `codegoropher deepseek` wraps into a large pill in the Request Browser table.

Recommended behavior:

```text
codegoropher…
```

With full run name in a tooltip.

CSS suggestion:

```css
.run-badge {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

In Run Detail, the run column can remain hidden because the whole page is already scoped to one run.

---

### 3.7 Run summary needs Errors and Success Rate

The top run stat strip should include operational health, especially when non-zero errors exist.

Current breakdown shows Status Codes lower down, but important errors can be below the fold.

Add to the run header:

```text
Errors: 2
Success rate: 98.2%
HTTP 400: 2
```

Recommended dynamic behavior:

- Always show `Errors` if error count > 0.
- Show `Success rate` when request count > 0.
- Highlight non-2xx status codes with warning color.

---

### 3.8 Metric definitions need tooltips

The run header contains metrics that are valuable but easy to confuse:

- Run open
- LLM wall time
- Request duration

Add small tooltip/help text:

| Metric | Suggested Explanation |
|---|---|
| Run open | Elapsed time since the run started. |
| Request duration | Sum of observed request durations. |
| LLM wall time | Observed model processing time / wall time according to captured request metrics. |
| Output tok/s | Output tokens divided by observed LLM/request generation duration. |

This is important because values like `LLM wall time: 2h 59m` and `Request duration: 11m 23s` can look contradictory without definitions.

---

## 4. Suggested Run Page Redesign

### 4.1 Desktop Run Header

Recommended structure:

```text
Run: codegoropher deepseek                                      [End run]
Started 24 May 2026, 09:12:40 · Active · Live

[Requests 112] [Errors 2] [Success 98.2%] [Input 1.05M] [Output 77.9k]
[Total 1.12M] [Cost $0.0667] [Output tok/s 114.04]
[Run open 3h10m] [LLM wall time 2h59m]
```

### 4.2 Add Run Detail Tabs

Recommended tabs:

```text
Overview | Traffic | Cost What-if | Models | Diagnostics
```

### 4.3 Overview Tab

Show compact cards:

```text
Traffic Health
112 requests
110 success
2 client errors
106 streams
106 tools
0 images

Top Models
Qwen/Qwen3.6-35B-A3B    106
gpt-test                  6

Cost Summary
Current estimate          $0.0667
GPT-5.4 Mini what-if      $1.13
GPT-5.5 what-if           $7.57
```

### 4.4 Traffic Tab

Show the request table with a compact default column set and an optional column chooser.

### 4.5 Cost What-if Tab

Move the detailed what-if table here, or keep a compact summary on Overview with an expandable detailed view.

---

## 5. Suggested Request Browser Improvements

### 5.1 Add Quick Filter Chips

The Request Browser already shows chips like:

```text
2.97k Total
2.91k Streams
0 Images
2.94k Tools
```

Make these clickable filters.

Add additional chips:

```text
Errors
Slow > 10s
Large > 10k tokens
No provider
```

### 5.2 Add Provider and Route Filters

After the provider/routing redesign, the Request Browser should expose:

```text
Provider: Any provider
Route: Any route
```

This is important for debugging:

- fallback behavior
- provider selection
- route matching
- unexpected costs
- latency differences between providers

### 5.3 Add a Column Preset / Column Chooser

The full table is useful, but not every workflow needs all columns.

Recommended presets:

| Preset | Columns |
|---|---|
| Default | Request, Model, Status, Performance, Tokens, Cost, Signals, Summary |
| Cost | Request, Model, Provider, Tokens, Cost, Pricing tier |
| Tools | Request, Model, Tool count, Signals, Tool preview |
| Performance | Request, Model, Duration, TPS, Token rate, Status |
| Raw | Existing full table |

### 5.4 Make the Whole Row Clickable

Rows should be clickable, not only the `#2974` link.

Requirements:

- Clicking a row opens Request Detail.
- Clicking an explicit link/button inside the row should preserve its own behavior.
- Add hover state to communicate clickability.
- Optional: add external-link icon on hover to open in a new tab.

### 5.5 Improve Search

Add a free-text search field that can search:

- request ID
- model
- provider
- route
- endpoint
- preview text
- error text
- tool name
- run name

---

## 6. Suggested Request Detail Improvements

Although the user asked specifically about Runs and Requests, Request Detail is tightly connected to this workflow.

### 6.1 Add Sticky Summary Header

Recommended header:

```text
POST /v1/chat/completions
Request #2972

Status 200
Duration 842 ms
TPS 42.76
Tokens 1.28k
Run codegoropher deepseek
Model Qwen/Qwen3.6-35B-A3B
Provider DeepSeek
Route qwen-* or global fallback
```

Actions:

```text
[Copy curl] [Copy request JSON] [Copy response] [Back to list]
```

### 6.2 Add Tabs

Recommended tabs:

```text
Overview | Request | Response | Tools | Stream | Cost | Headers | Routing
```

### 6.3 Overview Tab

Show compact cards:

```text
Routing
Route: global fallback
Provider: DeepSeek
Upstream: http://...
Model: Qwen/Qwen3.6-35B-A3B

Performance
Duration: 842 ms
TPS: 42.76
Streaming: yes
Chunks: 423

Tokens
Input: 1.24k
Output: 36
Total: 1.28k

Tool calls
Detected: yes
Count: 18
Malformed: 7
```

### 6.4 Tools Tab

The tool-call view should summarize tool calls before showing raw payloads.

Recommended summary:

```text
Tool calls detected: 18
Unique tools: read_file, list_dir, glob_search
Malformed arguments: 7
First valid tool call: read_file
```

Recommended card format:

```text
#1 read_file
Status: valid
Arguments:
  path: /Users/...

Raw JSON [collapsed]
```

### 6.5 Stream Tab

For SSE responses, provide a stream timeline:

```text
Chunk 1: role assistant
Chunk 2: reasoning_content: "Here"
Chunk 3: reasoning_content: "'s"
...
Final: stop / tool_calls / unknown
```

This will be much easier to debug than raw SSE text in the default view.

---

## 7. Specific Design Fixes

### Fix 1: Put Run Traffic closer to the summary

For active runs, recent traffic is very important. On narrow screens, move Run Traffic above What-if Cost or collapse What-if Cost by default.

### Fix 2: Keep pagination visible

For thousands of rows, pagination should appear at both top and bottom.

Recommended compact top pagination:

```text
1–50 of 2.97k    [Prev] [1] [2] [3] [Next]
```

### Fix 3: Improve loading and error states

Current loading states are fine, but API failure should show actionable controls:

```text
Could not refresh run traffic.
[Retry now]
```

### Fix 4: Reduce card height on narrow screens

On narrow screens, stat cards consume a lot of vertical space. Use either:

- compact two-column grid, or
- horizontally scrollable summary strip, or
- grouped metric rows

### Fix 5: Add sticky context while scrolling

When scrolling a long Run Detail page, keep a small sticky context bar:

```text
codegoropher deepseek · active · 112 requests · live
```

---

## 8. High-Priority Implementation Checklist

1. Fix cost/provider spacing in request rows.
2. Make stats chips clickable filters.
3. Add Provider and Route filters on Request Browser.
4. Add compact request table preset to reduce horizontal scrolling.
5. Add semantic preview for SSE/tool rows.
6. Add Errors and Success Rate to the run header.
7. Collapse What-if cost by default on narrow screens.
8. Add compact What-if summary table with expandable details.
9. Add tooltip/help text for Run open vs LLM wall time vs Request duration.
10. Make the whole request row clickable.
11. Add top pagination for large tables.
12. Add sticky run context while scrolling.
13. Add Request Detail tabs for Overview / Request / Response / Tools / Stream / Cost / Headers / Routing.
14. Add copy actions for request, response, curl, and upstream URL.
15. Add malformed tool-call detection and summary.

---

## 9. Recommended Next Mockups

### 9.1 Run Detail v2

Create an image/mockup with:

- Sticky run header
- Overview / Traffic / Cost What-if tabs
- Compact run health cards
- Error/success summary in header
- Request table lower on page
- Collapsible what-if cost section
- Compact what-if summary table

### 9.2 Request Browser v2

Create an image/mockup with:

- Clickable filter chips
- Provider and route filters
- Compact table layout
- Semantic preview column
- Optional right-side selected-request preview drawer
- Column preset menu

---

## 10. Acceptance Criteria

### 10.1 Runs

- Run detail page clearly communicates active/completed status.
- Run summary shows request count, token totals, cost, throughput, and errors.
- User can understand the difference between Run open, LLM wall time, and Request duration.
- User can see model, endpoint, status, and signal breakdowns.
- User can compare run cost against alternative models/providers.
- What-if cost is readable without horizontal scrolling in the default view.
- Live updates continue without disrupting the user’s current page position.

### 10.2 Request Browser

- User can quickly filter by stream, tool, image, error, provider, route, model, status, and run.
- Stats chips act as shortcuts to common filters.
- Request table is usable without horizontal scrolling in the default preset.
- Cost and provider are visually separated.
- Run badges do not cause excessive row height.
- Preview column shows semantic summaries instead of raw SSE whenever possible.
- Whole row click opens Request Detail.

### 10.3 Request Detail

- User can see the most important request facts without scrolling.
- Request/response content can be copied easily.
- Tool calls are summarized before raw payloads.
- SSE streams are shown as a timeline or chunk list.
- Cost and routing details are promoted to first-class sections.
- Headers remain available but do not dominate the default view.

---

## 11. Final Recommendation

The current Runs and Requests implementation is already useful and technically strong. The next improvements should not remove detail; they should **change the default presentation from raw tables to debugging workflows**.

The product should support two modes:

1. **Overview mode**
   - Fast answers
   - Health, cost, errors, traffic, and summaries

2. **Raw inspection mode**
   - Full table
   - Full request/response JSON
   - Headers
   - Raw SSE
   - Pricing snapshots

This will make `llm-observe-proxy` feel like a purpose-built LLM observability console rather than a generic admin table.
