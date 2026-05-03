# llama.cpp Qwen Reasoning Tool-Call Post-PR Repro/Test/Fix Guide

Date: 2026-05-03

This guide is written for a llama.cpp developer who wants concrete fixtures for
the Qwen reasoning/tool-call failure observed through `llm-observe-proxy`.

The short diagnosis is:

- Qwen emits its native tagged tool-call syntax after a thinking close:
  `<tool_call><function=...><parameter=...>`.
- llama.cpp sometimes keeps that output in `reasoning_content` instead of
  converting it to OpenAI-compatible `tool_calls`.
- The HTTP/SSE stream is valid, so OpenAI-compatible clients see a successful
  but empty assistant turn: no content, no tool call, and `finish_reason:
  "stop"`.
- The latest live capture also showed Qwen omitting required `read_file`
  parameters. That is a model compliance problem, but the server bug is that
  tool-looking output after `</think>` is exposed as reasoning and finalized as
  a normal stop.

## 1. Reproduce The Issue

### Live OpenAI-Compatible Request

Run llama-server with a Qwen thinking/tool model and the Qwen XML/tagged
tool-call template. The local failure used:

- Model alias: `qwen_3.6_35B_4bit`
- Response model: `Qwen3.6-35B-A3B-MXFP4_MOE.gguf`
- Server fingerprint when failing: `b9014-e9eddd019`
- Endpoint: `POST /v1/chat/completions`
- Stream: `true`
- Reasoning format: auto/deepseek-style `reasoning_content`

Minimal request shape:

```http
POST /v1/chat/completions
Content-Type: application/json
```

```json
{
  "model": "qwen_3.6_35B_4bit",
  "stream": true,
  "stream_options": {
    "include_usage": true
  },
  "temperature": 0.1,
  "top_p": 1,
  "messages": [
    {
      "role": "system",
      "content": "You are a coding assistant. Use tools when you need to inspect files."
    },
    {
      "role": "user",
      "content": "Create an AGENTS.md for this project. Inspect the project first."
    },
    {
      "role": "assistant",
      "content": "",
      "tool_calls": [
        {
          "id": "call_file_search",
          "type": "function",
          "function": {
            "name": "file_search",
            "arguments": "{\"query\":\"**/AGENTS.md\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_file_search",
      "content": "No files found"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "file_search",
        "description": "Search for files by glob pattern.",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string"
            }
          },
          "required": [
            "query"
          ]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "read_file",
        "description": "Read a range of lines from a file.",
        "parameters": {
          "type": "object",
          "properties": {
            "filePath": {
              "type": "string"
            },
            "startLine": {
              "type": "number"
            },
            "endLine": {
              "type": "number"
            }
          },
          "required": [
            "filePath",
            "startLine",
            "endLine"
          ]
        }
      }
    }
  ]
}
```

This exact short request may not always trigger the model failure. The
deterministic reproductions below should be used for CI. The important live
shape is a multi-turn Copilot-style conversation where the model decides to
inspect files after a prior tool result.

### Actual Failing Output

The failure stream is valid SSE and valid JSON. The problem is semantic: the
assistant's intended tool call is emitted as `reasoning_content`.

Sanitized actual stream:

```text
data: {"choices":[{"index":0,"delta":{"role":"assistant","content":null},"finish_reason":null}],"model":"Qwen3.6-35B-A3B-MXFP4_MOE.gguf","object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{"reasoning_content":"</think>"},"finish_reason":null}],"model":"Qwen3.6-35B-A3B-MXFP4_MOE.gguf","object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{"reasoning_content":"\n\nLet me gather project context.\n\n<tool_call>"},"finish_reason":null}],"model":"Qwen3.6-35B-A3B-MXFP4_MOE.gguf","object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{"reasoning_content":"\n<function=read_file>\n<parameter=filePath>\n/home/example/project/backend/app/main.py\n</parameter>\n</function>\n</tool_call>"},"finish_reason":null}],"model":"Qwen3.6-35B-A3B-MXFP4_MOE.gguf","object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"model":"Qwen3.6-35B-A3B-MXFP4_MOE.gguf","object":"chat.completion.chunk"}

data: {"choices":[],"usage":{"completion_tokens":220,"prompt_tokens":36466,"total_tokens":36686},"object":"chat.completion.chunk"}

data: [DONE]
```

