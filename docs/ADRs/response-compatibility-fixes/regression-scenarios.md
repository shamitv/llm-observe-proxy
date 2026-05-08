# Response Compatibility Regression Scenarios

This companion document gives enough sanitized request and response detail to
build regression tests for
[`ADR.md`](ADR.md)'s `qwen-tagged-tool-call-rewrite` implementation.

The source captures were large Copilot-style `/v1/chat/completions` requests
with dozens to hundreds of prior messages and tool definitions. They are not
committed in this ADR PR. This document intentionally preserves only the
behaviorally important shapes:

- OpenAI-compatible chat-completions requests with `stream: true`.
- Declared tools that include the intended function.
- Recent conversation state that made the next action likely.
- Upstream SSE output where a Qwen `<tool_call>` block was emitted inside
  reasoning instead of `delta.tool_calls`.
- The expected client-visible OpenAI-compatible shape after the fix.

Use these as reduced test inputs. They are not guaranteed to reproduce the exact
model generation by themselves because the original captures included much more
conversation context.

## Sanitization

The source captures were sanitized before reduction:

- Project paths and names became `/tmp/example-workspace/example-project`.
- Home-directory paths became `/home/user`.
- Host package-manager paths became `/home/system`.
- Shell prompts became `user@host`.
- Terminal and session IDs became `terminal-id` or `workspace-id`.
- Request headers and secrets were omitted.

## Source Scenario Summary

| Source row | Request shape | Original failure shape | Replay note |
| ---: | --- | --- | --- |
| `1142` | `stream: true`, 15 messages, tools included `read_file` and `run_in_terminal` | After `pip install -r requirements.txt` failed on `python-cors`, the model generated a `read_file` call for `backend/requirements.txt` inside `reasoning_content`; final `finish_reason` was `stop`. | Reproduced after sanitization. |
| `1230` | `stream: true`, 160 messages, tools included `run_in_terminal` | After server restart/reload confusion, the model generated a `run_in_terminal` call to check `/docs` inside `reasoning_content`; final `finish_reason` was `stop`. | Reproduced after sanitization. |
| `1256` | `stream: true`, 193 messages, tools included `read_file` | After conversation compaction and logger/settings errors, the intended next action was a `read_file` call for `backend/app/utils/logger.py`. | Did not reproduce after sanitization; replay produced normal structured `delta.tool_calls`, so treat it as a recovery/control scenario. |

When the failure reproduces, classify it as:

```text
HTTP 200
content-type: text/event-stream
stream ends with data: [DONE]
delta.content is empty
delta.tool_calls is absent
delta.reasoning_content or delta.reasoning contains a complete <tool_call> block
final finish_reason is "stop"
```

## Shared Tool Definitions

The reduced requests below keep only the tools required for the scenario. Real
Copilot traffic included many more tools.

```json
[
  {
    "type": "function",
    "function": {
      "name": "read_file",
      "parameters": {
        "type": "object",
        "properties": {
          "filePath": {
            "type": "string",
            "description": "The absolute path of the file to read."
          },
          "startLine": {
            "type": "number",
            "description": "The line number to start reading from, 1-based."
          },
          "endLine": {
            "type": "number",
            "description": "The inclusive line number to end reading at, 1-based."
          }
        },
        "required": ["filePath", "startLine", "endLine"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "run_in_terminal",
      "parameters": {
        "type": "object",
        "properties": {
          "command": {
            "type": "string",
            "description": "The command to run in the terminal."
          },
          "explanation": {
            "type": "string",
            "description": "A one-sentence description of what the command does."
          },
          "goal": {
            "type": "string",
            "description": "A short description of the goal or purpose of the command."
          },
          "mode": {
            "type": "string",
            "enum": ["sync", "async"],
            "description": "Execution mode for this command."
          },
          "timeout": {
            "type": "number",
            "description": "Optional hard cap in milliseconds."
          }
        },
        "required": ["command", "explanation", "goal", "mode"]
      }
    }
  }
]
```

## Scenario 1: Read `requirements.txt`

The preceding tool result showed a package install failure:

```text
ERROR: Could not find a version that satisfies the requirement python-cors>=0.0.1
ERROR: No matching distribution found for python-cors>=0.0.1
(venv) user@host:~/work/example-project/backend$
```

The model should call `read_file` to inspect
`/tmp/example-workspace/example-project/backend/requirements.txt`.

### Reduced Request

