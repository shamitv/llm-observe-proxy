# llama.cpp Qwen3.6 Copilot Tool-Calling Fix Impact

Date: 2026-05-02

This note compares the original Copilot/Qwen3.6 failure capture in
`docs/analysis/llama-cpp-qwen36-copilot-tool-calling.md` with the latest
`llm-observe-proxy` captures after testing the llama.cpp branch:

<https://github.com/shamitv/llama.cpp/tree/fix/qwen-reasoning-tool-calls>

The short version: the last-hour Copilot run no longer shows the original
failure signature. The old server fingerprint repeatedly leaked Qwen tagged
tool calls through `delta.reasoning_content` and ended those turns with
`finish_reason: "stop"`. The new server fingerprint emits structured
OpenAI-compatible `delta.tool_calls` and ends tool turns with
`finish_reason: "tool_calls"`.

## Scope

Local proxy database:

- DB: `llm_observe_proxy.sqlite3`
- Endpoint: `POST /v1/chat/completions`
- Model requested by client: `qwen_3.6_35B_4bit`
- Response model: `Qwen3.6-35B-A3B-MXFP4_MOE.gguf`
- All timestamps below are UTC.

Before baseline:

- Primary failing rows: `162` through `181`
- Captured: `2026-05-01 11:47:17` through `2026-05-01 11:50:33`
- Server fingerprint: `b8992-5cbfb1807`

After window:

- Last-hour rows reviewed: `185` through `226`
- Captured: `2026-05-02 11:58:10` through `2026-05-02 12:10:55`
- Server fingerprint: `b9014-e9eddd019`
- The fingerprint suffix matches branch head
  `e9eddd0193ca38d9a608155df65e92a3b1032e9e`.

Method:

- Parsed captured SSE response bodies from SQLite.
- Reconstructed `delta.content`, `delta.reasoning_content`, and
  `delta.tool_calls`.
- Counted final `finish_reason` values, JSON parse errors, stream completion,
  tool names, message counts, tool counts, and token usage.

## llama.cpp Branch Review

Compared with `shamitv/llama.cpp` `master` at
`63d93d17336e41e4cc73a64451e5b1d2477abdb1`, branch
`fix/qwen-reasoning-tool-calls` contains 7 commits and changes 9 files:

- Production parser path:
  - `common/chat.cpp`
  - `common/chat.h`
  - `common/chat-auto-parser-generator.cpp`
- Test coverage:
  - `tests/test-chat.cpp`
  - `tools/server/tests/unit/test_tool_call.py`
  - `tools/server/tests/utils.py`
- Local planning docs:
  - `docs/plans/qwen-copilot-tool-calling-fix.md`
  - `docs/plans/qwen-copilot-tool-calling-implementation-summary.md`
  - `docs/plans/qwen-copilot-tool-calling-pr-notes.md`

Important behavior changes:

- `common_chat_parser_params` now carries `thinking_start_tag` and
  `thinking_end_tag` from `common_chat_params`.
- `common_chat_peg_parse()` now reconstructs the effective parser input more
  carefully when a generation prompt ends at the thinking start tag and the
  model begins by closing an empty thinking block. This covers Qwen streams
  that start with `</think>` while the parser's configured end tag contains
  leading whitespace.
- The tagged tool-call autoparser now allows post-reasoning assistant content
  before a tool call when tools are required and reasoning extraction is active.
  This matches Qwen outputs shaped like:

```text
</think>

Let me inspect the current directory.
<tool_call>
<function=run_in_terminal>
...
```

Test coverage added or strengthened:

- Pure Qwen tagged tool call after `</think>`.
- Post-thinking content followed by a tagged tool call.
- Required tool-choice with post-thinking content before a tagged tool call.
- Copilot-shaped multi-turn history:
  `manage_todo_list` assistant call, matching tool result, then
  `run_in_terminal`.
- Negative safety case where a `<tool_call>` block inside active thinking
  remains `reasoning_content` and is not promoted into an executable tool call.
- Server test helpers now assert streamed `finish_reason` from the choice object
  and verify OpenAI function `arguments` are JSON strings.

Review note:

- The branch-local files under `docs/plans/` still contain older wording saying
  no production parser or server code changed. That is stale for the current
  branch, because `common/chat.cpp`, `common/chat.h`, and
  `common/chat-auto-parser-generator.cpp` do contain production parser changes.

## Before vs After

| Metric | Before primary rows `162`-`181` | After rows `185`-`226` |
| --- | ---: | ---: |
| Rows reviewed | 20 | 42 |
| HTTP 200 | 20 | 42 |
| `text/event-stream` | 20 | 42 |
| Valid JSON SSE streams | 20 | 42 |
| Streams ending in `data: [DONE]` | 20 | 42 |
| Structured tool-call turns | 3 | 41 |
| Normal content-answer turns | 1 | 1 |
| Empty reasoning tool leaks | 16 | 0 |
| Responses with `<tool_call>` in `reasoning_content` | 16 | 0 |
| Final `finish_reason: "tool_calls"` | 3 | 41 |
| Final `finish_reason: "stop"` | 17 | 1 |
| Message-count range | 13-21 | 24-109 |
| Tool-count range | 65-67 | 67-68 |
| Total-token range | 27,786-30,770 | 29,991-49,131 |
| Median duration | 1,917.5 ms | 3,315 ms |

