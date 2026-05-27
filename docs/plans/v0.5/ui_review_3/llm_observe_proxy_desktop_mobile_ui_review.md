# LLM Observe Proxy UI Review: Desktop + Mobile Requests/Runs

## Purpose

This review covers the current desktop and mobile implementation of the `LLM Observe Proxy` **Requests** and **Runs** areas, based on the latest screenshots.

The goal is to provide an actionable review that a coding agent can use to improve the UI implementation. The focus is usability, information density, wasted space, responsive behavior, and observability workflows.

---

## Executive Summary

The desktop implementation is moving in the right direction: the Requests page now has stronger filter controls, provider/route awareness, a request inspector, and a more useful compact request table. The Run detail page now behaves more like a live dashboard rather than a plain table.

The mobile implementation is functional, but it currently behaves too much like a desktop layout squeezed into a narrow viewport. The main problems are:

1. Too much vertical wasted space.
2. Tables remain table-like on mobile.
3. Filter controls are too tall.
4. Runs list still uses desktop table columns and horizontal scrolling.
5. Request rows repeat low-value information across many lines.
6. The active run card is too large relative to the information it contains.
7. Navigation and summary chips consume too much space before users reach traffic.

The highest-value improvement is to implement **separate mobile layouts**, not just responsive wrapping of the desktop table.

---

# 1. Screens Reviewed

The screenshots show these main states:

## Request Browser, mobile

- Header with product name and nav buttons.
- Request Browser title.
- Summary chips: Total, Streams, Images, Tools, Errors, Slow >10s, Large >10k tok.
- Active run card.
- Filter form with Endpoint, Model, Provider, Route, Run, Status, and checkboxes.
- Compact request rows.

## Runs page, mobile

- Header with product name and nav buttons.
- Runs title.
- Summary chips: Shown, Active.
- Active run card.
- Runs table with columns: Run, Status, Requests, LLM wall time, Total tokens, Cost.
- Horizontal scrolling.

## Request Browser / Run detail, desktop

- Wide header and top nav.
- Active run summary.
- Filter controls.
- Request table.
- Right-side request inspector.
- Run overview and recent traffic.

---

# 2. Overall Assessment

## What is working well

The current implementation has several strong foundations:

- The visual style is consistent: white cards, teal accent, rounded pills, clean tables.
- The Requests page has the right observability dimensions: model, provider, route, status, performance, tokens, cost, and signals.
- The Run detail page has the right aggregates: requests, success, errors, run time, token usage, cost, and throughput.
- Provider and route concepts are now visible in request rows, which is important for a proxy.
- Request inspector on desktop is useful.
- Summary chips are useful and should become more interactive.

## Main remaining issue

The UI still treats desktop and mobile as mostly the same layout. On mobile, the page should become a **stacked monitoring feed**, not a squeezed table.

Mobile users need a fast path to answer:

- Is the run healthy?
- Are there errors?
- What changed recently?
- What requests are currently happening?
- Which model/provider is being used?
- Which requests are expensive, slow, or failed?

They should not need to scroll through large forms or horizontally scroll tables to answer those questions.

---

# 3. Desktop Review

## 3.1 Request Browser Desktop

### What works

The desktop Request Browser has improved a lot:

- The top summary chips are useful.
- Provider and route filters are present.
- Request rows are more semantic than before.
- The right-side inspector is valuable.
- Selected row state is visible.
- Cost/provider separation is better than the earlier implementation.

### Issues

#### 3.1.1 Horizontal scroll still appears

The table still needs horizontal scrolling in some desktop screenshots. This is especially visible when the right inspector is open.

This should be avoided for the default desktop view.

Recommended behavior:

When the inspector is open, use fewer table columns:

```text
Request | Model / Provider | Run | Status | Performance | Tokens | Cost
```

Move `Signals` and `Summary` primarily into the inspector.

Alternative:

- Keep table full-width.
- Open the inspector as a slide-over drawer only when a row is clicked.

#### 3.1.2 Too many row-level detail actions

The row currently includes a visible `View full details` link in the Summary area. This becomes repetitive.

Recommended interaction:

```text
Single click row      -> select row and update inspector
Double click / Enter  -> open full request detail
Open button           -> open full detail page
```

Remove repeated `View full details` links from every row. Use a chevron or inspector action instead.

#### 3.1.3 Request rows are still taller than necessary

The Request column often stacks:

```text
#2974
24 May 2026
12:15:26
POST
/v1/chat/completions
```

Compact version:

```text
#2974 · 24 May 12:15:26
POST /v1/chat/completions
```

This will reduce vertical row height significantly.