Client-visible result:

```json
{
  "role": "assistant",
  "content": null,
  "reasoning_content": "</think>\n\nLet me gather project context.\n\n<tool_call>...",
  "tool_calls": null,
  "finish_reason": "stop"
}
```

For an OpenAI-compatible tool client, this is an empty assistant turn. There is
no message to display and no tool to execute.

### Expected Output

For a valid generated tool call after the thinking block, llama.cpp should emit
OpenAI-compatible `delta.tool_calls` and finish with `tool_calls`.

Expected stream shape:

```text
data: {"choices":[{"index":0,"delta":{"role":"assistant","content":null},"finish_reason":null}],"object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{"content":"Let me gather project context."},"finish_reason":null}],"object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_abc","type":"function","function":{"name":"read_file"}}]},"finish_reason":null}],"object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"filePath\":\"/home/example/project/backend/app/main.py\",\"startLine\":1,\"endLine\":120}"}}]},"finish_reason":null}],"object":"chat.completion.chunk"}

data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}],"object":"chat.completion.chunk"}

data: [DONE]
```

Client-visible result:

```json
{
  "role": "assistant",
  "content": "Let me gather project context.",
  "tool_calls": [
    {
      "id": "call_abc",
      "type": "function",
      "function": {
        "name": "read_file",
        "arguments": "{\"filePath\":\"/home/example/project/backend/app/main.py\",\"startLine\":1,\"endLine\":120}"
      }
    }
  ],
  "finish_reason": "tool_calls"
}
```

If the model tries to omit required arguments, the lazy tool grammar should
constrain generation after the tool-call trigger so that the model cannot close
the tool call until required parameters are present. If a malformed generated
tool call still reaches post-processing, the server should not silently return
an empty `stop` turn.

## 2. Create Failing Tests

The most reliable tests are parser tests. They do not depend on sampling,
temperature, or a real model.

Add these fixtures to the `Qwen3.5-4B.jinja` block in `tests/test-chat.cpp`.
That template uses the same Qwen tagged tool-call family:

```text
<tool_call>
<function=name>
<parameter=arg>
value
</parameter>
</function>
</tool_call>
```

### Test Fixture Tool

Add a Copilot-shaped file reader near the other test tools:

```cpp
static common_chat_tool read_file_tool{
    /* .name = */ "read_file",
    /* .description = */ "Read a range of lines from a file",
    /* .parameters = */ R"({
        "type": "object",
        "properties": {
            "filePath": {
                "type": "string"
            },
            "startLine": {
                "type": "number"
            },
            "endLine": {
                "type": "number"
            }
        },
        "required": ["filePath", "startLine", "endLine"]
    })",
};
```

### Test 1: Empty Thinking Close Followed By Tool Call

This covers the common Qwen case where the prompt already opened thinking and
the model immediately closes it before calling a tool.

```cpp
tst.test(
       "</think>\n\n"
       "<tool_call>\n"
       "<function=read_file>\n"
       "<parameter=filePath>\n/home/example/project/backend/app/main.py\n</parameter>\n"
       "<parameter=startLine>\n1\n</parameter>\n"
       "<parameter=endLine>\n120\n</parameter>\n"
       "</function>\n"
       "</tool_call>")
    .enable_thinking(true)
    .reasoning_format(COMMON_REASONING_FORMAT_AUTO)
    .tools({ read_file_tool })
    .expect_tool_calls({
        {
            "read_file",
            R"({"filePath": "/home/example/project/backend/app/main.py", "startLine": 1, "endLine": 120})",
            {}
        },
    })
    .run();
```

