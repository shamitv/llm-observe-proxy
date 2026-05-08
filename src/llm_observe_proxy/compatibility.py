from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

QWEN_TAGGED_TOOL_CALL_REWRITE = "qwen-tagged-tool-call-rewrite"


@dataclass(frozen=True)
class CompatibilityFix:
    id: str
    name: str
    description: str
    risk_note: str
    endpoints: tuple[str, ...]
    supports_streaming: bool
    supports_non_streaming: bool
    default_enabled: bool = False


@dataclass(frozen=True)
class CompatibilityResult:
    body: bytes
    rewritten: bool = False
    applied: tuple[dict[str, object], ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedQwenToolCall:
    pre_text: str
    function_name: str
    arguments_json: str


@dataclass(frozen=True)
class QwenParseResult:
    status: str
    parsed: ParsedQwenToolCall | None = None
    warning: str | None = None


AVAILABLE_FIXES: tuple[CompatibilityFix, ...] = (
    CompatibilityFix(
        id=QWEN_TAGGED_TOOL_CALL_REWRITE,
        name="Qwen tagged tool-call rewrite",
        description=(
            "Promote complete Qwen <tool_call> blocks from reasoning into OpenAI "
            "tool_calls."
        ),
        risk_note=(
            "Opt-in only. The fix promotes model-generated text into client-visible "
            "tool calls after validating the declared tool schema."
        ),
        endpoints=("/v1/chat/completions",),
        supports_streaming=True,
        supports_non_streaming=True,
    ),
)

FIX_BY_ID = {fix.id: fix for fix in AVAILABLE_FIXES}
TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=([^>\s]+)>\s*(.*?)\s*</function>\s*</tool_call>",
    re.DOTALL,
)
PARAM_RE = re.compile(r"<parameter=([^>\s]+)>\s*(.*?)\s*</parameter>", re.DOTALL)


def compatibility_fix_rows() -> list[dict[str, object]]:
    return [
        {
            "id": fix.id,
            "name": fix.name,
            "description": fix.description,
            "risk_note": fix.risk_note,
            "endpoints": ", ".join(fix.endpoints),
            "supports_streaming": fix.supports_streaming,
            "supports_non_streaming": fix.supports_non_streaming,
            "default_enabled": fix.default_enabled,
        }
        for fix in AVAILABLE_FIXES
    ]


def normalize_fix_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates = [
            candidate.strip()
            for chunk in value.splitlines()
            for candidate in chunk.split(",")
            if candidate.strip()
        ]
    elif isinstance(value, (list, tuple)):
        candidates = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("Compatibility fix IDs must be strings.")
            stripped = item.strip()
            if stripped:
                candidates.append(stripped)
    else:
        raise ValueError("Compatibility fixes must be a list of strings.")

    normalized: list[str] = []
    seen: set[str] = set()
    for fix_id in candidates:
        if fix_id not in FIX_BY_ID:
            raise ValueError(f"Unknown compatibility fix: {fix_id}.")
        if fix_id in seen:
            raise ValueError(f"Duplicate compatibility fix: {fix_id}.")
        seen.add(fix_id)
        normalized.append(fix_id)
    return tuple(normalized)


def fix_ids_text(fix_ids: tuple[str, ...]) -> str:
    return "\n".join(fix_ids)


def apply_non_streaming_compatibility_fixes(
    *,
    endpoint: str,
    request_payload: Any | None,
    response_body: bytes,
    content_type: str | None,
    fix_ids: tuple[str, ...],
) -> CompatibilityResult:
    result = CompatibilityResult(body=response_body)
    working = response_body
    applied: list[dict[str, object]] = []
    warnings: list[str] = []
    rewritten = False
    for fix_id in fix_ids:
        if fix_id == QWEN_TAGGED_TOOL_CALL_REWRITE:
            partial = _rewrite_qwen_non_streaming(
                endpoint=endpoint,
                request_payload=request_payload,
                response_body=working,
                content_type=content_type,
            )
            working = partial.body
            applied.extend(partial.applied)
            warnings.extend(partial.warnings)
            rewritten = rewritten or partial.rewritten
    if working != response_body or applied or warnings or rewritten:
        result = CompatibilityResult(
            body=working,
            rewritten=rewritten or working != response_body,
            applied=tuple(applied),
            warnings=tuple(warnings),
        )
    return result