#### 3.1.4 `Signals: None` should be quieter

A `None` signal draws attention even when nothing important happened.

Use:

```text
—
```

or leave the cell blank.

Only show signal pills when there is a meaningful signal:

```text
Stream
Tool
Image
Error
Slow
Large
```

#### 3.1.5 Summary text needs clamping

Long Chinese or English summaries should be clamped to 1–2 lines in table rows.

Suggested CSS:

```css
.request-summary {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

Full content should live in the inspector or detail page.

---

## 3.2 Desktop Request Inspector

### What works

The right-side inspector is a strong addition. It makes the table feel interactive and avoids forcing users into a detail page for every click.

### Improvements

#### Make the inspector sticky

```css
.request-inspector {
  position: sticky;
  top: 96px;
  max-height: calc(100vh - 120px);
  overflow: auto;
}
```

#### Promote provider/route in Overview

Because this is an LLM proxy, route/provider data should be first-class.

Add to Overview:

```text
Provider: DeepSeek
Route: global fallback
Upstream: /v1/chat/completions
Forwarded model: ...
Compatibility fixes: ...
```

Do not hide all of this behind `Route / Provider`.

#### Add copy/open actions

Useful actions:

```text
Open full details
Copy request ID
Copy request JSON
Copy response
Copy as curl
```

---

## 3.3 Run Detail Desktop

### What works

The Run detail dashboard is much closer to the target design:

- Good top-level run title.
- Strong KPI strip.
- Clear tabs.
- Good overview cards.
- Recent traffic section is useful.
- Live state is visible.

### Issues

#### What-if baseline appears semantically confusing

If the run is currently using DeepSeek and the current cost is `$0.0667`, the comparison card should treat the current run as baseline.

Recommended:

```text
Current: DeepSeek / Qwen3.6       $0.0667
GPT-5.4 Mini                      $1.13     +1594%
GPT-5.5                           $7.57     +11250%
```

If GPT-5.5 is intentionally used as comparison baseline, label that explicitly:

```text
Comparison baseline: GPT-5.5
Current run: DeepSeek / Qwen3.6
```

#### Overview cards have uneven density

Cards such as Top Models, Status Codes, and Signals can look sparse on wide screens.

Recommended:

- Use a compact grid.
- Reduce fixed card height.
- Allow cards to auto-size.
- Let larger cards span columns only when needed.

#### Errors need stronger visual prominence

If errors are non-zero, the error KPI should be visibly emphasized:

```css
.kpi-card.error {
  background: #fff5f5;
  border-color: #fecaca;
}
```

---

# 4. Mobile Review

## 4.1 High-Level Mobile Problem

The mobile implementation is readable but wastes too much space. The layout appears to be a desktop dashboard wrapped into a single column.

The main mobile rule should be:

> On mobile, show summaries as compact cards and tables as stacked list items.

Do not render wide tables on mobile unless they are inside an intentional horizontal data viewer.

---

# 5. Mobile Request Browser Review

## 5.1 Header and Navigation

### Current issue

The header consumes a lot of space:

- Product logo/title row.
- Full nav row with Requests, Runs, Settings, Health.
- Then page title.
- Then summary chips.

This pushes the actual request traffic far down the page.

### Recommendation

On mobile, use:

```text
[LO] LLM Observe Proxy          [menu]
```

Then a compact active section switcher:

```text
Requests | Runs | Settings | Health
```

or hide secondary nav behind the menu and show only current section.

Suggested mobile header:

```text
LO  Request Browser        [menu]
2.97k requests · Live
```

The full product name can be shown in a drawer or smaller text.

---

## 5.2 Summary Chips

### Current issue

The summary chips wrap across multiple rows:

```text
2.97k Total
2.91k Streams
0 Images
2.94k Tools
27 Errors
1.46k Slow >10s
2.88k Large >10k tok
```

This is useful but takes vertical space.

### Recommendation

Use horizontal scrolling chips:

```css
.mobile-chip-row {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  white-space: nowrap;
  padding-bottom: 4px;
}
```

The chip row should stay one line tall.

Also make chips clickable filters.

---

## 5.3 Active Run Card

### Current issue

The active run card is large but contains little information:

```text
RUN IN PROGRESS
codegoropher deepseek
112 requests · 4h 41m open
End run
```

The `End run` button uses a full row and creates a lot of empty space.

### Recommendation

Make the active run card compact:

```text
Run in progress
codegoropher deepseek        [End]
112 req · 4h 41m · 27 errors
```

Use a smaller danger button:

```css
.mobile-end-run {
  padding: 8px 12px;
  min-height: 36px;
}
```

On mobile, a destructive action should still be available, but it does not need a full-width button unless the user opens the run detail page.

---

## 5.4 Filter Form

### Current issue

The mobile filter form is the largest source of wasted space.

Each checkbox appears as a full-width pill row:

```text
[ ] Streaming
[ ] Tools
[ ] Images
[ ] Errors
[ ] Slow >10s
[ ] Large >10k tok
```

This consumes too much vertical height.

### Recommendation

Use a collapsed filter drawer by default.

Default state:

```text
[Search / endpoint]        [Filters]
Active: Status 200 · Live
```

When expanded:

```text
Model       Provider
Route       Run
Status
[Stream] [Tool] [Image] [Error]
[Slow >10s] [Large >10k]
[Apply] [Reset]
```

Signal filters should be chips, not full-width checkbox rows.

Suggested mobile filter layout:

```html
<section class="mobile-filter-bar">
  <input placeholder="Search requests, model, endpoint..." />
  <button>Filters</button>