Failure before the fix:

- The parser can treat `</think>...<tool_call>...` as reasoning/content instead
  of a tool call.
- In streaming mode this becomes `delta.reasoning_content` plus
  `finish_reason: "stop"`.

### Test 2: Transition Text Before Tool Call

Qwen templates explicitly allow natural-language reasoning before a tool call.
When that text appears after `</think>`, it should be assistant content, not
reasoning.

```cpp
tst.test(
       "</think>\n\n"
       "Let me inspect the project entry point.\n\n"
       "<tool_call>\n"
       "<function=read_file>\n"
       "<parameter=filePath>\n/home/example/project/backend/app/main.py\n</parameter>\n"
       "<parameter=startLine>\n1\n</parameter>\n"
       "<parameter=endLine>\n120\n</parameter>\n"
       "</function>\n"
       "</tool_call>")
    .enable_thinking(true)
    .reasoning_format(COMMON_REASONING_FORMAT_AUTO)
    .tools({ read_file_tool })
    .expect_content("Let me inspect the project entry point.")
    .expect_tool_calls({
        {
            "read_file",
            R"({"filePath": "/home/example/project/backend/app/main.py", "startLine": 1, "endLine": 120})",
            {}
        },
    })
    .run();
```

Failure before the fix:

- The transition text and `<tool_call>` can stay in `reasoning_content`.
- No OpenAI-compatible `tool_calls` are emitted.

### Test 3: Required Tool Mode Allows Post-Reasoning Transition Text

`peg_test_builder` currently does not expose a `tool_choice` setter in some
llama.cpp revisions. Add this helper if needed:

```cpp
peg_test_builder & tool_choice(common_chat_tool_choice choice) {
    tc_.params.tool_choice = choice;
    return *this;
}
```

Then add:

```cpp
tst.test(
       "</think>\n\n"
       "I need to read the file before answering.\n\n"
       "<tool_call>\n"
       "<function=read_file>\n"
       "<parameter=filePath>\n/home/example/project/backend/app/main.py\n</parameter>\n"
       "<parameter=startLine>\n1\n</parameter>\n"
       "<parameter=endLine>\n120\n</parameter>\n"
       "</function>\n"
       "</tool_call>")
    .enable_thinking(true)
    .reasoning_format(COMMON_REASONING_FORMAT_AUTO)
    .tool_choice(COMMON_CHAT_TOOL_CHOICE_REQUIRED)
    .tools({ read_file_tool })
    .expect_content("I need to read the file before answering.")
    .expect_tool_calls({
        {
            "read_file",
            R"({"filePath": "/home/example/project/backend/app/main.py", "startLine": 1, "endLine": 120})",
            {}
        },
    })
    .run();
```

Failure before the fix:

- `TAG_WITH_TAGGED` parsing uses `force_tools ? p.eps() : content_before_tools`.
- Under required tool mode, valid transition text before `<tool_call>` causes
  the parse to miss the tool call.

### Test 4: Tool-Looking Text Inside Active Thinking Is Not Executed

This safety test should already exist in some form. Keep or add it alongside
the positive fixtures.

```cpp
tst.test(
       "Thinking about a fake call: <tool_call>\n"
       "<function=read_file>\n"
       "<parameter=filePath>\n/home/example/project/backend/app/main.py\n</parameter>\n"
       "</function>\n"
       "</tool_call>\n"
       "</think>\n\n"
       "<tool_call>\n"
       "<function=read_file>\n"
       "<parameter=filePath>\n/home/example/project/backend/app/main.py\n</parameter>\n"
       "<parameter=startLine>\n1\n</parameter>\n"
       "<parameter=endLine>\n120\n</parameter>\n"
       "</function>\n"
       "</tool_call>")
    .enable_thinking(true)
    .reasoning_format(COMMON_REASONING_FORMAT_AUTO)
    .tools({ read_file_tool })
    .expect_reasoning(
       "Thinking about a fake call: <tool_call>\n"
       "<function=read_file>\n"
       "<parameter=filePath>\n/home/example/project/backend/app/main.py\n</parameter>\n"
       "</function>\n"
       "</tool_call>")
    .expect_tool_calls({
        {
            "read_file",
            R"({"filePath": "/home/example/project/backend/app/main.py", "startLine": 1, "endLine": 120})",
            {}
        },
    })
    .run();
```

