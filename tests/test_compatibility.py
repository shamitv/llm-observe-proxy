from __future__ import annotations

import json

from llm_observe_proxy.compatibility import (
    QWEN_TAGGED_TOOL_CALL_REWRITE,
    StreamingCompatibilityTransformer,
    normalize_fix_ids,
    parse_qwen_tagged_tool_call,
)

READ_FILE_REQUEST = {
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string"},
                        "startLine": {"type": "number"},
                        "endLine": {"type": "number"},
                    },
                    "required": ["filePath", "startLine", "endLine"],
                },
            },
        }
    ]
}

RUN_TERMINAL_REQUEST = {
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "run_in_terminal",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "explanation": {"type": "string"},
                        "goal": {"type": "string"},
                        "mode": {"type": "string", "enum": ["sync", "async"]},
                        "timeout": {"type": "number"},
                    },
                    "required": ["command", "explanation", "goal", "mode"],
                },
            },
        }
    ]
}


def test_qwen_parser_promotes_read_file_regression_example() -> None:
    result = parse_qwen_tagged_tool_call(
        """The requirements.txt has an incorrect package name. Let me check and fix it:

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
</tool_call>""",
        request_payload=READ_FILE_REQUEST,
    )

    assert result.status == "matched"
    assert result.parsed is not None
    assert result.parsed.function_name == "read_file"
    assert result.parsed.pre_text.startswith("The requirements.txt")
    assert json.loads(result.parsed.arguments_json) == {
        "endLine": 30,
        "filePath": "/tmp/example-workspace/example-project/backend/requirements.txt",
        "startLine": 1,
    }


def test_qwen_parser_promotes_run_terminal_regression_example() -> None:
    result = parse_qwen_tagged_tool_call(
        """The server should have auto-reloaded. Let me check if it's running:

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
</tool_call>""",
        request_payload=RUN_TERMINAL_REQUEST,
    )

    assert result.status == "matched"
    assert result.parsed is not None
    assert json.loads(result.parsed.arguments_json) == {
        "command": "curl -s http://localhost:8000/docs | head -20",
        "explanation": "Check if backend server is running",
        "goal": "Verify backend server status",
        "mode": "sync",
        "timeout": 10000,
    }


def test_qwen_parser_converts_parameter_values_by_schema_type() -> None:
    request = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "mixed",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer"},
                            "price": {"type": "number"},
                            "dryRun": {"type": "boolean"},
                            "filters": {"type": "object"},
                            "tags": {"type": "array"},
                            "note": {"type": "string"},
                        },
                        "required": ["count", "price", "dryRun", "filters", "tags", "note"],
                    },
                },
            }
        ]
    }

    result = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=mixed>
<parameter=count>7</parameter>
<parameter=price>3.5</parameter>
<parameter=dryRun>true</parameter>
<parameter=filters>{"kind":"demo"}</parameter>
<parameter=tags>["a","b"]</parameter>
<parameter=note>keep as text</parameter>
</function>
</tool_call>""",
        request_payload=request,
    )

    assert result.status == "matched"
    assert result.parsed is not None
    assert json.loads(result.parsed.arguments_json) == {
        "count": 7,
        "price": 3.5,
        "dryRun": True,
        "filters": {"kind": "demo"},
        "tags": ["a", "b"],
        "note": "keep as text",
    }


def test_qwen_parser_rejects_malformed_and_ambiguous_blocks() -> None:
    duplicate = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=read_file>
<parameter=filePath>/tmp/a</parameter>
<parameter=filePath>/tmp/b</parameter>
<parameter=startLine>1</parameter>
<parameter=endLine>2</parameter>
</function>
</tool_call>""",
        request_payload=READ_FILE_REQUEST,
    )
    unknown_tool = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=unknown_tool>
<parameter=value>test</parameter>
</function>
</tool_call>""",
        request_payload=READ_FILE_REQUEST,
    )
    missing_required = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=read_file>
<parameter=filePath>/tmp/a</parameter>
<parameter=startLine>1</parameter>
</function>
</tool_call>""",
        request_payload=READ_FILE_REQUEST,
    )
    unknown_param = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=read_file>
<parameter=filePath>/tmp/a</parameter>
<parameter=startLine>1</parameter>
<parameter=endLine>2</parameter>
<parameter=extra>ignored?</parameter>
</function>
</tool_call>""",
        request_payload=READ_FILE_REQUEST,
    )
    post_tool = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=read_file>
<parameter=filePath>/tmp/a</parameter>
<parameter=startLine>1</parameter>
<parameter=endLine>2</parameter>
</function>
</tool_call>
Then keep talking.""",
        request_payload=READ_FILE_REQUEST,
    )
    non_finite_number = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=read_file>
<parameter=filePath>/tmp/a</parameter>
<parameter=startLine>NaN</parameter>
<parameter=endLine>2</parameter>
</function>
</tool_call>""",
        request_payload=READ_FILE_REQUEST,
    )

    assert duplicate.status == "rejected"
    assert duplicate.warning and "duplicate parameter" in duplicate.warning
    assert unknown_tool.status == "rejected"
    assert unknown_tool.warning and "undeclared tool" in unknown_tool.warning
    assert missing_required.status == "rejected"
    assert missing_required.warning and "missing required parameter" in missing_required.warning
    assert unknown_param.status == "rejected"
    assert unknown_param.warning and "unknown parameter" in unknown_param.warning
    assert post_tool.status == "rejected"
    assert post_tool.warning and "content appeared after tagged block" in post_tool.warning
    assert non_finite_number.status == "rejected"
    assert non_finite_number.warning and "finite number" in non_finite_number.warning


def test_qwen_parser_leaves_ordinary_text_alone_and_marks_incomplete_pending() -> None:
    ordinary = parse_qwen_tagged_tool_call(
        "The assistant mentions tool_call as plain prose.",
        request_payload=READ_FILE_REQUEST,
        allow_pending=True,
    )
    incomplete = parse_qwen_tagged_tool_call(
        """<tool_call>
<function=read_file>
<parameter=filePath>/tmp/a</parameter>""",
        request_payload=READ_FILE_REQUEST,
        allow_pending=True,
    )

    assert ordinary.status == "none"
    assert incomplete.status == "pending"


def test_streaming_transformer_preserves_existing_structured_tool_calls() -> None:
    transformer = StreamingCompatibilityTransformer(
        endpoint="/v1/chat/completions",
        request_payload=READ_FILE_REQUEST,
        fix_ids=normalize_fix_ids([QWEN_TAGGED_TOOL_CALL_REWRITE]),
    )
    event = (
        b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
        b'"id":"call_existing","type":"function","function":{"name":"read_file",'
        b'"arguments":"{}"}}]},"finish_reason":null}]}\n\n'
    )

    output = b"".join(transformer.feed(event) + transformer.finish())

    assert output == event
    assert transformer.rewritten is False
    assert transformer.applied == []
    assert transformer.warnings == []