</section>
```

Expanded panel:

```html
<div class="mobile-filter-drawer">
  <select>Model</select>
  <select>Provider</select>
  <select>Route</select>
  <select>Run</select>
  <select>Status</select>

  <div class="chip-grid">
    <button>Stream</button>
    <button>Tool</button>
    <button>Image</button>
    <button>Error</button>
    <button>Slow >10s</button>
    <button>Large >10k</button>
  </div>
</div>
```

---

## 5.5 Mobile Request Rows

### What works

The mobile request rows are much better than the original table. They show:

- Request ID
- Time
- Model
- Provider
- Status
- Duration
- TPS
- Cost
- Provider
- Chevron

### Issues

#### Date formatting bug / awkward formatting

The screenshot shows date/time as:

```text
24 May
202612:15:26
```

This needs fixing.

Use:

```text
24 May · 12:15:26
```

or:

```text
24 May 12:15
```

#### Rows still look like table columns

The row is laid out as small columns, which can become cramped.

Better mobile row:

```text
#2974 · 24 May 12:15:26              200
gpt-test · DeepSeek
2.97s · 49.56 TPS · $0.000042
5 in · 147 out · 152 total           Stream >
```

For tool/stream rows:

```text
#2972 · 24 May 10:56:30              200
Qwen/Qwen3.6-35B-A3B · DeepSeek
842ms · 42.76 TPS · $0.000026
1.24k in · 36 out · 1.28k total      Stream Tool >
```

For error rows:

```text
#2958 · 24 May 10:37:11              500
Qwen/Qwen3.6-35B-A3B · DeepSeek
1.14s · $0.000000
Server error                         Error >
```

This is more natural on mobile than a table.

---

# 6. Mobile Runs Page Review

## 6.1 Main Issue: Runs Table Still Behaves Like Desktop

The Runs page has a horizontal table with columns:

```text
Run | Status | Requests | LLM wall time | Total tokens | Cost
```

On mobile this causes horizontal scrolling and large wasted row height.

### Recommendation

Replace mobile runs table with stacked run cards.

Example:

```text
codegoropher deepseek              active
24 May 2026 · 09:12:40
112 requests · 1.12M tokens · $0.0667
LLM wall time 2h 59m
[Open]
```

Another completed run:

```text
HF Upstream test                   complete
23 May 2026 · 22:39:13
106 requests · 5.14M tokens · $0.8066
LLM wall time 1h 56m
[Open]
```

For very large runs:

```text
Interview app V2                   complete
20 May 2026 · 09:14:59
2.73k requests · 171M tokens
LLM wall time 2d 13h
Cost unavailable
[Open]
```

No horizontal scroll should be needed.

---

## 6.2 Active Run Card on Runs Page

Same issue as Request Browser: the active run card is too tall for its content.

Recommended compact version:

```text
Run in progress
codegoropher deepseek
112 requests · 4h 41m open
[Open] [End]
```

Use side-by-side compact buttons.

---

## 6.3 Runs Summary Chips

Current:

```text
4 Shown
1 Active
```

Good, but add:

```text
Total requests
Total tokens
Total cost
```

If screen space is tight, make this a horizontal scroll chip row.

---

# 7. Mobile-Specific Layout Requirements

## 7.1 Breakpoints

Use explicit layout breakpoints.

Recommended:

```css
:root {
  --mobile-max: 767px;
  --tablet-min: 768px;
  --desktop-min: 1024px;
}
```

At `max-width: 767px`:

- Hide desktop table layout.
- Use mobile card/list layout.
- Collapse filters.
- Use horizontal chip rows.
- Avoid `min-width` table shells.
- Remove horizontal scroll except for chip rows.

## 7.2 Mobile Request List Component

Create a separate mobile component instead of relying on the same desktop table.

Desktop:

```html
<table class="requests-table desktop-only">...</table>
```

Mobile:

```html
<div class="request-card-list mobile-only">
  <article class="request-card">...</article>