class StreamingCompatibilityTransformer:
    def __init__(
        self,
        *,
        endpoint: str,
        request_payload: Any | None,
        fix_ids: tuple[str, ...],
    ) -> None:
        self._enabled = (
            QWEN_TAGGED_TOOL_CALL_REWRITE in fix_ids
            and endpoint == "/v1/chat/completions"
            and bool(_declared_tools(request_payload))
        )
        self._rewriter = (
            QwenTaggedToolCallStreamRewriter(request_payload) if self._enabled else None
        )
        self._buffer = b""
        self.applied: list[dict[str, object]] = []
        self.warnings: list[str] = []
        self.rewritten = False

    def feed(self, chunk: bytes) -> list[bytes]:
        if not self._rewriter:
            return [chunk] if chunk else []

        self._buffer += chunk
        outputs: list[bytes] = []
        while True:
            event_end = self._buffer.find(b"\n\n")
            separator_len = 2
            if event_end < 0:
                event_end = self._buffer.find(b"\r\n\r\n")
                separator_len = 4
            if event_end < 0:
                break
            raw_event = self._buffer[: event_end + separator_len]
            self._buffer = self._buffer[event_end + separator_len :]
            outputs.extend(self._rewriter.feed_event(raw_event))
        self._sync_metadata()
        return outputs

    def finish(self) -> list[bytes]:
        if not self._rewriter:
            return [self._buffer] if self._buffer else []
        outputs = self._rewriter.finish()
        if self._buffer:
            outputs.append(self._buffer)
            self._buffer = b""
        self._sync_metadata()
        return outputs

    def _sync_metadata(self) -> None:
        if not self._rewriter:
            return
        self.applied = list(self._rewriter.applied)
        self.warnings = list(self._rewriter.warnings)
        self.rewritten = self._rewriter.rewritten


