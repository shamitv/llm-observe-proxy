# ADR Draft: Response Compatibility Fix Pipeline

Status: Proposed
Date: 2026-05-05

## Is An ADR Appropriate?

An ADR is appropriate if the project is deciding whether `llm-observe-proxy`
should remain strictly record-only or allow an opt-in response transformation
mode. That is an architectural boundary decision because it changes the proxy's
contract from "observe and pass through" to "observe, optionally normalize, and
pass through."

This document should stay in ADR form while that boundary is being decided. If
the decision is accepted, a follow-up implementation plan should live under
`docs/plans/features/response-compatibility-fixes/`. If the team wants to
explore the feature without committing to the architectural change, better
alternatives are:

- A design RFC under `docs/design/response-compatibility-fixes.md`.
- A feature plan under `docs/plans/features/response-compatibility-fixes/`.
- A troubleshooting runbook under `docs/analysis/` if the feature remains only
  an experiment.

Recommendation: keep this as a draft ADR because the most important question is
architectural: whether a record-only proxy may offer explicitly configured
compatibility rewrites.

## Context

`llm-observe-proxy` is currently described and implemented as a record-only
OpenAI-compatible proxy. It forwards requests to an upstream `/v1` API, stores
request/response metadata and bodies in SQLite, and returns the upstream
response to the client without semantic changes.

Recent Qwen / llama.cpp / Copilot traffic showed a failure mode where the
upstream response is valid HTTP and valid SSE, but not useful to an
OpenAI-compatible tool-calling client:

- The request contains OpenAI `tools`.
- The upstream streams a complete Qwen-style tagged tool call, for example
  `<tool_call><function=read_file>...</function></tool_call>`.
- The tagged tool call appears in `delta.reasoning_content` or
  provider-specific `delta.reasoning`.
- No structured `delta.tool_calls` are emitted.
- The final `finish_reason` is `stop`, not `tool_calls`.

For observability this is fine: the proxy captures the raw body and makes the
failure visible. For live Copilot usage it still fails, because the client sees
no tool call to execute.

The proxy could provide a local unblocker by applying targeted compatibility
fixes at runtime. This would not replace upstream fixes in llama.cpp or provider
servers. It would be an explicitly configured compatibility layer for known
model/provider quirks.

## Decision

Introduce an opt-in **Response Compatibility Fix Pipeline**.

A compatibility fix is a small, named, deterministic transformation that can
inspect and optionally rewrite request or response data for a specific
OpenAI-compatible endpoint. Fixes are disabled by default. Users can configure a
list of fixes for the default upstream and for each model route. The proxy
applies the selected fixes at runtime in the configured order.

The initial target fix should be:

```text
qwen-tagged-tool-call-rewrite
```

Purpose:

Convert a complete Qwen-style tagged tool call that was emitted inside
`delta.reasoning` or `delta.reasoning_content` into OpenAI-compatible streamed
`delta.tool_calls`, when it is safe to do so.

The feature name should be "compatibility fixes" or "response compatibility
fixes", not "mods". "Fix" communicates that each transformation is narrow,
named, documented, and testable. "Rewrite" can be used for specific fix IDs
where the behavior actually rewrites the response body.

## Goals

- Preserve record-only behavior by default.
- Allow users to opt into targeted fixes for known model/provider quirks.
- Support model-specific and default-upstream fix chains.
- Allow users to choose the order in which fixes are applied.
- Keep original upstream request and response bytes available for audit.
- Make every fix individually testable.
- Make fix application visible in captured request detail pages.

## Non-Goals

- Do not silently mutate traffic by default.
- Do not add general model-output parsing heuristics with broad blast radius.
- Do not pretend proxy-side fixes are substitutes for upstream server fixes.
- Do not execute tools inside the proxy.
- Do not infer tool calls when the request did not declare tools.
- Do not rewrite arbitrary XML-like text unless it matches a strict supported
  fix.

## Configuration Model

There are two levels of fix configuration:

1. Default upstream fix chain.
2. Per-model-route fix chain.

The per-model-route chain wins for matching model routes. Unknown models use the
default upstream chain.

