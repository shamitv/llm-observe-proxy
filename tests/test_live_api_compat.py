from __future__ import annotations

import os

import httpx
import pytest

from llm_observe_proxy.capture import extract_stream_token_usage, extract_token_usage

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_API_TESTS") != "1",
    reason="live API compatibility probes are opt-in",
)


def test_live_openai_chat_usage_shape() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY is not set")

    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-4.1-nano",
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 8,
            "temperature": 0,
        },
        timeout=60.0,
    )

    assert response.status_code == 200
    usage = extract_token_usage(response.json())
    assert usage.input_tokens is not None
    assert usage.cached_input_tokens is not None
    assert usage.output_tokens is not None


def test_live_huggingface_router_stream_usage_shape() -> None:
    api_key = os.getenv("HF_TOKEN")
    if not api_key:
        pytest.skip("HF_TOKEN is not set")

    with httpx.Client(timeout=60.0) as client:
        with client.stream(
            "POST",
            "https://router.huggingface.co/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "meta-llama/Llama-3.1-8B-Instruct",
                "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                "max_tokens": 8,
                "temperature": 0,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        ) as response:
            body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    usage = extract_stream_token_usage(body)
    assert usage.input_tokens is not None
    assert usage.cached_input_tokens is not None
    assert usage.output_tokens is not None


def test_live_openrouter_usage_shape() -> None:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY is not set")

    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:8080",
            "X-Title": "llm-observe-proxy live compatibility probe",
        },
        json={
            "model": "meta-llama/llama-3.1-8b-instruct",
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 8,
            "temperature": 0,
            "usage": {"include": True},
        },
        timeout=60.0,
    )

    assert response.status_code == 200
    usage = extract_token_usage(response.json())
    assert usage.input_tokens is not None
    assert usage.cached_input_tokens is not None
    assert usage.output_tokens is not None