class QwenTaggedToolCallStreamRewriter:
    def __init__(self, request_payload: Any | None) -> None:
        self._request_payload = request_payload
        self._buffered_reasoning_events: list[bytes] = []
        self._reasoning_text = ""
        self._candidate_raw_events: list[bytes] = []
        self._candidate_outputs: list[bytes] = []
        self._post_candidate_events: list[bytes] = []
        self._candidate_applied: dict[str, object] | None = None
        self._candidate_pending = False
        self._saw_structured_tool_call = False
        self._rejected = False
        self._call_index = 0
        self.applied: list[dict[str, object]] = []
        self.warnings: list[str] = []
        self.rewritten = False

    def feed_event(self, raw_event: bytes) -> list[bytes]:
        event = _decode_sse_event(raw_event)
        if event is None:
            if _is_done_event(raw_event):
                if self._candidate_pending:
                    return self._reject_candidate(
                        "Qwen tool-call rewrite rejected: stream ended before finish reason.",
                        raw_event,
                    )
                return [*self._flush_buffered_reasoning(), raw_event]
            if self._candidate_pending:
                self._post_candidate_events.append(raw_event)
                return []
            if self._buffered_reasoning_events:
                self.warnings.append(
                    "Qwen tool-call rewrite rejected: non-JSON SSE event interrupted block."
                )
                self._rejected = True
                return [*self._flush_buffered_reasoning(), raw_event]
            return [raw_event]

        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            if self._candidate_pending:
                self._post_candidate_events.append(raw_event)
                return []
            if self._buffered_reasoning_events:
                self.warnings.append(
                    "Qwen tool-call rewrite rejected: usage/control event interrupted block."
                )
                self._rejected = True
                return [*self._flush_buffered_reasoning(), raw_event]
            return [raw_event]

        if self._candidate_pending:
            if _event_has_tool_calls(event):
                return self._reject_candidate(
                    "Qwen tool-call rewrite rejected: structured tool call appeared "
                    "after tagged block.",
                    raw_event,
                )
            if _event_has_non_empty_assistant_text(event):
                return self._reject_candidate(
                    "Qwen tool-call rewrite rejected: assistant content appeared "
                    "after tagged block.",
                    raw_event,
                )
            if _event_finish_reason(event) is not None:
                return self._accept_candidate(event, raw_event)
            self._post_candidate_events.append(raw_event)
            return []

        if _event_has_tool_calls(event):
            self._saw_structured_tool_call = True
            return [*self._flush_buffered_reasoning(), raw_event]

        reasoning = _event_reasoning_text(event)
        if (
            reasoning is not None
            and not self._saw_structured_tool_call
            and not self._rejected
        ):
            if not self._buffered_reasoning_events and "<tool_call>" not in reasoning:
                return [raw_event]
            self._buffered_reasoning_events.append(raw_event)
            self._reasoning_text += reasoning
            parse_result = parse_qwen_tagged_tool_call(
                self._reasoning_text,
                request_payload=self._request_payload,
                allow_pending=True,
            )
            if parse_result.status == "matched" and parse_result.parsed is not None:
                self._stage_tool_call(event, parse_result.parsed)
                return []
            if parse_result.status == "rejected":
                if parse_result.warning:
                    self.warnings.append(parse_result.warning)
                self._rejected = True
                return self._flush_buffered_reasoning()
            return []

        if _event_finish_reason(event) is not None:
            outputs = []
            if self._buffered_reasoning_events:
                self.warnings.append(
                    "Qwen tool-call rewrite rejected: incomplete tagged tool-call block."
                )
                self._rejected = True
                outputs.extend(self._flush_buffered_reasoning())
            outputs.append(raw_event)
            return outputs

        if self._buffered_reasoning_events:
            self.warnings.append(
                "Qwen tool-call rewrite rejected: non-reasoning delta interrupted block."
            )
            self._rejected = True
            return [*self._flush_buffered_reasoning(), raw_event]
        return [raw_event]

    def finish(self) -> list[bytes]:
        if self._candidate_pending:
            return self._reject_candidate(
                "Qwen tool-call rewrite rejected: stream ended before finish reason."
            )
        if self._buffered_reasoning_events:
            self.warnings.append(
                "Qwen tool-call rewrite rejected: incomplete tagged tool-call block."
            )
        return self._flush_buffered_reasoning()

    def _stage_tool_call(
        self,
        template_event: dict[str, Any],
        parsed: ParsedQwenToolCall,
    ) -> None:
        candidate_raw_events = self._buffered_reasoning_events
        self._buffered_reasoning_events = []
        self._reasoning_text = ""
        tool_call_id = f"call_qwen_rewrite_{self._call_index}"
        self._call_index += 1
        self._candidate_pending = True
        self._candidate_raw_events = candidate_raw_events
        self._candidate_applied = {
            "id": QWEN_TAGGED_TOOL_CALL_REWRITE,
            "action": "promoted_qwen_tagged_tool_call",
            "function": parsed.function_name,
        }

        outputs: list[bytes] = []
        if parsed.pre_text:
            outputs.append(
                _encode_sse_json_event(
                    _copy_event_with_delta(template_event, {"content": parsed.pre_text})
                )
            )
        outputs.append(
            _encode_sse_json_event(
                _copy_event_with_delta(
                    template_event,
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": parsed.function_name,
                                    "arguments": parsed.arguments_json,
                                },
                            }
                        ]
                    },
                )
            )
        )
        self._candidate_outputs = outputs

    def _accept_candidate(
        self,
        finish_event: dict[str, Any],
        raw_finish_event: bytes,
    ) -> list[bytes]:
        outputs = [*self._candidate_outputs, *self._post_candidate_events]
        if _event_finish_reason(finish_event) == "stop":
            outputs.append(
                _encode_sse_json_event(_copy_event_with_finish_reason(finish_event, "tool_calls"))
            )
        else:
            outputs.append(raw_finish_event)
        if self._candidate_applied is not None:
            self.applied.append(self._candidate_applied)
        self.rewritten = True
        self._clear_candidate()
        return outputs

    def _reject_candidate(self, warning: str, *tail_events: bytes) -> list[bytes]:
        self.warnings.append(warning)
        self._rejected = True
        outputs = [
            *self._candidate_raw_events,
            *self._post_candidate_events,
            *tail_events,
        ]
        self._clear_candidate()
        return outputs

    def _clear_candidate(self) -> None:
        self._candidate_raw_events = []
        self._candidate_outputs = []
        self._post_candidate_events = []
        self._candidate_applied = None
        self._candidate_pending = False

    def _flush_buffered_reasoning(self) -> list[bytes]:
        events = self._buffered_reasoning_events
        self._buffered_reasoning_events = []
        self._reasoning_text = ""
        return events