```json
{
  "model": "Qwen 3.6 35B",
  "stream": true,
  "messages": [
    {
      "role": "system",
      "content": "You are a coding assistant. Use tools when you need to inspect files or run commands."
    },
    {
      "role": "user",
      "content": "Build and run the example survey app in /tmp/example-workspace/example-project."
    },
    {
      "role": "assistant",
      "content": "Now let me install the backend dependencies:",
      "tool_calls": [
        {
          "id": "call_install",
          "type": "function",
          "function": {
            "name": "run_in_terminal",
            "arguments": "{\"command\":\"cd /tmp/example-workspace/example-project/backend && source venv/bin/activate && pip install -r requirements.txt\",\"explanation\":\"Install backend dependencies\",\"goal\":\"Install dependencies\",\"mode\":\"sync\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_install",
      "content": "ERROR: Could not find a version that satisfies the requirement python-cors>=0.0.1\nERROR: No matching distribution found for python-cors>=0.0.1\n(venv) user@host:~/work/example-project/backend$"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "read_file",
        "parameters": {
          "type": "object",
          "properties": {
            "filePath": { "type": "string" },
            "startLine": { "type": "number" },
            "endLine": { "type": "number" }
          },
          "required": ["filePath", "startLine", "endLine"]
        }
      }
    }
  ]
}
```

### Failing Upstream Reasoning

```text
The requirements.txt has an incorrect package name. Let me check and fix it:

<tool_call>
<function=read_file>
<parameter=endLine>
30
</parameter>
<parameter=filePath>
/tmp/example-workspace/example-project/backend/requirements.txt
</parameter>
<parameter=startLine>
1
</parameter>
</function>
</tool_call>
```

### Failing Upstream SSE Shape

```text
data: {"choices":[{"index":0,"delta":{"role":"assistant","content":null},"finish_reason":null}],"object":"chat.completion.chunk"}
data: {"choices":[{"index":0,"delta":{"reasoning_content":"The requirements.txt has an incorrect package name. Let me check and fix it:\n\n"},"finish_reason":null}],"object":"chat.completion.chunk"}
data: {"choices":[{"index":0,"delta":{"reasoning_content":"<tool_call>\n<function=read_file>\n<parameter=endLine>\n30\n</parameter>\n<parameter=filePath>\n/tmp/example-workspace/example-project/backend/requirements.txt\n</parameter>\n<parameter=startLine>\n1\n</parameter>\n</function>\n</tool_call>"},"finish_reason":null}],"object":"chat.completion.chunk"}
data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"object":"chat.completion.chunk"}
data: [DONE]
```

### Expected Transformed SSE Shape

The exact chunking may differ. The important reconstructed result is one
OpenAI-compatible `tool_calls` item and final `finish_reason: "tool_calls"`.

```text
data: {"choices":[{"index":0,"delta":{"role":"assistant","content":null},"finish_reason":null}],"object":"chat.completion.chunk"}
data: {"choices":[{"index":0,"delta":{"content":"The requirements.txt has an incorrect package name. Let me check and fix it:\n\n"},"finish_reason":null}],"object":"chat.completion.chunk"}
data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_qwen_rewrite_0","type":"function","function":{"name":"read_file","arguments":"{\"filePath\":\"/tmp/example-workspace/example-project/backend/requirements.txt\",\"startLine\":1,\"endLine\":30}"}}]},"finish_reason":null}],"object":"chat.completion.chunk"}
data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}],"object":"chat.completion.chunk"}
data: [DONE]
```

## Scenario 2: Check Backend Server

The preceding tool result showed Copilot trying to read terminal output after an
async terminal had already ended:

```text
Error: No active terminal execution found with ID terminal-id. The ID must be the exact value returned by run_in_terminal in async mode.
```

The model should call `run_in_terminal` to check whether the backend server is
responding.

### Reduced Request