The key impact is not just that simpler requests worked. The after window kept
working as the Copilot conversation grew to 109 messages, 68 tools, and about
49k total tokens. The earlier failure repeated at only 21 messages and 67
tools.

## Before Signature

The original failure was a semantically empty assistant turn:

- `delta.content` was absent or empty.
- `delta.tool_calls` was absent.
- `delta.reasoning_content` contained Qwen tagged tool text such as
  `<tool_call><function=run_in_terminal>...`.
- The final chunk reported `finish_reason: "stop"`.
- The stream itself was otherwise healthy: HTTP 200, valid SSE JSON, and
  `data: [DONE]`.

That left Copilot with no visible answer and no executable tool call, producing
the observed "Sorry, no response was returned" behavior.

## After Signature

The last-hour after window shows the OpenAI-compatible shape Copilot needs:

- Tool turns emit streamed `delta.tool_calls`.
- Tool turns finish with `finish_reason: "tool_calls"`.
- No row leaked `<tool_call>` tags inside `reasoning_content`.
- The one non-tool turn, row `226`, emitted normal `delta.content` and finished
  with `finish_reason: "stop"`.
- All streams were valid JSON SSE and ended with `data: [DONE]`.

Tool calls reconstructed in the after window:

| Tool | Turns |
| --- | ---: |
| `run_in_terminal` | 21 |
| `read_file` | 7 |
| `get_terminal_output` | 6 |
| `manage_todo_list` | 4 |
| `replace_string_in_file` | 3 |
| `kill_terminal` | 1 |

## After Rows

`Tool deltas` counts streamed tool-call delta chunks, not distinct tool calls.
`Tool` is the reconstructed function name.