def parse_qwen_tagged_tool_call(
    text: str,
    *,
    request_payload: Any | None,
    allow_pending: bool = False,
) -> QwenParseResult:
    if "<tool_call>" not in text:
        return QwenParseResult("none")

    match = TOOL_CALL_RE.search(text)
    if match is None:
        if allow_pending and "</tool_call>" not in text:
            return QwenParseResult("pending")
        return QwenParseResult(
            "rejected",
            warning="Qwen tool-call rewrite rejected: malformed tagged block.",
        )

    prefix = text[: match.start()]
    suffix = text[match.end() :]
    if suffix.strip():
        return QwenParseResult(
            "rejected",
            warning="Qwen tool-call rewrite rejected: content appeared after tagged block.",
        )

    function_name = match.group(1).strip()
    if not function_name:
        return QwenParseResult(
            "rejected",
            warning="Qwen tool-call rewrite rejected: missing function name.",
        )

    tools = _declared_tools(request_payload)
    schema = tools.get(function_name)
    if schema is None:
        return QwenParseResult(
            "rejected",
            warning=f"Qwen tool-call rewrite rejected: undeclared tool '{function_name}'.",
        )

    params_result = _parse_parameters(match.group(2), schema)
    if isinstance(params_result, str):
        return QwenParseResult("rejected", warning=params_result)

    try:
        arguments_json = json.dumps(
            params_result,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except ValueError as exc:
        return QwenParseResult("rejected", warning=f"Qwen tool-call rewrite rejected: {exc}")
    return QwenParseResult(
        "matched",
        ParsedQwenToolCall(
            pre_text=prefix,
            function_name=function_name,
            arguments_json=arguments_json,
        ),
    )


def _rewrite_qwen_non_streaming(
    *,
    endpoint: str,
    request_payload: Any | None,
    response_body: bytes,
    content_type: str | None,
) -> CompatibilityResult:
    if endpoint != "/v1/chat/completions" or not _declared_tools(request_payload):
        return CompatibilityResult(body=response_body)
    if content_type and "json" not in content_type.lower():
        return CompatibilityResult(body=response_body)

    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return CompatibilityResult(body=response_body)
    if not isinstance(payload, dict):
        return CompatibilityResult(body=response_body)

    choices = payload.get("choices")
    if not isinstance(choices, list):
        return CompatibilityResult(body=response_body)

    rewritten = False
    applied: list[dict[str, object]] = []
    warnings: list[str] = []
    for choice_index, choice in enumerate(choices):
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        if message.get("tool_calls"):
            continue
        reasoning_field = _message_reasoning_field(message)
        if reasoning_field is None:
            continue
        parse_result = parse_qwen_tagged_tool_call(
            str(message[reasoning_field]),
            request_payload=request_payload,
        )
        if parse_result.status == "matched" and parse_result.parsed is not None:
            if _message_has_non_empty_content(message):
                warnings.append(
                    "Qwen tool-call rewrite rejected: assistant content appeared "
                    "alongside tagged block."
                )
                continue
            parsed = parse_result.parsed
            message["content"] = parsed.pre_text or None
            message.pop("reasoning", None)
            message.pop("reasoning_content", None)
            message["tool_calls"] = [
                {
                    "id": f"call_qwen_rewrite_{choice_index}",
                    "type": "function",
                    "function": {
                        "name": parsed.function_name,
                        "arguments": parsed.arguments_json,
                    },
                }
            ]
            choice["finish_reason"] = "tool_calls"
            rewritten = True
            applied.append(
                {
                    "id": QWEN_TAGGED_TOOL_CALL_REWRITE,
                    "action": "promoted_qwen_tagged_tool_call",
                    "function": parsed.function_name,
                }
            )
        elif parse_result.status == "rejected" and parse_result.warning:
            warnings.append(parse_result.warning)

    if not rewritten and not warnings:
        return CompatibilityResult(body=response_body)
    body = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if rewritten
        else response_body
    )
    return CompatibilityResult(
        body=body,
        rewritten=rewritten,
        applied=tuple(applied),
        warnings=tuple(warnings),
    )


def _parse_parameters(inner: str, schema: dict[str, Any]) -> dict[str, Any] | str:
    params: dict[str, Any] = {}
    consumed: list[tuple[int, int]] = []
    properties = schema.get("properties")
    for match in PARAM_RE.finditer(inner):
        name = match.group(1).strip()
        if name in params:
            return f"Qwen tool-call rewrite rejected: duplicate parameter '{name}'."
        if isinstance(properties, dict) and name not in properties:
            return f"Qwen tool-call rewrite rejected: unknown parameter '{name}'."
        try:
            params[name] = _convert_parameter(name, _clean_parameter_value(match.group(2)), schema)
        except (ValueError, json.JSONDecodeError) as exc:
            return f"Qwen tool-call rewrite rejected: {exc}"
        consumed.append(match.span())

    remaining = _remove_spans(inner, consumed)
    if remaining.strip():
        return "Qwen tool-call rewrite rejected: malformed parameter tags."

    required = schema.get("required")
    if isinstance(required, list):
        for name in required:
            if isinstance(name, str) and name not in params:
                return f"Qwen tool-call rewrite rejected: missing required parameter '{name}'."
    return params


