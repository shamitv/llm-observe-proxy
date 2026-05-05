from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

DATA_IMAGE_RE = re.compile(r"^data:(image/[A-Za-z0-9.+-]+);base64,(.+)$", re.DOTALL)
URL_IMAGE_RE = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedImage:
    kind: str
    mime_type: str | None
    source: str
    data_base64: str | None = None


@dataclass(frozen=True)
class ExtractedTokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


STREAM_USAGE_MARKERS = (
    b'"usage"',
    b'"input_tokens"',
    b'"prompt_tokens"',
    b'"output_tokens"',
    b'"completion_tokens"',
    b'"total_tokens"',
)


def decode_json_bytes(body: bytes | None) -> Any | None:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def decode_sse_json_events(body: bytes | None) -> list[Any]:
    if not body:
        return []
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return []

    events: list[Any] = []
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
            continue
        if line.strip():
            continue
        _append_sse_event(events, data_lines)
        data_lines = []
    _append_sse_event(events, data_lines)
    return events


def _append_sse_event(events: list[Any], data_lines: list[str]) -> None:
    if not data_lines:
        return
    data = "\n".join(data_lines)
    if not data or data == "[DONE]":
        return
    try:
        events.append(json.loads(data))
    except json.JSONDecodeError:
        events.append({"data": data})


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def extract_model(payload: Any | None) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("model"), str):
        return payload["model"]
    return None


def extract_token_usage(payload: Any | None) -> ExtractedTokenUsage:
    usage = _find_usage(payload)
    if usage is None:
        return ExtractedTokenUsage()

    input_tokens = _first_int(usage, "input_tokens", "prompt_tokens")
    output_tokens = _first_int(usage, "output_tokens", "completion_tokens")
    total_tokens = _first_int(usage, "total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return ExtractedTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def extract_stream_token_usage(body: bytes | None) -> ExtractedTokenUsage:
    if not body or not _body_may_contain_usage(body):
        return ExtractedTokenUsage()

    usage_index = max(body.rfind(marker) for marker in STREAM_USAGE_MARKERS)
    data_index = body.rfind(b"data:", 0, usage_index)
    if data_index >= 0:
        event_end = body.find(b"\n\n", usage_index)
        if event_end < 0:
            event_end = len(body)
        event = body[data_index:event_end]
        try:
            text = event.decode("utf-8")
            data = "\n".join(
                line.removeprefix("data:").strip()
                for line in text.splitlines()
                if line.startswith("data:")
            )
            if data and data != "[DONE]":
                return extract_token_usage(json.loads(data))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    return extract_token_usage(decode_sse_json_events(body))


def extract_images(payload: Any | None) -> list[ExtractedImage]:
    images: list[ExtractedImage] = []

    def add_from_string(value: str) -> None:
        data_match = DATA_IMAGE_RE.match(value)
        if data_match:
            mime_type, data = data_match.groups()
            if _looks_like_base64(data):
                images.append(
                    ExtractedImage(
                        kind="data_url",
                        mime_type=mime_type,
                        source=value,
                        data_base64=data,
                    )
                )
            return
        if URL_IMAGE_RE.match(value):
            images.append(ExtractedImage(kind="url", mime_type=None, source=value))

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("image_url"), dict):
                url = value["image_url"].get("url")
                if isinstance(url, str):
                    add_from_string(url)
            if isinstance(value.get("image_url"), str):
                add_from_string(value["image_url"])
            if isinstance(value.get("type"), str) and value["type"] in {
                "image_url",
                "input_image",
            }:
                for key in ("url", "image_url"):
                    if isinstance(value.get(key), str):
                        add_from_string(value[key])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    deduped: list[ExtractedImage] = []
    seen: set[str] = set()
    for image in images:
        key = image.source
        if key not in seen:
            deduped.append(image)
            seen.add(key)
    return deduped


def has_tool_payload(payload: Any | None) -> bool:
    found = False

    def walk(value: Any) -> None:
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            if _dict_has_tool_signal(value):
                found = True
                return
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return found


def _dict_has_tool_signal(value: dict[str, Any]) -> bool:
    if value.get("tool_calls") or value.get("function_call") or value.get("tool_call_id"):
        return True
    value_type = value.get("type")
    if (
        isinstance(value_type, str)
        and value_type in {"function_call", "function_call_output", "tool_call"}
    ):
        return True
    if "tools" in value and isinstance(value["tools"], list) and value["tools"]:
        return True
    return False


def _find_usage(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if _looks_like_usage(value):
            return value
        usage = value.get("usage")
        if isinstance(usage, dict) and _looks_like_usage(usage):
            return usage
        for child in value.values():
            found = _find_usage(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_usage(child)
            if found is not None:
                return found
    return None


def _body_may_contain_usage(body: bytes | None) -> bool:
    if not body:
        return False
    return any(marker in body for marker in STREAM_USAGE_MARKERS)


def _looks_like_usage(value: dict[str, Any]) -> bool:
    return any(
        _int_or_none(value.get(key)) is not None
        for key in (
            "input_tokens",
            "prompt_tokens",
            "output_tokens",
            "completion_tokens",
            "total_tokens",
        )
    )


def _first_int(value: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        candidate = _int_or_none(value.get(key))
        if candidate is not None:
            return candidate
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _looks_like_base64(value: str) -> bool:
    try:
        base64.b64decode(value, validate=True)
    except ValueError:
        return False
    return True