</div>
```

CSS:

```css
.desktop-only {
  display: block;
}

.mobile-only {
  display: none;
}

@media (max-width: 767px) {
  .desktop-only {
    display: none !important;
  }

  .mobile-only {
    display: block;
  }
}
```

## 7.3 Mobile Run List Component

Same pattern:

```html
<table class="runs-table desktop-only">...</table>

<div class="run-card-list mobile-only">
  <article class="run-card">...</article>
</div>
```

---

# 8. Wasted Space Analysis

## 8.1 Request Browser Mobile

Major sources of wasted vertical space:

| Area | Issue | Fix |
|---|---|---|
| Header/nav | Product title + full nav consumes too much height | Compact header, move nav to menu or horizontal slim tabs |
| Summary chips | Wraps into multiple rows | One-line horizontal scroll chips |
| Active run card | Large white card with little info | Compact card with inline End button |
| Filter controls | Every field and checkbox is full-width | Collapsible filter drawer; chip grid |
| Checkbox pills | Six full-width rows | Compact toggle chips |
| Request rows | Date/time and endpoint stacked too much | Mobile request card format |
| Runs table | Desktop table causes horizontal scroll | Mobile run cards |

## 8.2 Runs Mobile

Major sources of wasted space:

| Area | Issue | Fix |
|---|---|---|
| Active run card | End button takes its own large block | Inline Open/End actions |
| Runs table rows | Each row is very tall because cells wrap | Replace with run cards |
| Horizontal scroll | Not mobile-friendly | Remove table layout on mobile |
| Columns | Too many desktop columns | Show key stats in card summary |

---

# 9. Recommended Mobile Layouts

## 9.1 Request Browser Mobile Target

```text
Header
LO Request Browser                         [menu]

Stats chip row
[2.97k Total] [2.91k Streams] [27 Errors] [1.46k Slow] ...

Active run compact card
codegoropher deepseek                      [End]
112 req · 4h 41m · 27 errors

Search/filter compact
[Search endpoint/model...]                 [Filters]

Active filters
Status 200 ×  Stream ×

Request cards
#2974 · 24 May 12:15:26              200
gpt-test · DeepSeek
2.97s · 49.56 TPS · $0.000042
5 in · 147 out · 152 total           >

#2972 · 24 May 10:56:30              200
Qwen/Qwen3.6-35B-A3B · DeepSeek
842ms · 42.76 TPS · $0.000026
1.24k in · 36 out · 1.28k total
Stream · Tool                         >
```

## 9.2 Runs Mobile Target

```text
Header
LO Runs                                   [menu]

Stats chip row
[4 Shown] [1 Active] [2.97k Requests] [177M Tokens]

Active run compact card
codegoropher deepseek                  active
112 requests · 4h 41m open
[Open] [End]

Run cards
codegoropher deepseek                  active
24 May 2026 · 09:12:40
112 requests · 1.12M tokens · $0.0667
LLM wall time 2h 59m                   >

HF Upstream test                       complete
23 May 2026 · 22:39:13
106 requests · 5.14M tokens · $0.8066
LLM wall time 1h 56m                   >
```

---

# 10. Desktop + Mobile Priority Fixes

## Highest Priority

1. **Remove horizontal scrolling on mobile Runs page**
   - Replace table with run cards.

2. **Collapse mobile filters**
   - Use one search row and a filter drawer.
   - Replace full-width checkboxes with compact chips.

3. **Make mobile summary chips horizontally scrollable**
   - Prevent multi-row chip wrapping.

4. **Compact the active run card**
   - Inline `End run` action.
   - Avoid large blank card areas.

5. **Create mobile request cards**
   - Do not rely on desktop request table layout.

6. **Fix mobile date/time formatting**
   - Avoid broken strings like `202612:15:26`.

7. **Remove repeated “View full details” from rows**
   - Make row/card clickable with chevron.

8. **Fix What-if baseline semantics**
   - Current run/provider should be baseline unless user explicitly chooses otherwise.

## Medium Priority

9. Add sticky desktop request inspector.
10. Add active state to clickable summary chips.
11. Add local-time display with UTC tooltip.
12. Add compact row density mode on desktop.
13. Improve error highlighting on run summary.
14. Add tooltips for `Run open`, `LLM wall time`, and `Request duration`.

---

# 11. Implementation Guidance for Coding Agents

## 11.1 Do Not Try to Make One Table Work Everywhere

Use separate desktop and mobile renderers.

Recommended:

```text
renderRequestsTableDesktop()
renderRequestsCardsMobile()