| ID | Created UTC | Messages | Tools | Content chars | Reasoning chars | Tool deltas | Tool | Finish | Duration ms | Total tokens |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |
| 185 | 2026-05-02 11:58:10 | 24 | 67 | 0 | 179 | 57 | `run_in_terminal` | `tool_calls` | 22872 | 29991 |
| 186 | 2026-05-02 11:58:36 | 26 | 67 | 0 | 72 | 55 | `run_in_terminal` | `tool_calls` | 5998 | 30320 |
| 187 | 2026-05-02 11:58:48 | 28 | 67 | 0 | 68 | 46 | `run_in_terminal` | `tool_calls` | 2396 | 30560 |
| 188 | 2026-05-02 12:00:42 | 30 | 67 | 0 | 127 | 64 | `run_in_terminal` | `tool_calls` | 3131 | 31121 |
| 189 | 2026-05-02 12:03:05 | 32 | 67 | 88 | 103 | 4 | `manage_todo_list` | `tool_calls` | 4149 | 31514 |
| 190 | 2026-05-02 12:03:09 | 34 | 67 | 0 | 152 | 44 | `read_file`, `read_file` | `tool_calls` | 3071 | 31670 |
| 191 | 2026-05-02 12:03:12 | 37 | 67 | 0 | 139 | 50 | `run_in_terminal` | `tool_calls` | 2834 | 32205 |
| 192 | 2026-05-02 12:03:25 | 39 | 67 | 0 | 80 | 96 | `run_in_terminal` | `tool_calls` | 3361 | 32473 |
| 193 | 2026-05-02 12:03:32 | 41 | 67 | 201 | 215 | 4 | `manage_todo_list` | `tool_calls` | 4792 | 32925 |
| 194 | 2026-05-02 12:03:37 | 43 | 67 | 0 | 65 | 41 | `run_in_terminal` | `tool_calls` | 2239 | 33004 |
| 195 | 2026-05-02 12:03:39 | 45 | 67 | 52 | 91 | 37 | `run_in_terminal` | `tool_calls` | 2486 | 33240 |
| 196 | 2026-05-02 12:03:46 | 47 | 67 | 106 | 546 | 77 | `run_in_terminal` | `tool_calls` | 5632 | 34142 |
| 197 | 2026-05-02 12:04:00 | 49 | 67 | 201 | 217 | 34 | `run_in_terminal` | `tool_calls` | 4437 | 34876 |
| 198 | 2026-05-02 12:04:04 | 51 | 67 | 66 | 141 | 4 | `manage_todo_list` | `tool_calls` | 3937 | 35162 |
| 199 | 2026-05-02 12:04:08 | 53 | 67 | 0 | 167 | 52 | `run_in_terminal` | `tool_calls` | 2732 | 35286 |
| 200 | 2026-05-02 12:04:15 | 55 | 67 | 0 | 85 | 52 | `run_in_terminal` | `tool_calls` | 2491 | 35511 |
| 201 | 2026-05-02 12:04:49 | 57 | 67 | 0 | 62 | 51 | `run_in_terminal` | `tool_calls` | 3344 | 36252 |
| 202 | 2026-05-02 12:06:21 | 59 | 67 | 0 | 115 | 34 | `run_in_terminal` | `tool_calls` | 2500 | 36483 |
| 203 | 2026-05-02 12:06:27 | 61 | 67 | 72 | 75 | 4 | `manage_todo_list` | `tool_calls` | 3804 | 36806 |
| 204 | 2026-05-02 12:06:31 | 63 | 67 | 0 | 66 | 51 | `run_in_terminal` | `tool_calls` | 2722 | 36942 |
| 205 | 2026-05-02 12:07:42 | 65 | 67 | 0 | 96 | 36 | `get_terminal_output` | `tool_calls` | 2482 | 37484 |
| 206 | 2026-05-02 12:07:44 | 67 | 67 | 0 | 174 | 57 | `run_in_terminal` | `tool_calls` | 3113 | 37696 |
| 207 | 2026-05-02 12:07:52 | 69 | 67 | 99 | 135 | 101 | `run_in_terminal` | `tool_calls` | 5099 | 38553 |
| 208 | 2026-05-02 12:08:13 | 71 | 67 | 52 | 135 | 36 | `get_terminal_output` | `tool_calls` | 2697 | 39150 |
| 209 | 2026-05-02 12:08:16 | 73 | 67 | 60 | 68 | 36 | `get_terminal_output` | `tool_calls` | 2006 | 39439 |
| 210 | 2026-05-02 12:08:18 | 75 | 67 | 0 | 70 | 36 | `get_terminal_output` | `tool_calls` | 1879 | 39726 |
| 211 | 2026-05-02 12:08:20 | 77 | 67 | 0 | 69 | 36 | `get_terminal_output` | `tool_calls` | 1831 | 40014 |
| 212 | 2026-05-02 12:08:22 | 79 | 67 | 152 | 133 | 36 | `kill_terminal` | `tool_calls` | 2636 | 40344 |
| 213 | 2026-05-02 12:08:25 | 82 | 67 | 94 | 301 | 22 | `read_file` | `tool_calls` | 30424 | 40826 |
| 214 | 2026-05-02 12:08:56 | 84 | 67 | 153 | 612 | 58 | `run_in_terminal` | `tool_calls` | 5112 | 41261 |
| 215 | 2026-05-02 12:09:01 | 86 | 67 | 0 | 356 | 138 | `read_file` | `tool_calls` | 4727 | 41541 |
| 216 | 2026-05-02 12:09:06 | 88 | 67 | 82 | 146 | 65 | `run_in_terminal` | `tool_calls` | 3286 | 41802 |
| 217 | 2026-05-02 12:09:10 | 90 | 67 | 193 | 306 | 91 | `run_in_terminal` | `tool_calls` | 5283 | 42224 |
| 218 | 2026-05-02 12:09:31 | 92 | 67 | 55 | 61 | 81 | `run_in_terminal` | `tool_calls` | 4656 | 42949 |
| 219 | 2026-05-02 12:09:53 | 94 | 68 | 0 | 77 | 35 | `get_terminal_output` | `tool_calls` | 26757 | 43891 |
| 220 | 2026-05-02 12:10:20 | 96 | 68 | 62 | 134 | 22 | `read_file` | `tool_calls` | 2713 | 44284 |
| 221 | 2026-05-02 12:10:23 | 98 | 68 | 0 | 249 | 24 | `read_file` | `tool_calls` | 2827 | 44850 |
| 222 | 2026-05-02 12:10:26 | 100 | 68 | 113 | 334 | 24 | `read_file` | `tool_calls` | 3890 | 45697 |
| 223 | 2026-05-02 12:10:30 | 102 | 68 | 203 | 323 | 171 | `replace_string_in_file` | `tool_calls` | 6691 | 46537 |
| 224 | 2026-05-02 12:10:37 | 104 | 68 | 0 | 298 | 181 | `replace_string_in_file` | `tool_calls` | 5764 | 46808 |
| 225 | 2026-05-02 12:10:43 | 107 | 68 | 126 | 320 | 171 | `replace_string_in_file` | `tool_calls` | 11855 | 49032 |
| 226 | 2026-05-02 12:10:55 | 109 | 68 | 73 | 517 | 0 | - | `stop` | 2808 | 49131 |

## Conclusion

The after data shows a clear behavioral improvement:

- Failure mode reduced from 16/20 primary before rows to 0/42 after rows.
- Structured tool-call turns increased from 3/20 to 41/42.
- No after row contains the original `<tool_call>`-inside-reasoning leak.
- Copilot progressed through many shell, file, todo, terminal-output, and edit
  tool turns in one growing conversation.

This supports treating branch `fix/qwen-reasoning-tool-calls` as an effective
fix for the captured Copilot/Qwen3.6 failure in this local configuration.

Remaining caveats:

- This is live integration evidence from the local endpoint, not a minimized
  upstream llama.cpp reproducer.
- The branch test coverage is strong around the parser shape, but it still uses
  synthetic fixtures rather than the exact captured Qwen3.6 stream.
- If preparing an upstream PR, update or omit the stale `docs/plans/` wording
  before presenting the change.
