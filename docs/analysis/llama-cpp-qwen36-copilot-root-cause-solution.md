# llama.cpp Qwen3.6 Copilot Tool Calling: Issue, Root Cause, and Solution

Date: 2026-05-02

This document summarizes the Qwen3.6/Copilot tool-calling failure observed via
`llm-observe-proxy`, the likely llama.cpp parser root cause, the fix tested in
`shamitv/llama.cpp`, and how the same work relates to other reported upstream
llama.cpp issues.

Primary local evidence:

- Original failure analysis:
  `docs/analysis/llama-cpp-qwen36-copilot-tool-calling.md`
- Fix impact analysis:
  `docs/analysis/llama-cpp-qwen36-copilot-tool-calling-fix-impact.md`
- Fix branch:
  <https://github.com/shamitv/llama.cpp/tree/fix/qwen-reasoning-tool-calls>

Public related reports checked on 2026-05-02:

- <https://github.com/ggml-org/llama.cpp/issues/20260>
- <https://github.com/ggml-org/llama.cpp/issues/21771>
- <https://github.com/ggml-org/llama.cpp/issues/22072>

All three public reports were still open when checked. The status below is
therefore based on local validation and code review, not upstream issue closure.

## Issue Description

VS Code GitHub Copilot Chat Agent mode was configured to use a llama.cpp
OpenAI-compatible endpoint serving `Qwen3.6-35B-A3B-MXFP4_MOE.gguf`.

During multi-turn agent workflows, Copilot repeatedly received successful
streaming chat-completion responses that were valid at the transport layer but
empty at the OpenAI client layer:

- HTTP status was `200`.
- Response type was `text/event-stream`.
- SSE chunks were parseable JSON.
- Streams ended with `data: [DONE]`.
- There were no proxy or upstream connection errors.

However, the assistant turn had no usable OpenAI payload:

- No non-empty `delta.content`.
- No `delta.tool_calls`.
- Final `finish_reason` was `"stop"`, not `"tool_calls"`.
- The model's intended tool call appeared only inside
  `delta.reasoning_content`.

The leaked model text looked like Qwen tagged tool-call syntax:

```text
</think>

<tool_call>
<function=run_in_terminal>
<parameter=command>
...
```

From Copilot's perspective this is a completed assistant turn with no message
to show and no tool to execute. The observed client symptom was:

```text
Autopilot recovered from a request error
Sorry, no response was returned.
```

The local proxy did not cause the failure. A direct replay of the exact captured
request against the upstream llama.cpp-compatible endpoint reproduced the same
empty OpenAI response shape 8 out of 8 times.

### Problematic LLM Response Snippets

The problematic responses were not malformed at the SSE layer. They were
problematic because the model's intended tool call was streamed as
`reasoning_content`, while the OpenAI-compatible fields that Copilot consumes
remained empty.

Sanitized chunks from a failing stream show the assistant starting with no
visible content and then leaking a Qwen tagged tool call through reasoning:

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

Reconstructed, the meaningful model text looked like a valid Qwen tagged tool
call, but it was in the wrong response field:

```text
</think>

<tool_call>
<function=run_in_terminal>
<parameter=command>
...
```

The same stream then ended as a normal stopped assistant turn rather than as a
tool-call turn:

```json
{"choices":[{"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

The missing piece was any corresponding structured OpenAI tool-call delta:

```json
{"delta":{"tool_calls":[{"index":0,"function":{"name":"run_in_terminal","arguments":"..."}}]}}
```

Because that `delta.tool_calls` shape never appeared, Copilot received a
successful but semantically empty assistant response.

## Root Cause

The failure was in the interaction between Qwen reasoning output, tagged
tool-call syntax, and llama.cpp's generated PEG parser for OpenAI-compatible
tool calls.

There were two related parser gaps.

### 1. Empty Thinking Close Did Not Match the Parser Shape

Qwen thinking models can begin a generated assistant turn by closing an empty
thinking section:

```text
</think>

<tool_call>
...
```

The parser does not always parse only the raw generated text. It reconstructs an
effective input by prefixing the generated text with the chat template's
generation prompt. In this path, the generated parser's `thinking_end_tag` can
include leading whitespace, while the model output may start directly with the
non-whitespace marker `</think>`.

Before the fix, `common_chat_peg_parse()` simply concatenated:

```text
generation_prompt + input
```

That could produce an effective parser input where the thinking end marker did
not match the parser's expected end tag. Once the parser failed to recognize the
reasoning boundary, the following `<tool_call>` block stayed inside
`reasoning_content` instead of being promoted to OpenAI `tool_calls`.

This matches the local failure rows: the model was trying to call
`run_in_terminal`, but Copilot received no structured tool call.

### 2. Required Tool Mode Was Too Strict About Text Before `<tool_call>`

Another Qwen-family pattern is:

```text
</think>