Example startup configuration:

```json
{
  "default_fixes": [],
  "model_routes": [
    {
      "model": "local-qwen",
      "upstream_url": "http://localhost:8000/v1",
      "upstream_model": "qwen3.5-35b-a3b",
      "fixes": [
        "qwen-tagged-tool-call-rewrite"
      ]
    },
    {
      "model": "openrouter-qwen",
      "upstream_url": "https://openrouter.ai/api/v1",
      "upstream_model": "qwen/qwen3.5-35b-a3b",
      "api_key_env": "OPEN_ROUTER_KEY",
      "fixes": []
    }
  ]
}
```

Example UI-managed settings model:

```text
Default upstream fixes:
1. none

Model route: local-qwen
1. qwen-tagged-tool-call-rewrite
2. future-fix-id
```

The UI should allow users to:

- Add a fix from a known registry.
- Remove a fix.
- Reorder fixes.
- See a short description and risk note for each fix.
- See whether a fix applies to streaming responses, non-streaming responses, or
  both.

## Fix Registry

Each fix should be registered with metadata:

```python
CompatibilityFix(
    id="qwen-tagged-tool-call-rewrite",
    name="Qwen tagged tool-call rewrite",
    description="Promote complete Qwen <tool_call> blocks from reasoning into OpenAI tool_calls.",
    endpoints={"/v1/chat/completions"},
    supports_streaming=True,
    supports_non_streaming=True,
    default_enabled=False,
)
```

Each fix implementation should receive:

- Endpoint path.
- Original request payload.
- Upstream response headers.
- Upstream response body or streaming events.
- Fix-specific context, such as declared tools.
- A mutable event/body builder.

Each fix should return:

- The transformed response bytes or events.
- A structured list of applied actions.
- Any warnings or parse failures.

## Runtime Behavior

### Non-Streaming Responses

For non-streaming JSON responses:

1. Proxy forwards the request to upstream.
2. Proxy reads the full upstream response.
3. Proxy stores the original upstream response body.
4. Proxy applies the configured fix chain to a working response body.
5. Proxy returns the transformed body to the client.
6. Proxy stores metadata about applied fixes.

### Streaming Responses

For `text/event-stream` responses:

1. Proxy forwards the request to upstream.
2. Proxy reads upstream SSE events.
3. Proxy stores original upstream chunks.
4. Proxy applies the configured fix chain to the streaming event sequence.
5. Proxy yields transformed SSE chunks to the client.
6. Proxy stores the transformed response body separately or stores enough
   metadata to reconstruct what the client received.

For streaming fixes that need to detect complete tool-call blocks, the proxy may
need bounded buffering. The `qwen-tagged-tool-call-rewrite` fix should buffer
only after it sees `<tool_call>` in a reasoning delta and should flush as soon
as a complete `</tool_call>` is parsed or the fix decides the block is invalid.

## Initial Fix: Qwen Tagged Tool-Call Rewrite

### Trigger Conditions

The fix may run only when all conditions are true:

- Endpoint is `/v1/chat/completions`.
- Request payload contains non-empty `tools`.
- Response is a chat-completions response or SSE chat-completions stream.
- No structured `tool_calls` have already been emitted for the current
  assistant turn.
- A complete tagged block is found in `delta.reasoning` or
  `delta.reasoning_content`.
- The parsed function name matches one of the request's declared tool names.
- Parsed arguments can be serialized as a JSON object string.

### Rewrite Behavior

Given reasoning text like:

```text
The server should have auto-reloaded. Let me check if it is running:

<tool_call>
<function=run_in_terminal>
<parameter=command>
curl -s http://localhost:8000/docs | head -20
</parameter>
<parameter=mode>
sync
</parameter>
</function>
</tool_call>
```

The fix should preserve the pre-tool reasoning text as reasoning, then emit
structured tool-call deltas:

```json
{
  "choices": [
    {
      "index": 0,
      "delta": {
        "tool_calls": [
          {
            "index": 0,
            "id": "call_...",
            "type": "function",
            "function": {
              "name": "run_in_terminal",
              "arguments": "{\"command\":\"curl -s http://localhost:8000/docs | head -20\",\"mode\":\"sync\"}"
            }
          }
        ]
      },
      "finish_reason": null
    }
  ]
}
```