This protects the important boundary: only tool calls after the reasoning close
are executable.

### Optional Server Streaming Assertion

For server-level tests, assert the reconstructed streamed response shape:

```python
body = server.make_any_request("POST", "/v1/chat/completions", data={
    "model": "qwen-test",
    "stream": True,
    "stream_options": {"include_usage": True},
    "messages": [
        {"role": "system", "content": "You are a coding assistant."},
        {"role": "user", "content": "Inspect the project."},
    ],
    "tools": [READ_FILE_TOOL],
})

choice = body["choices"][0]
message = choice["message"]

assert choice["finish_reason"] == "tool_calls"
assert message.get("tool_calls")
assert message["tool_calls"][0]["function"]["name"] == "read_file"
assert isinstance(message["tool_calls"][0]["function"]["arguments"], str)
assert "<tool_call>" not in (message.get("reasoning_content") or "")
```

This is less deterministic with a real model than the PEG tests, but it catches
the OpenAI compatibility contract that Copilot depends on.

## 3. Implement The Fix

The fix belongs in llama.cpp's chat parser/server path, not in clients and not
in a record-only proxy.

### A. Carry Thinking Tags Into Parser Params

`common_chat_params` already has:

```cpp
std::string thinking_start_tag;
std::string thinking_end_tag;
```

Add matching fields to `common_chat_parser_params`:

```cpp
std::string thinking_start_tag;
std::string thinking_end_tag;
```

Copy them in the constructor:

```cpp
common_chat_parser_params(const common_chat_params & chat_params) {
    format = chat_params.format;
    generation_prompt = chat_params.generation_prompt;
    thinking_start_tag = chat_params.thinking_start_tag;
    thinking_end_tag = chat_params.thinking_end_tag;
}
```

For the server path, pass them through the task JSON:

```cpp
llama_params["thinking_start_tag"] = chat_params.thinking_start_tag;
llama_params["thinking_end_tag"] = chat_params.thinking_end_tag;
```

Then read them into `params.chat_parser_params` in `server-task.cpp`.

### B. Normalize The Empty Thinking Close

In `common_chat_peg_parse()`, replace blind concatenation with reconstruction
that handles this shape:

```text
generation_prompt = "...<think>\n"
input             = "</think>\n\n<tool_call>..."
```

Pseudo-code:

```cpp
static std::string ltrim_copy(std::string s) {
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), [](unsigned char ch) {
        return !std::isspace(ch);
    }));
    return s;
}

static bool ends_with(const std::string & value, const std::string & suffix);
static bool starts_with(const std::string & value, const std::string & prefix);

std::string effective_input;
if (params.generation_prompt.empty()) {
    effective_input = input;
} else {
    effective_input = params.generation_prompt + input;

    const std::string stripped_end = ltrim_copy(params.thinking_end_tag);
    if (!params.thinking_start_tag.empty() &&
        !params.thinking_end_tag.empty() &&
        stripped_end != params.thinking_end_tag &&
        ends_with(params.generation_prompt, params.thinking_start_tag) &&
        starts_with(input, stripped_end) &&
        !starts_with(input, params.thinking_end_tag)) {
        const auto leading_ws_len =
            params.thinking_end_tag.size() - stripped_end.size();
        effective_input =
            params.generation_prompt +
            params.thinking_end_tag.substr(0, leading_ws_len) +
            input;
    }
}
```