Let me inspect the current directory.
<tool_call>
...
```

When tool choice is required, the tagged tool-call parser previously forced the
post-reasoning output to begin directly with the tool-call marker. That was too
strict for real Qwen outputs, which may emit a short transition sentence between
the reasoning block and the tool call.

This is the same broad parser shape reported in llama.cpp issue #20260, where a
Qwen3.5 thinking model used behind Copilot emitted text before `<tool_call>` and
the server failed to parse the completed assistant output.

## Solution

The tested fix branch changes the parser, not the proxy and not the client.

Production parser changes:

- `common_chat_parser_params` now carries `thinking_start_tag` and
  `thinking_end_tag` from the chat template parameters.
- `common_chat_peg_parse()` reconstructs the effective parser input more
  carefully when:
  - the generation prompt ends at the thinking start tag,
  - the model begins by closing the thinking block, and
  - the parser's thinking end tag has leading whitespace.
- In that case, the parser inserts the expected leading whitespace before the
  model's `</think>` marker so the reasoning boundary matches.
- The tagged tool-call autoparser now permits optional post-reasoning assistant
  content before `<tool_call>` when reasoning extraction is active, even under
  required-tool mode.

Regression coverage added or strengthened:

- Qwen tagged tool call immediately after `</think>`.
- Qwen transition content between `</think>` and `<tool_call>`.
- Required-tool mode with transition content before `<tool_call>`.
- Copilot-shaped multi-turn history:
  - user asks for work,
  - assistant calls `manage_todo_list`,
  - tool returns `Successfully wrote todo list`,
  - assistant then emits a `run_in_terminal` tagged tool call.
- Safety case where a `<tool_call>` block inside active thinking remains
  `reasoning_content` and is not executed as a tool.
- OpenAI compatibility checks that streamed tool-call arguments are JSON
  strings and that tool-call turns finish with `finish_reason: "tool_calls"`.

The fix preserves the important safety boundary:

- Tool-looking text before the reasoning end marker stays reasoning-only.
- Tool-looking text after the reasoning end marker is eligible for structured
  OpenAI `tool_calls`.

No proxy-side compatibility shim was needed. `llm-observe-proxy` remains a
record-only proxy.

## Local Validation

Before the fix, the primary failure window was rows `162` through `181`:

| Metric | Before |
| --- | ---: |
| Rows reviewed | 20 |
| Empty reasoning tool leaks | 16 |
| Structured tool-call turns | 3 |
| Normal content answers | 1 |
| Final `finish_reason: "stop"` | 17 |
| Final `finish_reason: "tool_calls"` | 3 |
| Responses containing `<tool_call>` in `reasoning_content` | 16 |

After testing branch head `e9eddd0193ca38d9a608155df65e92a3b1032e9e`, the
server fingerprint changed to `b9014-e9eddd019`. The last-hour rows reviewed
were `185` through `226`:

| Metric | After |
| --- | ---: |
| Rows reviewed | 42 |
| Empty reasoning tool leaks | 0 |
| Structured tool-call turns | 41 |
| Normal content answers | 1 |
| Final `finish_reason: "stop"` | 1 |
| Final `finish_reason: "tool_calls"` | 41 |
| Responses containing `<tool_call>` in `reasoning_content` | 0 |
| Reconstructed tool calls with valid JSON arguments | 42/42 |

The after run also progressed further than the failing run:

- Before failure repeated around 21 messages and 67 tools.
- After validation reached 109 messages, 68 tools, and about 49k total tokens.

This supports treating the branch as a full fix for the local
Qwen3.6/Copilot failure mode.

## Related Issue Status

| Report | Status from this work | Notes |
| --- | --- | --- |
| Local Qwen3.6/Copilot empty response capture | Fully fixed locally | The exact observed failure signature went from 16/20 before rows to 0/42 after rows. |
| llama.cpp #20260: Qwen3.5 Copilot parser fails when text appears before `<tool_call>` | Functionally fixed for the reported parser shape, pending upstream confirmation | The branch directly changes the required-tool tagged parser to allow post-reasoning text before `<tool_call>` and adds regression coverage for this shape. The public issue remains open. |
| llama.cpp #21771: Qwen3 tagged format fails on `array<object>` parameter values and leaks partial arguments | Partially addressed at most | This branch improves adjacent OpenAI streaming and argument-string validation, but it does not directly replace the `p.json()` path for nested `array<object>` values inside tagged `<parameter>` blocks. A dedicated `firecrawl_search.sources`-style fixture is still needed. |
| llama.cpp #22072: malformed or incomplete JSON arguments for simple object schemas | Partially addressed / locally improved | The after capture reconstructed 42 tool calls with 42 valid JSON argument strings, and tests now assert JSON-string arguments and streamed finish reasons. The specific ChatWise `thread_fetch_messages` reproduction has not been proven fixed. |

## Practical Outcome

The fix moves Copilot from a retry/error loop to normal agent operation for the
tested Qwen3.6 setup:

- `run_in_terminal`, `read_file`, `get_terminal_output`,
  `manage_todo_list`, `replace_string_in_file`, and `kill_terminal` were all
  emitted as structured OpenAI tool calls in the after capture.
- Copilot could continue through a long multi-turn workflow.
- The server no longer returned semantically empty successful responses for the
  captured failure pattern.

## Remaining Work

For a stronger upstream PR or issue-closing argument:

- Add a sanitized fixture from the exact Qwen3.6 failing stream.
- Add a dedicated #21771-style `array<object>` tagged-parameter fixture.
- Add a #22072-style fixture for the simple-object schema that produced
  malformed or incomplete arguments in ChatWise.
- Update or omit branch-local `docs/plans/` notes that still say no production
  parser code changed; that wording is stale for the current branch.