If the upstream final event says `finish_reason: "stop"` and the fix emitted a
tool call for the assistant turn, rewrite the final reason to:

```json
{"finish_reason": "tool_calls"}
```

### Rejection Conditions

The fix must refuse to rewrite when:

- The tagged block is incomplete.
- The function name is missing.
- The function name is not declared in request `tools`.
- Argument tags are malformed or duplicate in a way that cannot be represented
  safely.
- A structured tool call has already been emitted upstream.
- The response already has non-empty final assistant content after the tool
  block.
- The parser would need to guess a schema type that is not represented in the
  generated tags.

When the fix refuses to rewrite, it should pass the original response through
unchanged and record a warning.

## Data Capture And Auditability

Because this feature changes client-visible responses, records should
distinguish:

- Original upstream response body.
- Client-visible transformed response body.
- Applied fix IDs and order.
- Per-fix action summaries.
- Per-fix warnings/errors.

Potential database fields:

```text
response_body                 # client-visible body, or keep current semantics
upstream_response_body_raw     # original upstream body
compat_fixes_json              # ordered fix IDs and action summaries
compat_fix_errors_json         # parse/rewrite warnings
response_was_rewritten         # boolean
```

If schema churn should be minimized, the first implementation can store only
client-visible `response_body` plus `compat_fixes_json`, but that loses the
current strong audit property. The preferred implementation stores both raw and
transformed bodies.

## Ordering Semantics

Fixes are applied in the configured order.

Rules:

- Each fix receives the output of the previous fix.
- Each fix must be deterministic.
- A fix can declare that it terminates the chain for an assistant turn.
- Fixes must not reorder unrelated SSE events.
- Fixes must not consume usage events.
- Fixes must preserve `[DONE]`.

The UI should show the effective ordered chain for:

- Default upstream.
- Startup model routes.
- UI-managed model routes.
- Each captured request detail page.

## Safety And Security

Compatibility fixes can make model-generated text executable by a client that
executes tool calls. Therefore the initial implementation must be conservative:

- Fixes are disabled by default.
- Fixes are opt-in per default upstream or per model route.
- Tool names must match declared request tools.
- Arguments must be valid JSON strings after conversion.
- The proxy must not execute tools.
- The admin UI must clearly mark rewritten responses.
- The raw upstream body must remain available for review.

## Test Strategy

Extensive tests are required before enabling any rewrite path.

### Unit Tests

Add parser-level tests for `qwen-tagged-tool-call-rewrite`:

- Parses one complete `<tool_call>` block.
- Parses multiple `<parameter=...>` tags.
- Preserves string values with newlines.
- Converts numeric-looking values according to schema or keeps strings when
  schema is unknown.
- Rejects unknown function names.
- Rejects incomplete blocks.
- Rejects duplicate parameters unless the behavior is explicitly defined.
- Rejects malformed nesting.
- Rejects output when no request tools are declared.
- Does not rewrite ordinary reasoning text containing the literal word
  `tool_call`.

### Streaming Tests

Add SSE tests for:

- Tool-call tags split across many chunks.
- `<tool_call>` begins in one `reasoning_content` chunk and ends later.
- Provider uses `delta.reasoning` instead of `delta.reasoning_content`.
- Pre-tool reasoning is preserved.
- Final `finish_reason: stop` becomes `tool_calls` only when a tool call was
  emitted.
- Usage events survive unchanged.
- `[DONE]` survives unchanged.
- Existing structured `delta.tool_calls` are passed through unchanged.
- Invalid tagged blocks pass through unchanged and record warnings.

### Non-Streaming Tests

Add JSON response tests for:

- `message.reasoning_content` contains a complete Qwen tagged tool call.
- `message.reasoning` contains a complete Qwen tagged tool call.
- `message.tool_calls` is synthesized and `finish_reason` becomes
  `tool_calls`.
- Existing valid `message.tool_calls` are not modified.
- Rejected rewrites preserve the original response.