```json
{
  "model": "Qwen 3.6 35B",
  "stream": true,
  "messages": [
    {
      "role": "system",
      "content": "You are a coding assistant. Use tools when you need to inspect files or run commands."
    },
    {
      "role": "user",
      "content": "Continue getting the example backend running."
    },
    {
      "role": "assistant",
      "content": "Good progress! The server is detecting changes but needs email-validator. Let me install it:",
      "tool_calls": [
        {
          "id": "call_install_email_validator",
          "type": "function",
          "function": {
            "name": "run_in_terminal",
            "arguments": "{\"command\":\"/tmp/example-workspace/example-project/backend/venv/bin/pip install email-validator\",\"explanation\":\"Install missing email validation dependency\",\"goal\":\"Install email-validator\",\"mode\":\"sync\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_install_email_validator",
      "content": "Successfully installed email-validator"
    },
    {
      "role": "assistant",
      "content": "",
      "tool_calls": [
        {
          "id": "call_get_terminal",
          "type": "function",
          "function": {
            "name": "run_in_terminal",
            "arguments": "{\"command\":\"echo checking terminal\",\"explanation\":\"Check terminal state\",\"goal\":\"Check server state\",\"mode\":\"sync\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_get_terminal",
      "content": "Error: No active terminal execution found with ID terminal-id. The ID must be the exact value returned by run_in_terminal in async mode."
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "run_in_terminal",
        "parameters": {
          "type": "object",
          "properties": {
            "command": { "type": "string" },
            "explanation": { "type": "string" },
            "goal": { "type": "string" },
            "mode": { "type": "string", "enum": ["sync", "async"] },
            "timeout": { "type": "number" }
          },
          "required": ["command", "explanation", "goal", "mode"]
        }
      }
    }
  ]
}
```

### Failing Upstream Reasoning

```text
The server should have auto-reloaded. Let me check if it's running:

<tool_call>
<function=run_in_terminal>
<parameter=command>
curl -s http://localhost:8000/docs | head -20
</parameter>
<parameter=explanation>
Check if backend server is running
</parameter>
<parameter=goal>
Verify backend server status
</parameter>
<parameter=mode>
sync
</parameter>
<parameter=timeout>
10000
</parameter>
</function>
</tool_call>
```

### Expected Transformed Tool Call

```json
{
  "type": "function",
  "function": {
    "name": "run_in_terminal",
    "arguments": "{\"command\":\"curl -s http://localhost:8000/docs | head -20\",\"explanation\":\"Check if backend server is running\",\"goal\":\"Verify backend server status\",\"mode\":\"sync\",\"timeout\":10000}"
  }
}
```

## Scenario 3: Recovery / Control Case

The third source capture had similar context pressure after conversation
compaction and backend errors:

```text
NameError: name 'BaseModel' is not defined
AttributeError: 'Settings' object has no attribute 'LOG_LEVEL'
```

The intended next action was:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "arguments": "{\"filePath\":\"/tmp/example-workspace/example-project/backend/app/utils/logger.py\",\"startLine\":125,\"endLine\":135}"
  }
}
```

After sanitization, replay produced normal structured `delta.tool_calls` and
final `finish_reason: "tool_calls"`. Keep this as a control case:

- Existing structured `delta.tool_calls` must pass through unchanged.
- The fix must not double-promote or modify already structured calls.
- The final `finish_reason` must remain `tool_calls`.

## Malformed And Incomplete Blocks

Malformed tagged tool-call blocks are not accepted as input for promotion. They
must pass through unchanged, with rewrite metadata recording a warning. This is
important because the proxy must not guess executable tool arguments.

Examples that should be rejected:

```text
<tool_call>
<function=read_file>
<parameter=filePath>
/tmp/example-workspace/example-project/backend/requirements.txt
</parameter>
```

```text
<tool_call>
<function=read_file>
<parameter=filePath>
/tmp/example-workspace/example-project/backend/requirements.txt
</parameter>
<parameter=filePath>
/tmp/example-workspace/example-project/backend/other.txt
</parameter>
</function>
</tool_call>
```

```text
<tool_call>
<function=unknown_tool>
<parameter=value>
test
</parameter>
</function>
</tool_call>
```

## Test Assertions

Focused tests should assert:

- The fix only runs when configured.
- Complete well-formed Qwen tags in `delta.reasoning_content` are promoted.
- Complete well-formed Qwen tags in `delta.reasoning` are promoted.
- Natural language before the tag is preserved as visible assistant content or
  otherwise handled by explicitly documented behavior.
- `finish_reason: "stop"` changes to `"tool_calls"` only when a tool call was
  promoted.
- Tool names must exist in the request `tools`.
- Parameter values must serialize to valid JSON according to the tool schema
  where possible.
- Malformed, incomplete, unknown-tool, or ambiguous duplicate-parameter blocks
  pass through unchanged and record warnings.
- Assistant content after a candidate tagged block must reject the rewrite and
  preserve the original upstream response.
- Raw upstream SSE remains available in capture records.
- Client-visible transformed SSE remains available in capture records.
