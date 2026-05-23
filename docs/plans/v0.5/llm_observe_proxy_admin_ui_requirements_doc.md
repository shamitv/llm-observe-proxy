# LLM Observe Proxy Admin UI Redesign Requirements

## 1. Purpose

This document defines the requirements for redesigning the `LLM Observe Proxy` admin Settings UI. It is intended for a coding agent that will receive this document together with the generated UI mockup images for the **Server**, **Providers**, and **Routing** tabs.

The goal is to move the current Settings page from a single dense configuration screen into a clearer, safer, tab-based admin console that supports real operational workflows: configuring upstreams, defining provider metadata, routing incoming model names, setting fallback defaults, testing connectivity, and managing retention.

## 2. Design Intent

The redesigned UI should feel like a polished developer-admin dashboard, not a raw settings dump. It should preserve the existing product identity while improving information architecture, safety, route/provider clarity, and day-to-day operability.

The UI should support these user goals:

1. Quickly understand how the proxy is currently configured.
2. Know which URL clients should call.
3. Know which provider and model will be used if no route matches.
4. Configure global fallback provider/model behavior.
5. Configure provider definitions used by routes and pricing.
6. Configure model routing rules with clear match behavior.
7. Test provider connectivity and route resolution before relying on them.
8. Safely perform destructive actions such as deleting config or trimming history.
9. Keep pricing and provider management extensible without overwhelming the Settings page.

## 3. Inputs for Coding Agent

The coding agent should use this requirements document plus the UI images as the target visual and functional specification.

Expected image set:

1. **Server tab mockup**
   - Shows Connection Summary, Server tab active, Proxy listener, Global upstream fallback defaults, Compatibility fixes, Model routes, Test route / diagnostics, and Data retention.

2. **Providers tab mockup**
   - Shows Providers tab active, Provider registry table, Selected provider editor, Fallback defaults, Provider health / diagnostics, and Recent provider usage.

3. **Routing tab mockup**
   - Shows Routing tab active, Route registry table, Selected route editor, Fallback routing behavior, Route simulator / diagnostics, and Recent route usage.

The agent should treat the images as layout/style references, not pixel-perfect mandatory output. Functionality, information architecture, data model compatibility, and safe UX are more important than exact visual matching.

## 4. Current UI vs New UI

### 4.1 Current UI Summary

The current Settings page contains multiple unrelated configuration areas on one long page:

- Incoming server settings
- Global upstream URL
- Default compatibility fixes
- Model routes
- Model providers
- Model pricing and tiers
- Test upstream
- Trim history

The current implementation is functional and compact, but it has these usability problems:

| Area | Current UI Issue |
|---|---|
| Information architecture | Too many unrelated controls on one page. Users must scroll through server, routes, providers, pricing, diagnostics, and data retention together. |
| Global upstream | Only exposes URL clearly. It does not clearly expose the default provider and default model fallback relationship. |
| Routing | Model route creation is inline and looks similar to existing values. Route match semantics are not sufficiently explicit. |
| Providers | Provider registry is mixed into the same Settings page as everything else. It lacks search, selection, health, and fallback context. |
| Compatibility fixes | Raw text IDs are useful for power users but unfriendly as the default interaction. |
| Pricing | Dense table with nested tier controls is hard to scan and risky to edit. |
| Destructive actions | Delete buttons are shown inline and can feel too easy to click. |
| Testing | Test upstream exists, but route/provider resolution preview should be clearer before running a test. |
| Safety | `Expose on all IPs` is technically clear but should explain LAN exposure risk more explicitly. |

### 4.2 New UI Summary

The new UI should organize Settings into clear tabs:

- **Server**
- **Routing**
- **Providers**
- **Pricing**
- **Diagnostics**
- **Data**

Each tab should show a consistent top **Connection Summary** strip followed by tab-specific content.