### Routing And Configuration Tests

Add tests for:

- Default upstream fix chain applies to unknown models.
- Per-model route fix chain applies to matching models.
- Per-model route fix chain overrides default chain.
- Fix order is preserved from startup JSON.
- Fix order is preserved from UI-managed settings.
- Invalid fix IDs are rejected with clear errors.
- Duplicate fix IDs are either rejected or de-duplicated by documented behavior.
- Startup routes remain read-only in the UI but show their configured fix chain.

### Capture And UI Tests

Add tests for:

- Raw upstream body and transformed client body are both stored.
- Request detail page marks rewritten responses.
- Request detail page shows applied fix IDs and warnings.
- Tool render mode shows synthesized tool calls.
- Raw SSE mode can show both upstream and client-visible streams, or clearly
  labels which one is being shown.

### Regression Fixtures

Use sanitized Qwen/Copilot fixtures from `docs/analysis/may_4/fixtures/` as
large integration-style regression tests where practical. Keep smaller focused
fixtures for normal unit tests.

## Migration Plan

1. Add fix registry and no-op fix-chain plumbing.
2. Add config parsing for `default_fixes` and route-level `fixes`.
3. Add UI support for selecting and ordering fixes.
4. Add capture metadata for applied fixes.
5. Add `qwen-tagged-tool-call-rewrite` behind the opt-in config.
6. Add extensive tests before documenting the feature as production-ready.
7. Update `README.md`, `README.pypi.md`, and `docs/tests/README.md`.

## Alternatives Considered

### Keep Proxy Strictly Record-Only

Pros:

- Preserves the current simple trust model.
- Avoids making model-generated text executable.
- Keeps the proxy useful as neutral evidence for upstream issues.

Cons:

- Does not unblock Copilot or other clients when upstream response shape is
  wrong.
- Requires users to patch upstream servers or switch providers.

### Fix Only Upstream llama.cpp

Pros:

- Correct place for OpenAI compatibility.
- Benefits all clients, not just this proxy.
- Avoids local compatibility debt.

Cons:

- Users may still need local mitigation while waiting for upstream fixes.
- Similar provider/model quirks may appear outside llama.cpp.

### Add A Hardcoded Qwen Rewrite Only

Pros:

- Fastest local unblocker.
- Smallest implementation surface.

Cons:

- Does not scale to other model/provider quirks.
- Hard to configure per provider.
- Easy to accidentally enable too broadly.

### Generic Middleware Plugins

Pros:

- Flexible.
- Could cover many request/response transformations.

Cons:

- Too broad for the current project.
- Harder to test and audit.
- Increases security and maintenance burden.

## Consequences

Positive:

- Users can locally unblock known compatibility issues.
- Fixes are explicit, ordered, and testable.
- The proxy becomes a controlled compatibility layer, not just an observer.

Negative:

- The proxy no longer remains strictly record-only when fixes are enabled.
- Runtime rewriting increases implementation complexity.
- The project must preserve raw upstream evidence to remain trustworthy.
- Misconfigured fixes could change client behavior in surprising ways.

## Open Questions

- Should transformed responses be stored in `response_body`, or should
  `response_body` remain raw upstream and a new field store client-visible
  output?
- Should fix configuration live only in startup JSON at first, or should UI
  management ship in the first version?
- Should fixes be allowed to transform requests, responses, or both?
- Should non-streaming support be implemented in the same milestone as
  streaming support?
- Should a fix be able to stop the chain after it rewrites a response?
- Should rejected fix attempts set `has_tool_calls` when a tool-like block was
  found but not promoted?

## Proposed Initial Acceptance Criteria

- With no configured fixes, all existing pass-through and capture tests continue
  to pass.
- With `qwen-tagged-tool-call-rewrite` configured for a model route, a malformed
  Qwen tagged tool call inside reasoning is returned to the client as structured
  OpenAI `tool_calls`.
- The original upstream SSE body is still available in the captured record.
- The client-visible transformed SSE body is available in the captured record.
- The request detail page shows that the response was rewritten and lists the
  applied fix.
- The feature is documented as opt-in and experimental.