def _convert_parameter(name: str, value: str, schema: dict[str, Any]) -> Any:
    properties = schema.get("properties")
    prop = properties.get(name) if isinstance(properties, dict) else None
    prop_type = prop.get("type") if isinstance(prop, dict) else None
    if prop_type == "integer":
        return int(value.strip())
    if prop_type == "number":
        stripped = value.strip()
        parsed_number = int(stripped) if re.fullmatch(r"[-+]?\d+", stripped) else float(stripped)
        if isinstance(parsed_number, float) and not math.isfinite(parsed_number):
            raise ValueError(f"Parameter '{name}' is not a finite number.")
        return parsed_number
    if prop_type == "boolean":
        stripped = value.strip().lower()
        if stripped in {"true", "1"}:
            return True
        if stripped in {"false", "0"}:
            return False
        raise ValueError(f"Parameter '{name}' is not a valid boolean.")
    if prop_type in {"object", "array"}:
        parsed = json.loads(value)
        if prop_type == "object" and not isinstance(parsed, dict):
            raise ValueError(f"Parameter '{name}' is not a JSON object.")
        if prop_type == "array" and not isinstance(parsed, list):
            raise ValueError(f"Parameter '{name}' is not a JSON array.")
        return parsed
    return value


def _declared_tools(request_payload: Any | None) -> dict[str, dict[str, Any]]:
    if not isinstance(request_payload, dict):
        return {}
    tools = request_payload.get("tools")
    if not isinstance(tools, list):
        return {}
    declared: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            parameters = function.get("parameters")
            declared[function["name"]] = parameters if isinstance(parameters, dict) else {}
            continue
        if tool.get("type") == "function" and isinstance(tool.get("name"), str):
            parameters = tool.get("parameters")
            declared[tool["name"]] = parameters if isinstance(parameters, dict) else {}
    return declared


def _message_reasoning_field(message: dict[str, Any]) -> str | None:
    for field in ("reasoning_content", "reasoning"):
        if isinstance(message.get(field), str):
            return field
    return None


def _message_has_non_empty_content(message: dict[str, Any]) -> bool:
    content = message.get("content")
    if content is None:
        return False
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return bool(content)
    return True


def _decode_sse_event(raw_event: bytes) -> dict[str, Any] | None:
    try:
        text = raw_event.decode("utf-8")
    except UnicodeDecodeError:
        return None
    data_lines = [
        line.removeprefix("data:").strip()
        for line in text.splitlines()
        if line.startswith("data:")
    ]
    if not data_lines:
        return None
    data = "\n".join(data_lines)
    if not data or data == "[DONE]":
        return None
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _is_done_event(raw_event: bytes) -> bool:
    return b"data: [DONE]" in raw_event


def _event_has_tool_calls(event: dict[str, Any]) -> bool:
    choices = event.get("choices")
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if isinstance(delta, dict) and delta.get("tool_calls"):
            return True
    return False


def _event_reasoning_text(event: dict[str, Any]) -> str | None:
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        return None
    for field in ("reasoning_content", "reasoning"):
        if isinstance(delta.get(field), str):
            return delta[field]
    return None


def _event_has_non_empty_assistant_text(event: dict[str, Any]) -> bool:
    choices = event.get("choices")
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            continue
        for field in ("content", "reasoning_content", "reasoning"):
            value = delta.get(field)
            if isinstance(value, str) and value.strip():
                return True
    return False


def _event_finish_reason(event: dict[str, Any]) -> str | None:
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    reason = choice.get("finish_reason")
    return reason if isinstance(reason, str) else None


def _copy_event_with_delta(event: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(event))
    choices = copied.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            choice["delta"] = delta
            choice["finish_reason"] = None
    return copied


def _copy_event_with_finish_reason(event: dict[str, Any], finish_reason: str) -> dict[str, Any]:
    copied = json.loads(json.dumps(event))
    choices = copied.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            choice["delta"] = {}
            choice["finish_reason"] = finish_reason
    return copied


def _encode_sse_json_event(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    cursor = 0
    remaining: list[str] = []
    for start, end in spans:
        remaining.append(text[cursor:start])
        cursor = end
    remaining.append(text[cursor:])
    return "".join(remaining)


def _clean_parameter_value(value: str) -> str:
    if value.startswith("\r\n"):
        value = value[2:]
    elif value.startswith("\n"):
        value = value[1:]
    if value.endswith("\r\n"):
        value = value[:-2]
    elif value.endswith("\n"):
        value = value[:-1]
    return value
