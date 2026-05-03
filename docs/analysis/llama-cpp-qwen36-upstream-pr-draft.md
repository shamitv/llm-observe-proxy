# Upstream llama.cpp PR Draft: Qwen Reasoning Tool-Call Parsing

Date: 2026-05-02

## PR Title

server: fix Qwen reasoning tagged tool-call parsing

## Related Reported Issues

Checked on 2026-05-02. All listed issues were open at the time of this draft.

| Issue | Status | Relationship to this PR |
| --- | --- | --- |
| <https://github.com/ggml-org/llama.cpp/issues/20260> | Open | Directly addressed. Qwen thinking models can emit transition text before `<tool_call>`, causing `peg-native` parsing to fail. |
| <https://github.com/ggml-org/llama.cpp/issues/21771> | Open | Related parser/streaming failure. This PR improves adjacent Qwen tagged tool-call handling, but a dedicated `array<object>` parameter fixture is still needed before claiming a full fix. |
| <https://github.com/ggml-org/llama.cpp/issues/22072> | Open | Related OpenAI-compatible tool-call argument failure. Local validation shows valid JSON arguments after this fix, but the specific ChatWise `thread_fetch_messages` reproduction is not yet proven fixed. |

Issue titles:

- #20260: Eval bug: unsloth/Qwen3.5-35B-A3B-GGUF `peg-native` chat format parser fails when model outputs text before `<tool_call>` (thinking model + tool calling)
- #21771: Qwen3 TAG_WITH_TAGGED tool format: p.json() fails on array<object> parameter values; partial tool_call leaked to client poisons multi-turn history
- #22072: Eval bug: llama-server OpenAI-compatible tool calling sometimes emits malformed/incomplete JSON arguments for simple object schemas

## PR Body

### Summary

This PR fixes a Qwen thinking-model tool-calling parser failure in the
OpenAI-compatible server path.

Qwen reasoning models can produce assistant turns shaped like:

```text
</think>

<tool_call>
<function=run_in_terminal>
<parameter=command>
...
```

or:

```text
</think>

Let me inspect the current directory.
<tool_call>
...
```

Before this change, those outputs could fail to become OpenAI-compatible
`tool_calls`. Depending on the path, the server either failed PEG parsing or
streamed the model's intended tool call as `reasoning_content`, with no
`delta.tool_calls` and a final `finish_reason: "stop"`.

For clients such as GitHub Copilot Chat Agent mode, that produces a successful
but semantically empty assistant turn: no visible content and no executable
tool call.

### Problem

There were two parser gaps in the Qwen tagged tool-call path.

First, the post-generation parser reconstructs an effective input from the chat
template generation prompt and the generated model text. For Qwen thinking
models, the generation prompt can end at the thinking start tag while the model
starts by closing an empty thinking block:

```text
</think>

<tool_call>
...
```

When the configured `thinking_end_tag` includes leading whitespace, simple
concatenation can produce an input where the reasoning boundary is not matched.
The following `<tool_call>` then remains reasoning text instead of being
promoted to an OpenAI tool call.

Second, required-tool parsing was too strict when reasoning extraction was
active. It expected post-reasoning output to start directly at `<tool_call>`.
Real Qwen outputs may include a short natural-language transition before the
tool call, which is the same parser shape reported in #20260.

### Fix

This PR updates the chat parser path so:

- `common_chat_parser_params` carries the chat template's
  `thinking_start_tag` and `thinking_end_tag`.
- `common_chat_peg_parse()` handles the Qwen empty-thinking-close case by
  reconstructing the parser input with the expected leading whitespace before
  the generated `</think>` marker.
- The tagged tool-call autoparser allows optional post-reasoning assistant
  content before `<tool_call>` when reasoning extraction is active, including
  required-tool mode.

The safety boundary is preserved:

- Tool-looking text before the reasoning end marker remains reasoning-only.
- Tool-looking text after the reasoning end marker can be parsed into
  structured OpenAI `tool_calls`.

### Validation

Local validation was done with VS Code GitHub Copilot Chat Agent mode against a
llama.cpp OpenAI-compatible endpoint serving
`Qwen3.6-35B-A3B-MXFP4_MOE.gguf`.

Before the fix:

| Metric | Count |
| --- | ---: |
| Captured rows reviewed | 20 |
| Empty reasoning tool leaks | 16 |
| Structured tool-call turns | 3 |
| Final `finish_reason: "stop"` | 17 |
| Responses containing `<tool_call>` in `reasoning_content` | 16 |

The same captured failing request replayed directly against the upstream server
reproduced the empty OpenAI response shape 8 out of 8 times.

After the fix:

| Metric | Count |
| --- | ---: |
| Captured rows reviewed | 42 |
| Empty reasoning tool leaks | 0 |
| Structured tool-call turns | 41 |
| Final `finish_reason: "tool_calls"` | 41 |
| Responses containing `<tool_call>` in `reasoning_content` | 0 |
| Reconstructed tool calls with valid JSON arguments | 42/42 |

The after run progressed to 109 messages, 68 tools, and about 49k total tokens.
The earlier failure repeated around 21 messages and 67 tools.

### Tests

Regression coverage added or strengthened for:

- Qwen tagged tool call immediately after `</think>`.
- Qwen transition text between `</think>` and `<tool_call>`.
- Required-tool mode with transition text before `<tool_call>`.
- Copilot-shaped multi-turn history:
  - user asks for work,
  - assistant calls `manage_todo_list`,
  - tool returns `Successfully wrote todo list`,
  - assistant emits a `run_in_terminal` tagged tool call.
- Negative safety case where a `<tool_call>` block inside active thinking
  remains `reasoning_content` and is not executed as a tool.
- OpenAI-compatible streaming checks that function `arguments` are JSON strings
  and tool-call turns finish with `finish_reason: "tool_calls"`.

### Notes

This should directly address #20260's text-before-`<tool_call>` parser shape.

It is related to #21771 and #22072 because they involve Qwen tagged tool-call
parsing, streamed tool-call state, and malformed or incomplete OpenAI tool-call
arguments. However, this PR should not be claimed as a complete fix for those
two issues until dedicated reproductions are added:

- #21771 needs an `array<object>` parameter fixture such as
  `firecrawl_search.sources`.
- #22072 needs the reported simple-object `thread_fetch_messages` fixture.
