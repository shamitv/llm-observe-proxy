from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
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
    cached_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None


STREAM_USAGE_MARKERS = (
    b'"usage"',
    b'"timings"',
    b'"input_tokens_details"',
    b'"input_tokens"',
    b'"prompt_tokens_details"',
    b'"prompt_tokens"',
    b'"prompt_n"',
    b'"prompt_eval_count"',
    b'"cached_tokens"',
    b'"cache_read_tokens"',
    b'"cache_write_tokens"',
    b'"cache_n"',
    b'"prompt_cache_hit_tokens"',
    b'"prompt_cache_miss_tokens"',
    b'"output_tokens"',
    b'"completion_tokens"',
    b'"predicted_n"',
    b'"eval_count"',
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
    return _find_token_usage(payload) or ExtractedTokenUsage()


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
                usage = extract_token_usage(json.loads(data))
                if _has_token_usage(usage):
                    return usage
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


TokenUsageParser = Callable[[dict[str, Any]], ExtractedTokenUsage | None]


def _find_token_usage(value: Any) -> ExtractedTokenUsage | None:
    if isinstance(value, dict):
        usage = value.get("usage")
        if isinstance(usage, dict):
            parsed_usage = _parse_openai_usage(usage)
            if _has_token_usage(parsed_usage):
                return parsed_usage

        parsed = _parse_token_usage_candidate(value)
        if parsed is not None:
            return parsed

        for child in value.values():
            found = _find_token_usage(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_token_usage(child)
            if found is not None:
                return found
    return None


def _body_may_contain_usage(body: bytes | None) -> bool:
    if not body:
        return False
    return any(marker in body for marker in STREAM_USAGE_MARKERS)


def _parse_token_usage_candidate(value: dict[str, Any]) -> ExtractedTokenUsage | None:
    for parser in TOKEN_USAGE_PARSERS:
        parsed = parser(value)
        if _has_token_usage(parsed):
            return parsed
    return None


def _parse_openai_usage(value: dict[str, Any]) -> ExtractedTokenUsage | None:
    if not _has_any_int(
        value,
        (
            "input_tokens",
            "prompt_tokens",
            "output_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        ),
    ):
        return None

    input_tokens = _first_int(value, "input_tokens", "prompt_tokens")
    if input_tokens is None:
        input_tokens = _sum_known(
            _first_int(value, "prompt_cache_hit_tokens"),
            _first_int(value, "prompt_cache_miss_tokens"),
        )

    return _build_token_usage(
        input_tokens=input_tokens,
        output_tokens=_first_int(value, "output_tokens", "completion_tokens"),
        total_tokens=_first_int(value, "total_tokens"),
        cached_input_tokens=_cached_input_tokens(value),
        cache_write_input_tokens=_cache_write_input_tokens(value),
    )


def _parse_llama_timings(value: dict[str, Any]) -> ExtractedTokenUsage | None:
    timings = value.get("timings")
    if not isinstance(timings, dict):
        if not _has_any_int(value, ("prompt_n", "cache_n", "predicted_n")):
            return None
        timings = value

    prompt_tokens = _first_int(timings, "prompt_n")
    cached_input_tokens = _first_int(timings, "cache_n")
    input_tokens = _sum_known(prompt_tokens, cached_input_tokens)
    output_tokens = _first_int(timings, "predicted_n")

    return _build_token_usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
    )


def _parse_ollama_usage(value: dict[str, Any]) -> ExtractedTokenUsage | None:
    if not _has_any_int(value, ("prompt_eval_count", "eval_count")):
        return None

    return _build_token_usage(
        input_tokens=_first_int(value, "prompt_eval_count"),
        output_tokens=_first_int(value, "eval_count"),
    )


TOKEN_USAGE_PARSERS: tuple[TokenUsageParser, ...] = (
    _parse_openai_usage,
    _parse_llama_timings,
    _parse_ollama_usage,
)


def _build_token_usage(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    cache_write_input_tokens: int | None = None,
) -> ExtractedTokenUsage:
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if (
        cached_input_tokens is not None
        and input_tokens is not None
        and cached_input_tokens > input_tokens
    ):
        cached_input_tokens = input_tokens
    return ExtractedTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_input_tokens=cache_write_input_tokens,
    )


def _has_any_int(value: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_int_or_none(value.get(key)) is not None for key in keys)


def _sum_known(*values: int | None) -> int | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known)


def _first_int(value: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        candidate = _int_or_none(value.get(key))
        if candidate is not None:
            return candidate
    return None


def _cached_input_tokens(usage: dict[str, Any]) -> int | None:
    for details_key in ("input_tokens_details", "prompt_tokens_details"):
        details = usage.get(details_key)
        if isinstance(details, dict):
            value = _first_int(details, "cached_tokens", "cache_read_tokens")
            if value is not None:
                return value
    return _first_int(usage, "cached_input_tokens", "prompt_cache_hit_tokens")


def _cache_write_input_tokens(usage: dict[str, Any]) -> int | None:
    for details_key in ("input_tokens_details", "prompt_tokens_details"):
        details = usage.get(details_key)
        if isinstance(details, dict):
            value = _first_int(details, "cache_write_tokens")
            if value is not None:
                return value
    return _first_int(usage, "cache_write_tokens")


def _has_token_usage(usage: ExtractedTokenUsage | None) -> bool:
    return usage is not None and any(
        value is not None
        for value in (
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.cache_write_input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )
    )


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