| Area | New UI Behavior |
|---|---|
| Information architecture | Use primary Settings layout plus secondary tab row. Each tab focuses on one operational domain. |
| Global upstream | Allows configuring URL, default provider, and default model. Makes fallback behavior explicit. |
| Routing | Provides a searchable route registry, selected route editor, route simulator, fallback behavior, and usage summary. |
| Providers | Provides a searchable provider registry, selected provider editor, fallback defaults, health checks, and usage summary. |
| Compatibility fixes | Presents checkboxes/chips for known fixes with descriptions, with advanced manual edit collapsed. |
| Pricing | Should be moved to its own tab with searchable pricing rows and separate tier management. |
| Destructive actions | Move data deletion into a danger-zone style card with confirmation. Use confirmations for delete actions. |
| Testing | Add route/provider previews before executing tests. |
| Safety | Add clearer helper text and warning language for network exposure and destructive actions. |

## 5. Global Layout Requirements

### 5.1 App Shell

The redesigned Settings UI should use a consistent app shell:

- Top header:
  - Product logo/icon
  - Product name: `LLM Observe Proxy`
  - Main nav items:
    - Requests
    - Runs
    - Settings, active
    - Health
  - User/avatar affordance on far right

- Left sidebar:
  - Section heading: `Settings`
  - Navigation items:
    - Server
    - Routing
    - Providers
    - Pricing
    - Diagnostics
    - Data
  - Highlight the currently selected tab
  - Bottom environment card:
    - Environment: `Local Development`
    - Version: current app version if available, otherwise a fallback like `v1.0.0`

- Main content:
  - Top `Connection Summary` strip
  - Secondary tab row
  - Tab-specific content cards

### 5.2 Visual Style

Use a clean, modern admin dashboard style:

- Light background
- White cards
- Soft shadows or subtle borders
- Teal/green primary accent
- Red for dangerous actions
- Amber/orange for warnings
- Green for healthy/active/success states
- Rounded corners
- Clear spacing
- Legible table row height
- Consistent labels and helper text

### 5.3 Responsive Behavior

The layout should degrade gracefully:

- Wide desktop: two/three-column dashboard layout.
- Medium screens: cards stack into fewer columns.
- Small screens: sidebar may collapse or stack; tables should horizontally scroll where necessary.
- Forms should not overflow horizontally.

## 6. Shared Components

### 6.1 Connection Summary

Each Settings tab should include a top summary strip. The contents may vary by tab, but the pattern should be consistent.

Minimum supported summary card fields:

- Icon
- Label
- Primary value
- Helper text
- Optional highlighted state

Examples:

Server tab:

- Proxy listener: `0.0.0.0:8080`
- Client base URL: `http://localhost:8080/v1`
- Global upstream: `HF Router / Qwen 3.6 35B`
- Stored rows: `65`

Providers tab:

- Active providers: `10`
- Default provider: `Hugging Face Router`
- Default model family: `Qwen 3.6 35B`
- Stored rows: `65`

Routing tab:

- Active routes: `8`
- Default provider: `Hugging Face Router`
- Default model family: `Qwen 3.6 35B`
- Stored rows: `65`

### 6.2 Status Badges

Support badges for:

- Active
- Inactive
- Healthy
- Warning
- Missing key
- Valid
- Success
- Error

### 6.3 Confirmations

Dangerous operations must require confirmation.

Operations requiring confirmation:

- Delete provider
- Delete route
- Delete pricing entry
- Delete pricing tier
- Trim history
- Disable active provider used by routes
- Disable active route that currently receives traffic

Confirmation text should name the affected entity and, where possible, show impact.

Example:

> Delete provider `Hugging Face Router`? This may affect 3 routes and 12 model pricing entries.

## 7. Server Tab Requirements

### 7.1 Server Tab Purpose

The Server tab is for configuring listener behavior, global upstream fallback defaults, default compatibility fixes, basic route overview, testing, and data retention.

### 7.2 Proxy Listener Card

