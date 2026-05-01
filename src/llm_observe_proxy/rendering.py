from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

from markdown_it import MarkdownIt

from llm_observe_proxy.capture import decode_json_bytes, decode_sse_json_events, pretty_json

MARKDOWN = MarkdownIt("commonmark", {"html": False})


@dataclass(frozen=True)
class RenderedPayload:
    mode: str
    title: str
    text: str
    html: str | None = None
    tool_blocks: list[dict[str, Any]] | None = None


def render_payload(
    body: bytes | None,
    content_type: str | None,
    mode: str = "auto",
) -> RenderedPayload:
    body = body or b""
    requested_mode = mode if mode in {"auto", "json", "text", "markdown", "tool", "sse"} else "auto"
    json_payload = decode_json_bytes(body)
    text = _body_to_text(body)
    sse_events = decode_sse_json_events(body) if _is_sse(content_type, text) else []
    tool_blocks = collect_tool_blocks(json_payload if json_payload is not None else sse_events)

    resolved_mode = requested_mode
    if requested_mode == "auto":
        if tool_blocks:
            resolved_mode = "tool"
        elif sse_events:
            resolved_mode = "sse"
        elif json_payload is not None:
            resolved_mode = "json"
        elif _looks_like_markdown(text):
            resolved_mode = "markdown"
        else:
            resolved_mode = "text"

    if resolved_mode == "json":
        if json_payload is not None:
            return RenderedPayload("json", "Formatted JSON", pretty_json(json_payload))
        return RenderedPayload("text", "Text", text)

    if resolved_mode == "tool":
        if tool_blocks:
            return RenderedPayload(
                "tool",
                "Tool Calls and Responses",
                pretty_json(tool_blocks),
                tool_blocks=tool_blocks,
            )
        return RenderedPayload("text", "Text", extract_text(json_payload) or text)

    if resolved_mode == "markdown":
        markdown_text = extract_text(json_payload) or text
        return RenderedPayload(
            "markdown",
            "Markdown",
            markdown_text,
            html=MARKDOWN.render(markdown_text),
        )

    if resolved_mode == "sse":
        return RenderedPayload("sse", "Raw SSE Stream", text)

    return RenderedPayload("text", "Text", extract_text(json_payload) or text)


def collect_tool_blocks(payload: Any | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            tool_calls = value.get("tool_calls")
            if isinstance(tool_calls, list):
                for call in tool_calls:
                    blocks.append({"kind": "chat.tool_call", "payload": call})
            function_call = value.get("function_call")
            if function_call:
                blocks.append({"kind": "chat.function_call", "payload": function_call})
            value_type = value.get("type")
            if value_type in {"function_call", "function_call_output", "tool_call"}:
                blocks.append({"kind": value_type, "payload": value})
            if value.get("tool_call_id") and value.get("role") == "tool":
                blocks.append({"kind": "chat.tool_response", "payload": value})
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return blocks


def extract_text(payload: Any | None) -> str | None:
    if isinstance(payload, dict):
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        choices = payload.get("choices")
        if isinstance(choices, list):
            texts: list[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message") or choice.get("delta")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    texts.append(message["content"])
            if texts:
                return "\n\n".join(texts)
        output = payload.get("output")
        if isinstance(output, list):
            texts = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            texts.append(part["text"])
            if texts:
                return "\n\n".join(texts)
    return None


def escape_preview(value: str, limit: int = 160) -> str:
    value = " ".join(value.split())
    if len(value) > limit:
        value = f"{value[: limit - 1]}..."
    return html.escape(value)


def _is_sse(content_type: str | None, text: str) -> bool:
    return bool(content_type and "text/event-stream" in content_type.lower()) or text.startswith(
        "data:"
    )


def _looks_like_markdown(text: str) -> bool:
    signals = ("# ", "## ", "```", "- ", "* ", "| ", "> ", "[")
    return any(signal in text for signal in signals)


def _body_to_text(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")
