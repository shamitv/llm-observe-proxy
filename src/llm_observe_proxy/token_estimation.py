from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import tiktoken

FALLBACK_ENCODING = "o200k_base"


@dataclass(frozen=True)
class EstimatedInputTokens:
    tokens: int
    tokenizer: str
    model: str | None


def estimate_input_tokens(
    payload: Any | None,
    *,
    endpoint: str,
    model: str | None,
) -> EstimatedInputTokens | None:
    prompt_payload = _prompt_payload(payload, endpoint=endpoint)
    if prompt_payload is None:
        return None

    text = json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not text:
        return None

    encoding, tokenizer_name = _encoding_for_model(model)
    return EstimatedInputTokens(
        tokens=len(encoding.encode(text)),
        tokenizer=tokenizer_name,
        model=model,
    )


def _prompt_payload(payload: Any | None, *, endpoint: str) -> Any | None:
    if not isinstance(payload, dict):
        return None

    if endpoint.endswith("/chat/completions"):
        return _pick_prompt_fields(
            payload,
            (
                "messages",
                "tools",
                "functions",
                "function_call",
                "tool_choice",
                "response_format",
            ),
        )

    if endpoint.endswith("/responses"):
        return _pick_prompt_fields(
            payload,
            (
                "input",
                "instructions",
                "tools",
                "tool_choice",
                "response_format",
            ),
        )

    return _pick_prompt_fields(payload, ("prompt", "input", "messages", "tools"))


def _pick_prompt_fields(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any] | None:
    selected = {key: payload[key] for key in keys if key in payload}
    return selected or None


def _encoding_for_model(model: str | None):
    if model:
        try:
            return tiktoken.encoding_for_model(model), model
        except KeyError:
            pass
    return tiktoken.get_encoding(FALLBACK_ENCODING), FALLBACK_ENCODING