Fields:

- `Admin / proxy port`
  - Type: number
  - Min: 1
  - Max: 65535
  - Required

- `Expose on LAN / all interfaces`
  - Type: checkbox/toggle
  - Maps to binding host behavior:
    - On: `0.0.0.0`
    - Off: `localhost` or `127.0.0.1`, depending on current backend behavior

Helper text:

> Allow connections from other devices on your network.

When enabled, optionally show warning:

> Network exposed. Use only on trusted networks.

Button:

- `Save listener settings`

### 7.3 Global Upstream Fallback Defaults Card

This is a key change.

The user must be able to configure:

1. Global upstream URL
2. Default provider
3. Default model

Fields:

- `Global upstream URL`
  - Example: `http://localhost:8000/v1`
  - Required
  - Should validate URL shape where practical

- `Default provider`
  - Dropdown populated from provider registry
  - Example: `Hugging Face Router`
  - Required if fallback is enabled

- `Default model`
  - Dropdown or text input
  - Example: `Qwen 3.6 35B`
  - If provider has known model catalog/pricing entries, prefer dropdown/autocomplete
  - Should allow manual entry for local/custom models

Helper text:

> When no route matches a request, the proxy will use Qwen 3.6 35B from Hugging Face Router as the default fallback.

Button:

- `Save upstream defaults`

Backend must store these separately, not only as a URL string.

Suggested config fields:

```json
{
  "upstream_url": "http://localhost:8000/v1",
  "default_provider_slug": "huggingface-router",
  "default_model": "Qwen 3.6 35B"
}
```

### 7.4 Compatibility Fixes Card

Known compatibility fixes should be selectable via checkboxes.

Example fixes:

- `qwen-tagged-tool-call-rewrite`
  - Description: Promote complete `<tool_call>` blocks from reasoning into OpenAI `tool_calls`.

- `strip-reasoning-tags`
  - Description: Remove `<think>...</think>` style reasoning tags from output.

- `normalize-function-names`
  - Description: Normalize function/tool names to `snake_case`.

Requirements:

- Show known fixes as checkbox items with descriptions.
- Preserve ordering where ordering matters.
- Provide collapsed advanced editor: `Advanced manual edit (JSON)` or `Advanced manual edit`.
- Manual editor should allow direct editing of fix IDs for advanced users.
- Save button: `Save fixes`.

### 7.5 Model Routes Summary

The Server tab can include a compact route summary table or link to the Routing tab.

Minimum behavior:

- Show existing route rows, if present.
- Provide `+ Add route` button that navigates to Routing tab or opens route creation UI.
- Avoid making this section the primary route editor if the Routing tab exists.

### 7.6 Test Route / Diagnostics Card

Fields:

- Select route
- Test type:
  - Simple message
  - Image message
  - Function call
- Message/prompt text area

Preview:

- Route used
- Upstream URL
- Send as model
- Provider

Result:

- Status
- Duration
- Response summary/body
- Error details if failed

Actions:

- `Run test`
- `Image message`
- `Function call`

### 7.7 Data Retention / Danger Zone Card

Fields:

- Retain days
- Confirmation checkbox

Actions:

- `Trim records`
- `Refresh count`

Requirements:

- Red danger-zone styling.
- Button disabled until confirmation is checked.
- Show preview count before deleting:
  - `Current preview: 0 rows will be deleted.`
- Deletion endpoint should return deleted count.

## 8. Providers Tab Requirements

### 8.1 Providers Tab Purpose

The Providers tab manages upstream provider definitions used by routing, pricing, authentication, health checks, and fallback defaults.

### 8.2 Provider Registry Card

Title:

- `Provider registry`

Helper text:

> Manage upstream provider definitions used by routing and pricing.

Controls:

- Search input: `Search providers...`
- Status filter: `All status`
- Currency filter: `All currencies`
- Button: `+ Add provider`

Table columns:

- Provider
- Slug
- Base URL
- Currency
- Status
- Models / Routes
- Actions

Example rows:

| Provider | Slug | Base URL | Currency | Status | Models / Routes |
|---|---|---|---|---|---|
| Hugging Face Router | huggingface-router | https://router.huggingface.co/v1 | USD | Active | 12 models / 3 routes |
| OpenAI | openai | https://api.openai.com/v1 | USD | Active | 8 models / 4 routes |
| Anthropic | anthropic | https://api.anthropic.com/v1 | USD | Active | 5 models / 2 routes |
| Alibaba Cloud Model Studio | alibaba | https://dashscope-intl.aliyuncs.com/compatible-mode/v1 | USD | Active | 6 models / 1 route |
| Local llama.cpp | local-llama | http://localhost:8000/v1 | Local | Active | 2 models / 2 routes |

Actions:

- Edit
- Delete

Requirements:

- Row selection should populate the Selected Provider card.
- Search should filter by provider name, slug, and base URL.
- Filters should be optional but visually present.
- Pagination should be supported if provider count exceeds visible rows.

### 8.3 Selected Provider Card

Title:

- `Selected provider`

Fields:

- Provider name
- Slug
- Base URL
- Currency
- Authentication
  - API key env var
- Default for fallback
  - Toggle: yes/no
- Supported capabilities
  - Text
  - Vision
  - Tool calling

Example selected provider:

```text
Provider name: Hugging Face Router
Slug: huggingface-router
Base URL: https://router.huggingface.co/v1
Currency: USD
API key env var: HF_TOKEN
Default for fallback: Yes
Capabilities: Text, Vision, Tool calling
```

Helper info:

> When no route matches, the proxy can use this provider together with the configured fallback model.

Actions:

- `Save provider`
- `Test provider`

Validation:

- Slug must be unique.
- Slug should be URL-safe / config-safe.
- Base URL should be valid or allow local URLs.
- API key env var should be optional for local providers.
- If provider is set as default fallback, it must be active.

### 8.4 Fallback Defaults Card

This should mirror the fallback fields from the Server tab.

Fields:

- Default provider
- Default model
- Resolution rule

Example:

```text
Default provider: Hugging Face Router
Default model: Qwen 3.6 35B
Resolution rule: Used when no route matches
```

Info text:

> If a request doesn’t match any route, the proxy will use the default provider and model above. This ensures requests always have a valid upstream.

### 8.5 Provider Health / Diagnostics Card

Title:

- `Provider health / diagnostics`

Action:

- `Run health checks`

Columns:

- Provider
- Last check
- Latency
- Auth
- Result

Example rows:

| Provider | Last check | Latency | Auth | Result |
|---|---:|---:|---|---|
| Hugging Face Router | 1 min ago | 420 ms | Valid | Healthy |
| OpenAI | 1 min ago | 380 ms | Valid | Healthy |
| Local llama.cpp | 2 min ago | 95 ms | N/A | Healthy |
| Anthropic | 2 min ago | — | Missing key | Warning |

Backend behavior:

- Provider health check should test a lightweight endpoint where possible.
- If no standard health endpoint exists, perform a minimal model/list or small request depending on provider compatibility.
- Avoid costly calls unless explicitly requested.
- Store transient health results in memory or lightweight database table if useful.

### 8.6 Recent Provider Usage Card

Title:

- `Recent provider usage`

Columns:

- Provider
- Requests today
- Estimated cost
- Active routes

Example rows:

| Provider | Requests today | Estimated cost | Active routes |
|---|---:|---:|---:|
| Hugging Face Router | 4,512 | $12.48 | 3 |
| OpenAI | 2,187 | $8.73 | 4 |
| Anthropic | 1,046 | $4.21 | 2 |
| Alibaba Cloud Model Studio | 643 | $1.82 | 1 |
| Local llama.cpp | 128 | $0.00 | 2 |

CTA:

- `View full usage analytics →`

## 9. Routing Tab Requirements

### 9.1 Routing Tab Purpose

The Routing tab manages how incoming model names are matched and forwarded to upstream providers/models.

### 9.2 Route Registry Card

Title:

- `Route registry`

Helper text:

> Define how incoming models are matched and forwarded to upstream providers.

Controls:

- Search input: `Search routes...`
- Status filter: `All status`
- Provider filter: `All providers`
- Button: `+ Add route`

Table columns:

- Incoming model
- Match type
- Route upstream URL
- Send as model
- Provider
- Fallback
- Status
- Actions

Example rows:

| Incoming model | Match type | Route upstream URL | Send as model | Provider | Fallback | Status |
|---|---|---|---|---|---|---|
| local-qwen | Exact | http://localhost:8000/v1 | qwen3-coder-30b | Local llama.cpp | No | Active |
| qwen-* | Prefix | https://router.huggingface.co/v1 | Qwen 3.6 35B | Hugging Face Router | Yes | Active |
| vision-* | Prefix | https://router.huggingface.co/v1 | Qwen 3.6 VL | Hugging Face Router | Yes | Active |
| gpt-* | Prefix | https://api.openai.com/v1 | gpt-5.4-mini | OpenAI | Yes | Active |
| embed-* | Prefix | https://api.openai.com/v1 | text-embedding-3-small | OpenAI | No | Active |

Actions:

- Edit
- Delete

Requirements:

- Row selection populates Selected Route card.
- Search filters incoming model, upstream URL, upstream model, provider.
- Must support pagination.
- Must show active/inactive status.
- Must show whether route overrides fallback.

### 9.3 Match Types

Support at least these match types:

1. Exact
   - `local-qwen` matches only `local-qwen`.

2. Prefix
   - `qwen-*` matches incoming models starting with `qwen-`.

Optional future match types:

3. Regex
   - Advanced users only.
   - Should include validation and test simulator.

4. Contains
   - Lower priority; only implement if needed.

Route resolution should be deterministic.

Suggested order:

1. Enabled routes only
2. Higher route priority first
3. Exact match before prefix match if priority ties
4. Longer/more-specific pattern before shorter pattern if priority ties
5. Stable tie-breaker, such as creation order or slug/name
6. Fallback provider/model if no route matches

### 9.4 Selected Route Card

Title:

- `Selected route`

Fields:

- Incoming model
- Match type
- Route upstream URL
- Send as model
- Provider
- API key env var
- Compatibility fixes
- Override fallback
- Route priority
- Enabled

Example selected route:

```text
Incoming model: qwen-*
Match type: Prefix match
Route upstream URL: https://router.huggingface.co/v1
Send as model: Qwen 3.6 35B
Provider: Hugging Face Router
API key env var: HF_TOKEN
Compatibility fixes: qwen-tagged-tool-call-rewrite, strip-reasoning-tags
Override fallback: Yes
Route priority: 50
Enabled: Yes
```

Info text:

> Requests with models matching `qwen-*` will be sent to Hugging Face Router and forwarded as Qwen 3.6 35B.

Actions:

- `Save route`
- `Test route`

Validation:

- Incoming model pattern required.
- Match type required.
- Provider required unless route uses raw upstream URL only.
- Upstream URL required, but may be inferred from provider if provider selected.
- Send as model required unless the system intentionally forwards original model name.
- Priority should be numeric.
- API key env var can be inherited from provider unless overridden.

### 9.5 Fallback Routing Behavior Card

Fields:

- Default provider
- Default model
- Resolution rule

Example:

```text
Default provider: Hugging Face Router
Default model: Qwen 3.6 35B
Resolution rule: Use fallback when no route matches
```

Info text:

> If an incoming model does not match any configured route, the proxy will use the default provider and model.

### 9.6 Route Simulator / Diagnostics Card

Purpose:

Allow users to test route resolution before sending real requests.