The goal is to let the generated parser see the reasoning end marker exactly as
it was inferred from the chat template.

### C. Permit Post-Reasoning Content Before Tagged Tool Calls

In `analyze_tools::build_tool_parser_tag_tagged()`, change the final parser
composition from:

```cpp
return ctx.reasoning_parser +
       (force_tools ? p.eps() : p.optional(p.content(content_before_tools))) +
       tool_calls +
       p.end();
```

to:

```cpp
const bool allow_content_before_tools =
    !force_tools || ctx.extracting_reasoning;

return ctx.reasoning_parser +
       (allow_content_before_tools ? p.optional(p.content(content_before_tools)) : p.eps()) +
       tool_calls +
       p.end();
```

Make the same change for `TAG_WITH_JSON` if the same required-tool restriction
exists there.

This keeps required tool mode strict about producing a tool call, but stops it
from rejecting harmless post-reasoning transition text.

### D. Preserve The Safety Boundary

Do not parse tool-looking text before the reasoning end marker as a tool call.
The parser should only promote `<tool_call>` after reasoning has closed.

Expected behavior:

```text
<think>
Maybe call <tool_call>...</tool_call>
</think>

<tool_call>real call</tool_call>
```

Result:

- First block stays in `reasoning_content`.
- Second block becomes `tool_calls`.

## 4. Validate The Fix

### Local Parser Tests

Build and run the parser tests:

```bash
cmake --build build --target test-chat
./build/bin/test-chat --filter Qwen3.5
./build/bin/test-chat --filter Qwen3-Coder
```

Exact binary paths vary by build directory. If your tree places tests under a
different path, run the equivalent `test-chat` binary.

Expected validation results:

- Empty `</think>` plus valid `<tool_call>` parses into `tool_calls`.
- Transition text after `</think>` becomes `content`, not
  `reasoning_content`.
- Required tool mode still emits `tool_calls`.
- Fake tool calls inside active reasoning remain `reasoning_content`.

### Server Tests

Run the existing server tool-call suite:

```bash
python3 -m pytest tools/server/tests/unit/test_tool_call.py -q
```

Add or update a server-level streaming assertion if you have a deterministic
fixture for Qwen tagged output. The final stream reconstruction must satisfy:

```python
assert choice["finish_reason"] == "tool_calls"
assert message["tool_calls"]
assert message["content"] in (None, "", "Let me inspect the project entry point.")
assert "<tool_call>" not in (message.get("reasoning_content") or "")
```

### Live Copilot/Qwen Validation

Replay a Copilot-shaped request or run VS Code Copilot Agent mode through the
OpenAI-compatible llama-server endpoint.

Before fix signature:

| Metric | Bad value |
| --- | --- |
| `delta.content` | empty |
| `delta.tool_calls` | absent |
| `delta.reasoning_content` | contains `<tool_call>` |
| final `finish_reason` | `stop` |

After fix signature:

| Metric | Good value |
| --- | --- |
| `delta.tool_calls` | present for tool turns |
| final `finish_reason` | `tool_calls` |
| `delta.reasoning_content` | does not contain post-`</think>` tool tags |
| tool arguments | JSON strings |

### Caveat: Missing Required Arguments

The captured May 3 failure included this model output:

```text
<tool_call>
<function=read_file>
<parameter=filePath>
/home/example/project/backend/app/main.py
</parameter>
</function>
</tool_call>
```

That is schema-invalid for the Copilot `read_file` tool because it omits
`startLine` and `endLine`. This part is a model-output limitation.

The server-side fix still matters because an OpenAI-compatible server should
not return a clean empty `stop` turn when the model is clearly attempting a
tool call. With the reasoning boundary and lazy grammar applied correctly,
valid tagged calls are promoted, and invalid in-progress calls are much less
likely to be allowed to close before required parameters are generated.
