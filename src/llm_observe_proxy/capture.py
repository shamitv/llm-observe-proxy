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


def decode_json_bytes(body: bytes | None) -> Any | None:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def extract_model(payload: Any | None) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("model"), str):
        return payload["model"]
    return None


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
    if value.get("type") in {"function_call", "function_call_output", "tool_call"}:
        return True
    if "tools" in value and isinstance(value["tools"], list) and value["tools"]:
        return True
    return False


def _looks_like_base64(value: str) -> bool:
    try:
        base64.b64decode(value, validate=True)
    except ValueError:
        return False
    return True
