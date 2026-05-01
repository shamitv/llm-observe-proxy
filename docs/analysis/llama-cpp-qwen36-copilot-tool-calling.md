# llama.cpp + Qwen3.6 35B-A3B Copilot Tool-Calling Failure Analysis

Date: 2026-05-01

Branch: `feature/troubleshoot-llm-messages`

This document summarizes a local capture from `llm-observe-proxy` where VS Code
GitHub Copilot Chat Agent mode was configured to use a llama.cpp-compatible
OpenAI endpoint serving Qwen3.6 35B-A3B. It also includes a ready-to-adapt issue
report for `ggml-org/llama.cpp`.

## Short Summary

The proxy captured valid HTTP 200 streaming chat-completion responses, but many
responses contained no OpenAI-standard assistant content and no structured
OpenAI tool calls. Instead, the model output appeared only in
`delta.reasoning_content`, including Qwen-style pseudo-XML tool-call text such
as `<tool_call><function=run_in_terminal>...`.

From an OpenAI-compatible client perspective, those responses are effectively
empty:

- `delta.content` is `null` or absent.
- `delta.tool_calls` is absent.
- `finish_reason` is `stop`, not `tool_calls`.
- The stream still ends cleanly with `data: [DONE]`.

This matches the VS Code Copilot UI symptom:

```text
Autopilot recovered from a request error
Sorry, no response was returned.
```

The evidence points to a llama.cpp/Qwen tool-call parsing or chat-template
interaction rather than a proxy transport failure.

## Local Capture Environment

Observed client:

- Client: VS Code GitHub Copilot Chat Agent mode
- Request user agent: `GitHubCopilotChat/0.47.2026043003`
- Endpoint: `POST /v1/chat/completions`
- Upstream: OpenAI-compatible `/v1/chat/completions` endpoint
  (host redacted)
- Request mode: streaming
- `stream_options`: `{"include_usage": true}`
- Tool count in failing requests: 67
- Request history shape: multi-turn agent workflow with `assistant` and `tool`
  messages already present

Observed model identifiers:

- Request model: `qwen_3.6_35B_4bit`
- Response model: `Qwen3.6-35B-A3B-MXFP4_MOE.gguf`

Proxy behavior:

- `llm-observe-proxy` is record-only.
- It forwards requests upstream and streams upstream response chunks back to the
  client.
- It does not parse, mutate, normalize, or synthesize SSE chunks.
- For these rows, it captured the exact upstream SSE body after streaming.

## DB Evidence

Recent captured rows reviewed:

- Row IDs: `162` through `181`
- Count: 20 recent requests
- Status codes: 20/20 were `HTTP 200`
- Response content type: 20/20 were `text/event-stream`
- SSE validity: 20/20 had parseable JSON SSE events
- Stream termination: 20/20 ended with `data: [DONE]`
- Proxy/upstream connection errors: none captured

Aggregate response patterns:

| Pattern | Count | Meaning |
| --- | ---: | --- |
| No `content`, has `reasoning_content`, no `tool_calls`, `finish_reason: "stop"` | 16 | Main failure signature |
| Has `content`, has `reasoning_content`, has `tool_calls`, `finish_reason: "tool_calls"` | 2 | Good/usable tool-call shape |
| No `content`, has `reasoning_content`, has `tool_calls`, `finish_reason: "tool_calls"` | 1 | Tool call emitted, no user-visible content |
| Has `content`, has `reasoning_content`, no `tool_calls`, `finish_reason: "stop"` | 1 | Normal final-ish answer |

Per-row summary:

| ID | Messages | Tools | Content chars | Reasoning chars | Tool-call deltas | Finish reason | Duration ms |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 181 | 21 | 67 | 0 | 343 | 0 | `stop` | 1767 |
| 180 | 21 | 67 | 0 | 353 | 0 | `stop` | 1904 |
| 179 | 21 | 67 | 0 | 353 | 0 | `stop` | 1896 |
| 178 | 21 | 67 | 0 | 343 | 0 | `stop` | 2159 |
| 177 | 21 | 67 | 0 | 343 | 0 | `stop` | 1837 |
| 176 | 21 | 67 | 0 | 343 | 0 | `stop` | 1834 |
| 175 | 21 | 67 | 0 | 343 | 0 | `stop` | 1869 |
| 174 | 21 | 67 | 0 | 343 | 0 | `stop` | 23029 |
| 173 | 21 | 67 | 0 | 343 | 0 | `stop` | 1958 |
| 172 | 21 | 67 | 0 | 343 | 0 | `stop` | 1931 |
| 171 | 21 | 67 | 0 | 343 | 0 | `stop` | 1877 |
| 170 | 21 | 67 | 0 | 343 | 0 | `stop` | 1825 |
| 169 | 21 | 67 | 0 | 343 | 0 | `stop` | 1812 |
| 168 | 21 | 67 | 0 | 343 | 0 | `stop` | 2065 |
| 167 | 21 | 67 | 0 | 343 | 0 | `stop` | 1779 |
| 166 | 21 | 67 | 0 | 343 | 0 | `stop` | 2046 |
| 165 | 19 | 67 | 100 | 79 | 4 | `tool_calls` | 4962 |
| 164 | 17 | 67 | 97 | 118 | 62 | `tool_calls` | 2958 |
| 163 | 15 | 67 | 0 | 152 | 4 | `tool_calls` | 23569 |
| 162 | 13 | 65 | 2144 | 662 | 0 | `stop` | 30496 |

The key observation is that rows `166` through `181` repeatedly returned an
assistant turn that contained no user-visible content and no machine-readable
tool call, even though the reasoning stream showed that the model was trying to
call a tool.

## Direct Upstream Replay Verification

After the initial DB review, the exact request payload from captured row `181`
was replayed directly against the upstream OpenAI-compatible service. Endpoint
host and authentication details are omitted from this document.

Replay results:

- Runs: 8
- HTTP 200 responses: 8/8
- Valid JSON SSE streams: 8/8
- Streams ending with `data: [DONE]`: 8/8
- Runs matching the failure signature: 8/8
- Runs with structured `delta.tool_calls`: 0/8
- Runs with non-empty `delta.content`: 0/8
- Exceptions/timeouts: 0/8

Failure signature used for replay classification:

- `delta.content` reconstructed to an empty string.
- No `delta.tool_calls` chunks were emitted.
- `delta.reasoning_content` contained `<tool_call>`.
- Final finish reason was exactly `["stop"]`.
- Stream ended with `data: [DONE]`.
- No malformed SSE JSON chunks were encountered.

Per-run replay summary:

| Run | HTTP | Events | Content chars | Reasoning chars | Tool-call deltas | Finish reason | Duration ms |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | 200 | 77 | 0 | 343 | 0 | `stop` | 22933 |
| 2 | 200 | 77 | 0 | 343 | 0 | `stop` | 1761 |
| 3 | 200 | 77 | 0 | 343 | 0 | `stop` | 1760 |
| 4 | 200 | 81 | 0 | 353 | 0 | `stop` | 1837 |
| 5 | 200 | 77 | 0 | 343 | 0 | `stop` | 2655 |
| 6 | 200 | 77 | 0 | 343 | 0 | `stop` | 2039 |
| 7 | 200 | 77 | 0 | 343 | 0 | `stop` | 1787 |
| 8 | 200 | 77 | 0 | 343 | 0 | `stop` | 1734 |

This shows the failure is consistently reproducible by replaying the same
multi-turn Copilot request directly to the upstream service. It also removes the
record-only proxy from the reproduction path.

## Working vs Failing Requests

Some nearby requests did work, including later "plan review" requests captured
as rows `182` through `184`. The main differences were in the conversation
state and the kind of next action the model attempted.

Working plan-review flow:

- Rows: `182`, `183`, `184`
- Message counts: 3, 6, and 9
- Tool count: 66
- Previous tool before final answer: `read_file`
- Rows `182` and `183` emitted structured `delta.tool_calls` for `read_file`.
- Row `184` emitted a normal final answer in `delta.content`.
- No `<tool_call>` text appeared in `delta.reasoning_content`.

Failing execution flow:

- Rows: `166` through `181`
- Message count: 21
- Tool count: 67
- Previous tool before every failure: `manage_todo_list`
- Previous tool result before every failure:
  `Successfully wrote todo list`
- The model's intended next action was `run_in_terminal`.
- The response emitted `<tool_call><function=run_in_terminal>...` only inside
  `delta.reasoning_content`.
- No structured `delta.tool_calls` were emitted.
- No non-empty `delta.content` was emitted.
- The final finish reason was `stop`.

The failure is not simply caused by a long context or many tools. Other captures
with much longer histories still produced valid tool calls. It also is not
caused by the presence of 67 tools alone, because rows `164` and `165` had 67
tools and emitted valid structured tool calls.

The sharpest transition was:

| Row | Previous tool | Response result |
| ---: | --- | --- |
| 164 | `manage_todo_list` | Valid `run_in_terminal` tool call |
| 165 | `run_in_terminal` | Valid `manage_todo_list` tool call |
| 166 | `manage_todo_list` | Failed: `run_in_terminal` appeared only in `reasoning_content` |

This suggests a state-sensitive parser/template failure around a continuation
turn after `manage_todo_list`, where Qwen emits a terminal tool call in its
tagged pseudo-XML format but llama.cpp does not promote it into OpenAI
`tool_calls`.

## Failing Stream Shape

Sanitized excerpt from row `181`:

```json
{"delta":{"role":"assistant","content":null},"finish_reason":null}
{"delta":{"reasoning_content":"</think>"},"finish_reason":null}
{"delta":{"reasoning_content":"\n"},"finish_reason":null}
{"delta":{"reasoning_content":"\n<tool_call>"},"finish_reason":null}
{"delta":{"reasoning_content":"\n<function"},"finish_reason":null}
{"delta":{"reasoning_content":"="},"finish_reason":null}
{"delta":{"reasoning_content":"run"},"finish_reason":null}
{"delta":{"reasoning_content":"_in"},"finish_reason":null}
{"delta":{"reasoning_content":"_terminal"},"finish_reason":null}
{"delta":{"reasoning_content":">"},"finish_reason":null}
```

The reconstructed reasoning text begins like this:

```text
</think>

<tool_call>
<function=run_in_terminal>
<parameter=command>
...
```

The stream eventually finishes with:

```json
{"choices":[{"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

There is no corresponding OpenAI-compatible `delta.tool_calls` event.

## Expected Stream Shape

If the model intends to call a tool, an OpenAI-compatible streaming response
should emit structured tool-call deltas and finish with `tool_calls`, for
example:

```json
{
  "choices": [
    {
      "delta": {
        "tool_calls": [
          {
            "index": 0,
            "id": "call_...",
            "type": "function",
            "function": {
              "name": "run_in_terminal",
              "arguments": "{\"command\":\"...\"}"
            }
          }
        ]
      },
      "finish_reason": null
    }
  ]
}
```

And the final chunk should report:

```json
{
  "choices": [
    {
      "delta": {},
      "finish_reason": "tool_calls"
    }
  ]
}
```

If the model does not intend to call a tool, the user-visible answer should be
emitted through `delta.content`. It should not be emitted only through
`delta.reasoning_content`.

## Why Copilot Reports "No Response"

Copilot appears to treat the failed rows as empty assistant turns:

- No `delta.content` means there is no visible assistant message to display.
- No `delta.tool_calls` means there is no tool action to execute.
- `finish_reason: "stop"` tells the client the assistant turn is complete.

This leaves the client with a successful but semantically empty completion. The
observed UI then retries and eventually shows:

```text
Sorry, no response was returned.
```

## Reproduction Path

The strongest reproduction path is to use VS Code GitHub Copilot Chat Agent mode
against a llama.cpp OpenAI-compatible endpoint serving a Qwen3.6 35B-A3B GGUF.

1. Start `llama-server` with a Qwen3.6 35B-A3B GGUF model and OpenAI-compatible
   chat-completion endpoint enabled.
2. Configure VS Code GitHub Copilot Chat Agent mode to use that endpoint,
   directly or through a transparent proxy.
3. Start an agentic task that requires shell/file tools.
4. Let the conversation proceed through several assistant/tool turns.
5. Observe that early turns may emit valid `tool_calls`, but later turns can
   switch to emitting Qwen pseudo-XML tool calls inside `reasoning_content`.
6. Capture the streaming response from `/v1/chat/completions`.
7. Check whether a failed stream has:
   - `HTTP 200`
   - `content-type: text/event-stream`
   - `data: [DONE]`
   - no malformed SSE JSON
   - `delta.reasoning_content` containing `<tool_call>`
   - no `delta.tool_calls`
   - no non-empty `delta.content`
   - final `finish_reason: "stop"`

The captured request shape that reproduced the issue was:

```json
{
  "model": "qwen_3.6_35B_4bit",
  "stream": true,
  "stream_options": {"include_usage": true},
  "n": 1,
  "temperature": "...",
  "top_p": "...",
  "messages": [
    "... multi-turn user/assistant/tool history ..."
  ],
  "tools": [
    "... 67 OpenAI-style function tools ..."
  ]
}
```

The last roles before a failing response looked like:

```text
assistant, user, assistant, tool, assistant, tool, assistant, tool
```

This suggests the bug may require multi-turn agent state, not just a single
first-turn tool request.

## Notes For a Smaller Repro

If a smaller repro is needed, start with:

- A single OpenAI function tool named `run_in_terminal`.
- A user prompt that asks the model to run a command.
- Streaming enabled.
- Thinking enabled, because Qwen3.6 models operate in thinking mode by default.
- At least one prior assistant/tool exchange in history.

Example minimal request shape:

```json
{
  "model": "qwen_3.6_35B_4bit",
  "stream": true,
  "stream_options": {"include_usage": true},
  "messages": [
    {
      "role": "user",
      "content": "Create a Python virtual environment in the current project."
    },
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_1",
          "type": "function",
          "function": {
            "name": "run_in_terminal",
            "arguments": "{\"command\":\"pwd\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_1",
      "content": "./project"
    },
    {
      "role": "user",
      "content": "Now create the venv."
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "run_in_terminal",
        "description": "Run a shell command.",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {"type": "string"}
          },
          "required": ["command"]
        }
      }
    }
  ]
}
```

The issue is reproduced if the response contains a pseudo-XML tool call only in
`reasoning_content`, with no OpenAI `tool_calls` delta.

## Related Public Reports

These public reports appear closely related:

- llama.cpp issue #20260: Qwen3.5 35B-A3B with GitHub Copilot Chat Agent mode
  can fail during multi-turn tool-calling when thinking text precedes
  `<tool_call>`.
  <https://github.com/ggml-org/llama.cpp/issues/20260>
- llama.cpp issue #21771: Qwen3 TAG_WITH_TAGGED tool format can leak partial
  tool-call state to the client and poison multi-turn history.
  <https://github.com/ggml-org/llama.cpp/issues/21771>
- llama.cpp issue #22072: Qwen3.6 35B-A3B tool-calling problems with malformed
  or incomplete tool arguments.
  <https://github.com/ggml-org/llama.cpp/issues/22072>
- Qwen3.6 35B-A3B model card: Qwen3.6 models operate in thinking mode by
  default and Qwen documents explicit reasoning/tool parsers for vLLM/SGLang.
  <https://huggingface.co/Qwen/Qwen3.6-35B-A3B>
- llama.cpp function-calling docs: OpenAI-style function calling support and
  supported native tool-call formats.
  <https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md>

## Possible Mitigations To Test

These are not confirmed fixes from this capture, but they are useful experiments:

1. Upgrade llama.cpp to the latest commit and retest.
2. Disable Qwen thinking mode for tool-calling sessions if the server supports
   passing chat-template kwargs, for example `enable_thinking: false`.
3. Try a Qwen-specific parser/server stack known to support this model family,
   such as vLLM or SGLang with Qwen reasoning and tool-call parsers.
4. Test whether a llama.cpp chat-template change prevents `<tool_call>` from
   appearing inside reasoning output.
5. As a last resort, add a proxy-side compatibility shim that rewrites
   `<tool_call>` inside `reasoning_content` into OpenAI `tool_calls`. This would
   be brittle because it requires parsing model-generated XML-like text from a
   reasoning stream.

## Fill Before Filing

The local proxy machine did not expose the remote `llama-server` process, so add
these fields before filing upstream:

- llama.cpp commit or release.
- Full `llama-server` launch command.
- Exact GGUF source and quantization file.
- Whether `--jinja`, custom chat templates, or chat-template kwargs were used.
- Whether thinking was enabled, disabled, or left at the Qwen3.6 default.
- Operating system, CPU/GPU backend, and relevant hardware.
- Whether the same request works with non-streaming mode.

## Draft llama.cpp Issue

Title:

```text
Qwen3.6-35B-A3B streams tool calls only in reasoning_content as <tool_call>, no delta.tool_calls, causing OpenAI clients to see empty responses
```

Body:

````markdown
### Problem description

I am using `llama-server` as an OpenAI-compatible backend for VS Code GitHub
Copilot Chat Agent mode with a Qwen3.6 35B-A3B GGUF model. In multi-turn
agentic workflows, the server sometimes returns `HTTP 200` streaming chat
completion responses that are valid SSE, but unusable for OpenAI-compatible
clients.

The model appears to intend a tool call, but the streamed response contains the
tool-call text only in `delta.reasoning_content` as Qwen pseudo-XML:

```text
</think>