Fields:

- Incoming model to test
- Message type

Example:

```text
Incoming model to test: qwen-chat
Message type: Simple message
```

Preview result:

```text
Matched route: qwen-*
Upstream URL: https://router.huggingface.co/v1
Send as model: Qwen 3.6 35B
Provider: Hugging Face Router
```

Result state:

- Match found
- No match, fallback will be used
- No match and fallback not configured
- Route disabled
- Missing API key

Action:

- `Run simulation`

### 9.7 Recent Route Usage Card

Title:

- `Recent route usage`

Columns:

- Route
- Requests today
- Last matched

Example rows:

| Route | Requests today | Last matched |
|---|---:|---|
| qwen-* | 3,104 | 2 min ago |
| gpt-* | 1,882 | 1 min ago |
| vision-* | 406 | 7 min ago |
| local-qwen | 218 | 4 min ago |
| embed-* | 96 | 9 min ago |

CTA:

- `View full routing analytics →`

## 10. Pricing Tab Requirements

The detailed pricing tab image is not included in this batch, but the new UI should move pricing to a dedicated tab.

### 10.1 Pricing Tab Purpose

Manage model pricing metadata without overcrowding provider or routing configuration.

### 10.2 Pricing Registry

Recommended table columns:

- Provider
- Model
- Display name
- Input / 1M
- Cached input / 1M
- Output / 1M
- Aliases
- Tiers
- Active
- Actions

Requirements:

- Search by provider, model, display name, alias.
- Filter by provider and active status.
- Show tiers summarized, not fully expanded inline.
- Provide `Manage tiers` action that opens detail drawer/modal/card.
- Avoid rendering tier creation forms inside table rows by default.

## 11. Backend / Data Model Requirements

### 11.1 Provider Model

Suggested provider fields:

```json
{
  "slug": "huggingface-router",
  "name": "Hugging Face Router",
  "base_url": "https://router.huggingface.co/v1",
  "currency": "USD",
  "api_key_env": "HF_TOKEN",
  "active": true,
  "is_default_fallback_provider": true,
  "capabilities": {
    "text": true,
    "vision": true,
    "tool_calling": true
  },
  "created_at": "...",
  "updated_at": "..."
}
```

### 11.2 Route Model

Suggested route fields:

```json
{
  "id": "route_qwen_prefix",
  "incoming_model": "qwen-*",
  "match_type": "prefix",
  "upstream_url": "https://router.huggingface.co/v1",
  "upstream_model": "Qwen 3.6 35B",
  "provider_slug": "huggingface-router",
  "api_key_env": "HF_TOKEN",
  "compatibility_fixes": [
    "qwen-tagged-tool-call-rewrite",
    "strip-reasoning-tags"
  ],
  "override_fallback": true,
  "priority": 50,
  "active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

### 11.3 Global Fallback Settings

Suggested settings fields:

```json
{
  "global_upstream_url": "http://localhost:8000/v1",
  "default_provider_slug": "huggingface-router",
  "default_model": "Qwen 3.6 35B",
  "fallback_enabled": true,
  "default_compatibility_fixes": [
    "qwen-tagged-tool-call-rewrite"
  ]
}
```

### 11.4 Health Check Result Model

Suggested transient/result fields:

```json
{
  "provider_slug": "huggingface-router",
  "checked_at": "...",
  "latency_ms": 420,
  "auth_state": "valid",
  "status": "healthy",
  "message": "OK"
}
```

### 11.5 Usage Summary Model

Usage summaries can be computed from existing request logs.

Provider usage fields:

```json
{
  "provider_slug": "huggingface-router",
  "requests_today": 4512,
  "estimated_cost": 12.48,
  "active_routes": 3
}
```

Route usage fields:

```json
{
  "route_id": "route_qwen_prefix",
  "route_label": "qwen-*",
  "requests_today": 3104,
  "last_matched_at": "..."
}
```

## 12. API / Endpoint Requirements

The exact route names can follow the existing backend conventions, but the UI needs API support for the following operations.

### 12.1 Settings

- Get settings summary
- Update listener settings
- Update global upstream fallback defaults
- Update default compatibility fixes
- Get storage/retention preview
- Trim records

### 12.2 Providers

- List providers
- Create provider
- Get provider
- Update provider
- Delete provider
- Test provider
- Run provider health checks
- Get provider usage summary

### 12.3 Routes

- List routes
- Create route
- Get route
- Update route
- Delete route
- Simulate route match
- Test route
- Get route usage summary

### 12.4 Pricing

- List model prices
- Create/update/delete model price
- List tiers for a model price
- Create/update/delete tier

## 13. Route Resolution Requirements

When a request arrives:

1. Extract incoming model name from request body.
2. Find active routes matching the incoming model.
3. Sort matching routes deterministically.
4. Select best route.
5. If route found:
   - Use route upstream URL/provider.
   - Rewrite model to route upstream model if configured.
   - Apply route compatibility fixes.
   - Use route API key env var or provider API key env var.
6. If no route found:
   - Use default provider and default model if fallback enabled.
   - Use global upstream URL if configured.
   - Apply default compatibility fixes.
7. If no route and no fallback configured:
   - Return a clear admin/configuration error.

The UI should display this behavior consistently in summary cards, fallback panels, route editor info boxes, and simulator results.

## 14. Validation and Error Handling

### 14.1 Form Validation

Validate on client side where convenient and always on server side.

Provider validation:

- Slug required and unique.
- Name required.
- Base URL required unless provider is purely metadata, but route execution needs a URL.
- Currency required.
- API key env var optional for local providers.

Route validation:

- Incoming model required.
- Match type required.
- Provider or upstream URL required.
- Upstream model required unless forwarding original model is explicitly allowed.
- Priority numeric.
- Compatibility fix IDs must be known or accepted by advanced mode.

Fallback validation:

- Default provider must exist and be active.
- Default model must not be empty.
- Default provider should have base URL.

### 14.2 Error Presentation

Errors should be shown near the relevant form and optionally as toast messages.

Examples:

- `Provider slug already exists.`
- `Default provider is inactive.`
- `Route pattern qwen-* overlaps with another route at the same priority.`
- `HF_TOKEN is not set in the environment.`
- `Could not reach upstream URL.`

### 14.3 Success Presentation

Show success feedback after saves/tests:

- `Provider saved.`
- `Route saved.`
- `Upstream defaults saved.`
- `Health checks completed.`
- `Simulation matched qwen-*.`

## 15. Security and Safety Requirements

1. Never display raw API key values.
2. Display only env var names such as `HF_TOKEN` or `OPENAI_API_KEY`.
3. Warn when exposing the proxy on all interfaces.
4. Confirm destructive actions.
5. Prevent accidental deletion of providers/routes that are currently in use, or show impact before allowing deletion.
6. Avoid logging secrets in test results.
7. Sanitize displayed response bodies where necessary.
8. If admin UI is exposed beyond localhost, consider authentication or at least a clear warning.

## 16. Accessibility Requirements

- All interactive controls must be keyboard accessible.
- Inputs must have visible labels.
- Buttons must have discernible text.
- Status colors must be accompanied by text labels.
- Focus states should be visible.
- Tables should use proper header semantics.
- Confirmation dialogs should trap focus while open.
- Do not rely on color alone for warning/success/error states.

## 17. Implementation Notes for Coding Agent

### 17.1 Suggested Delivery Order

Recommended implementation order:

1. Create shared layout shell and Settings tabs.
2. Implement Connection Summary component.
3. Implement Server tab with improved Global upstream fallback defaults.
4. Refactor provider management into Providers tab.
5. Refactor route management into Routing tab.
6. Add route simulator endpoint and UI.
7. Add provider health check endpoint and UI.
8. Move pricing into a dedicated Pricing tab.
9. Add confirmations and safety improvements.
10. Polish responsive behavior and accessibility.

### 17.2 Compatibility With Existing Backend

Where possible, preserve existing POST endpoints initially and add new structured endpoints incrementally.

If existing backend currently stores only flat values, add migration/default behavior:

- If no `default_provider_slug` is set, infer from upstream URL if possible.
- If no `default_model` is set, leave blank and show warning.
- Existing route definitions should be mapped into the new route table.
- Existing provider definitions should be mapped into provider registry.
- Existing default compatibility fixes text should be parsed into selected checkbox states.

### 17.3 Non-Goals for First Pass

The first implementation does not need:

- Pixel-perfect matching to generated images.
- Full drag-and-drop route ordering.
- Full provider model catalog sync.
- Real-time streaming health checks.
- Complex pricing tier editor redesign if time is limited.
- Authentication overhaul unless already planned.

## 18. Acceptance Criteria

### 18.1 Server Tab

- User can view listener URL, client base URL, fallback provider/model, and stored rows in summary.
- User can update listener port and LAN exposure setting.
- User can update global upstream URL, default provider, and default model.
- User can understand that unmatched requests use the default provider/model.
- User can select compatibility fixes through checkboxes.
- User can run a test and see route/provider preview plus result.
- Trim history requires explicit confirmation.

### 18.2 Providers Tab

- User can search, filter, and view providers.
- User can select a provider and edit details.
- User can set provider as fallback default.
- User can see provider capabilities.
- User can test a provider.
- User can run health checks and see results.
- User can see recent provider usage.

### 18.3 Routing Tab

- User can search, filter, and view routes.
- User can select a route and edit details.
- User can clearly see match type, upstream URL, forwarded model, provider, fixes, priority, and enabled state.
- User can simulate an incoming model and see matched route/fallback behavior.
- User can see recent route usage.
- Route resolution is deterministic and documented in the UI or help text.

### 18.4 Safety

- Destructive actions require confirmation.
- API key values are never shown.
- Missing API keys are clearly indicated.
- Network exposure is clearly explained.
- Invalid configuration produces actionable error messages.

## 19. Example Target Workflow

### Workflow: Always use Qwen 3.6 35B from Hugging Face Router as default

1. User opens Settings → Server or Providers.
2. In Global upstream / Fallback defaults:
   - Default provider = `Hugging Face Router`
   - Default model = `Qwen 3.6 35B`
   - Resolution rule = `Use fallback when no route matches`
3. User saves upstream defaults.
4. Connection Summary updates:
   - Global upstream: `HF Router / Qwen 3.6 35B`
5. User opens Routing tab.
6. User creates or verifies route:
   - Incoming model = `qwen-*`
   - Match type = `Prefix`
   - Provider = `Hugging Face Router`
   - Send as model = `Qwen 3.6 35B`
7. User runs Route Simulator with `qwen-chat`.
8. UI shows:
   - Match found: `qwen-*`
   - Provider: `Hugging Face Router`
   - Send as model: `Qwen 3.6 35B`
9. User runs Test route.
10. UI shows success or actionable failure.

## 20. Glossary

| Term | Meaning |
|---|---|
| Incoming model | The model name sent by the client request. |
| Send as model | The model name forwarded to the upstream provider. |
| Provider | A named upstream service such as Hugging Face Router, OpenAI, Anthropic, or Local llama.cpp. |
| Global upstream URL | The default OpenAI-compatible `/v1` base URL used as fallback or base configuration. |
| Fallback | Provider/model used when no route matches. |
| Compatibility fix | A transformation that adapts model/provider output to expected OpenAI-compatible behavior. |
| Route simulator | A diagnostic UI that predicts which route/fallback will be used for an incoming model name. |
| Provider health | Lightweight test of provider connectivity/auth configuration. |