renderRunsTableDesktop()
renderRunsCardsMobile()
```

The data can be the same. The presentation should differ.

## 11.2 Keep API Shape Stable

The current live APIs likely already return enough data. The mobile card renderer can reuse existing fields.

For request cards:

```json
{
  "id": 2974,
  "created_at": "...",
  "method": "POST",
  "endpoint": "/v1/chat/completions",
  "model": "gpt-test",
  "billing_provider": "DeepSeek",
  "status_label": "200",
  "duration_display": "2.97 s",
  "tokens_per_second_display": "49.56",
  "tokens": {
    "input_display": "5",
    "output_display": "147",
    "total_display": "152"
  },
  "cost_display": "$0.000042",
  "is_stream": true,
  "has_tool_calls": false,
  "error": null,
  "preview": "你好！有什么可以帮你的吗？ 😊"
}
```

For run cards:

```json
{
  "id": 4,
  "name": "codegoropher deepseek",
  "is_active": true,
  "started_at": "...",
  "request_count_display": "112",
  "total_tokens_display": "1.12M",
  "total_cost_display": "$0.0667",
  "llm_wall_time_display": "2h 59m"
}
```

## 11.3 Add View-Specific CSS Classes

Suggested structure:

```css
@media (max-width: 767px) {
  .desktop-table-shell {
    display: none;
  }

  .mobile-card-list {
    display: grid;
    gap: 10px;
  }

  .toolbar {
    display: none;
  }

  .mobile-filter-summary {
    display: flex;
  }
}
```

## 11.4 Use Compact Cards

Mobile cards should use:

```css
.mobile-card {
  padding: 12px;
  border-radius: 14px;
}

.mobile-card-title {
  font-size: 0.95rem;
  line-height: 1.25;
}

.mobile-card-meta {
  font-size: 0.8rem;
  color: var(--muted);
}
```

## 11.5 Prefer Progressive Disclosure

Show only key information by default. Put details behind:

- expand action
- details page
- inspector drawer
- bottom sheet

Example mobile request card actions:

```text
Tap card         -> open request detail
Long press/menu  -> copy request ID / copy JSON
```

---

# 12. Acceptance Criteria

## Mobile Request Browser

- No horizontal scroll on the main page.
- Summary chips remain one-line horizontally scrollable.
- Filters are collapsed by default.
- Signal filters are compact chips.
- Active run card fits in a compact block.
- Request rows are rendered as mobile cards.
- Each request card shows:
  - ID
  - local date/time
  - model
  - provider
  - status
  - duration/TPS
  - tokens
  - cost
  - meaningful signal badges
- Date/time is readable and not malformed.
- Tap target size is at least 40px for buttons/chips.

## Mobile Runs Page

- No horizontal scroll.
- Runs are shown as stacked cards, not a desktop table.
- Active run card is compact.
- Each run card shows:
  - run name
  - active/complete status
  - start time
  - request count
  - total tokens
  - cost
  - LLM wall time
- Active run has obvious Open and End actions.

## Desktop Request Browser

- Default layout avoids horizontal scroll at common desktop widths.
- Right inspector is sticky or drawer-based.
- Summary chips are clickable filters.
- Row click selects request.
- Open action opens full request detail.
- Repeated per-row `View full details` links are removed.

## Run Detail

- What-if cost baseline is semantically correct.
- Error KPI is visually prominent when errors > 0.
- Overview cards avoid unnecessary empty space.
- Recent traffic rows are compact.
- Live status remains visible.

---

# 13. Recommended Next Work Order

1. Implement mobile request card renderer.
2. Implement mobile run card renderer.
3. Collapse mobile filters into drawer.
4. Make summary chips horizontally scrollable and clickable.
5. Fix mobile date/time formatting.
6. Reduce active run card height.
7. Remove repeated row-level detail links.
8. Fix What-if baseline.
9. Make desktop inspector sticky.
10. Tune desktop row density and card spacing.

---

# 14. Bottom Line

The desktop UI is now close to a useful LLM observability product. The Requests page and Run detail page have the right data model and the right overall structure.

The mobile UI still needs a more intentional responsive design. The most important change is to stop rendering desktop tables and full filter forms on mobile. Mobile should use compact summary chips, collapsed filters, and stacked request/run cards.

Once those changes are made, the product will feel coherent across desktop and mobile instead of being a desktop admin app squeezed into a phone-sized screen.