<tool_call>
<function=run_in_terminal>
<parameter=command>
...
```

There is no corresponding OpenAI-compatible `delta.tool_calls` event, no
non-empty `delta.content`, and the final chunk has `finish_reason: "stop"`
instead of `finish_reason: "tool_calls"`.

VS Code Copilot then reports:

```text
Autopilot recovered from a request error
Sorry, no response was returned.
```

### Expected behavior

If the model intends to call a tool, llama.cpp should stream OpenAI-compatible
`delta.tool_calls` chunks and finish with `finish_reason: "tool_calls"`.

If the model is producing a normal assistant answer, user-visible text should be
streamed in `delta.content`.

The client should not receive a successful assistant turn where the only
meaningful output is hidden inside `delta.reasoning_content`.

### Actual behavior

The server returns a successful stream:

- `HTTP 200`
- `content-type: text/event-stream`
- parseable JSON SSE chunks
- final `data: [DONE]`

But the failed assistant turn has:

- `delta.content`: `null` or absent
- `delta.tool_calls`: absent
- `delta.reasoning_content`: contains `<tool_call>...`
- final `finish_reason`: `"stop"`

Sanitized stream excerpt:

```json
{"delta":{"role":"assistant","content":null},"finish_reason":null}
{"delta":{"reasoning_content":"</think>"},"finish_reason":null}
{"delta":{"reasoning_content":"\n"},"finish_reason":null}
{"delta":{"reasoning_content":"\n<tool_call>"},"finish_reason":null}
{"delta":{"reasoning_content":"\n<function"},"finish_reason":null}
{"delta":{"reasoning_content":"="},"finish_reason":null}
{"delta":{"reasoning_content":"run"},"finish_reason":null}
{"delta":{"reasoning_content":"_in"},"finish_reason":null}
{"delta":{"reasoning_content":"_terminal"},"finish_reason":null}
{"delta":{"reasoning_content":">"},"finish_reason":null}
...
{"choices":[{"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

### Local capture summary

I captured the last 20 requests through a transparent, record-only OpenAI proxy.
The proxy forwards upstream chunks unchanged and stores the final request and
response bodies in SQLite.

Client:

- VS Code GitHub Copilot Chat Agent mode
- User agent: `GitHubCopilotChat/0.47.2026043003`
- Upstream: OpenAI-compatible `/v1/chat/completions` endpoint
  (host redacted)

Environment details to fill in:

- llama.cpp commit/release:
- Full `llama-server` command:
- GGUF source and quantization file:
- Chat template or `--jinja` settings:
- Chat-template kwargs, if any:
- OS and backend:
- GPU/CPU hardware:

Request shape:

- Endpoint: `POST /v1/chat/completions`
- `stream: true`
- `stream_options: {"include_usage": true}`
- 65 to 67 OpenAI-style function tools
- Multi-turn history containing prior `assistant` tool calls and `tool` results

Model identifiers:

- Request model: `qwen_3.6_35B_4bit`
- Response model: `Qwen3.6-35B-A3B-MXFP4_MOE.gguf`

Recent 20 response summary:

| Pattern | Count |
| --- | ---: |
| No `content`, has `reasoning_content`, no `tool_calls`, `finish_reason: "stop"` | 16 |
| Has `content`, has `reasoning_content`, has `tool_calls`, `finish_reason: "tool_calls"` | 2 |
| No `content`, has `reasoning_content`, has `tool_calls`, `finish_reason: "tool_calls"` | 1 |
| Has `content`, has `reasoning_content`, no `tool_calls`, `finish_reason: "stop"` | 1 |

All 20 responses were `HTTP 200` and ended with `data: [DONE]`.

I then replayed the exact captured request payload from one failing row directly
to the upstream service. Endpoint host and authentication details are omitted
from this report. That reproduced the failure signature 8/8 times:

- 8/8 returned `HTTP 200`
- 8/8 were valid JSON SSE streams ending in `data: [DONE]`
- 8/8 had no non-empty `delta.content`
- 8/8 had no structured `delta.tool_calls`
- 8/8 contained `<tool_call>` in `delta.reasoning_content`
- 8/8 finished with `finish_reason: "stop"`

### Steps to reproduce

1. Serve a Qwen3.6 35B-A3B GGUF model with `llama-server` using the
   OpenAI-compatible `/v1/chat/completions` endpoint.
2. Configure VS Code GitHub Copilot Chat Agent mode, or another
   OpenAI-compatible tool-calling client, to use that endpoint.
3. Run a multi-turn agent task that uses shell/file tools.
4. Capture the streaming response from `/v1/chat/completions`.
5. Continue until a later tool turn returns a stream where the model emits
   `<tool_call>` inside `delta.reasoning_content`.

The failing request shape was:

```json
{
  "model": "qwen_3.6_35B_4bit",
  "stream": true,
  "stream_options": {"include_usage": true},
  "messages": ["multi-turn user/assistant/tool history"],
  "tools": ["OpenAI-style function tools"]
}
```

The last roles before one failing response were:

```text
assistant, user, assistant, tool, assistant, tool, assistant, tool
```

### Why this seems llama.cpp/Qwen parsing related

The transport layer appears healthy: status 200, valid SSE, no proxy mutation,
and clean `[DONE]`.

The failure is semantic: Qwen-style `<tool_call>` text is present, but it is
streamed as reasoning rather than converted into OpenAI `tool_calls`.

This resembles existing Qwen/llama.cpp tool-call parser issues around thinking
text, Qwen tagged tool-call formats, and multi-turn tool-call history:

- https://github.com/ggml-org/llama.cpp/issues/20260
- https://github.com/ggml-org/llama.cpp/issues/21771
- https://github.com/ggml-org/llama.cpp/issues/22072

### Additional notes

Qwen3.6 models operate in thinking mode by default. It may be relevant that the
tool call appears after `</think>` but is still emitted through
`reasoning_content`, so OpenAI-compatible clients do not treat it as assistant
content or as a tool call.

I can provide sanitized request/response captures if useful.
````
