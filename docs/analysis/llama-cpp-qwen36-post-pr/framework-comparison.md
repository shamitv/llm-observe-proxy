# How Other Frameworks Handle Qwen Reasoning And Tool Calls

Date: 2026-05-03

This note compares the llama.cpp post-PR failure mode with the behavior exposed
by vLLM, SGLang, Hugging Face Transformers, and Hugging Face TGI.

The practical question is whether the Copilot failures should be treated as a
Qwen model limitation or as a serving-layer issue. The answer is mixed:

- Missing required tool arguments are a model compliance problem unless the
  server is using constrained decoding.
- A generated tool call after the thinking section that is returned as
  `reasoning_content` and then finalized as an empty successful assistant turn
  is a serving-layer translation problem.

## Relevant Failure Shape

The observed llama.cpp/Copilot stream looked structurally successful but
semantically empty:

```json
{
  "choices": [
    {
      "delta": {
        "reasoning_content": "</think><tool_call><function=read_file>..."
      },
      "finish_reason": null
    }
  ]
}
```

The final event then ended with:

```json
{
  "choices": [
    {
      "delta": {},
      "finish_reason": "stop"
    }
  ]
}
```

From an OpenAI-compatible client's point of view, that is neither a normal text
answer nor an OpenAI tool call. It is a successful response with no useful
assistant output.

The core boundary to preserve is:

```text
<think> model-private reasoning </think> visible assistant content or tool calls
```

Tool-looking text before the reasoning close should stay hidden from tool
parsers. Tool-looking text after the reasoning close should be visible to the
content/tool parser, not stranded in `reasoning_content`.

## vLLM

Primary docs:

- [vLLM reasoning outputs](https://docs.vllm.ai/en/stable/features/reasoning_outputs/)
- [vLLM tool calling](https://docs.vllm.ai/en/stable/features/tool_calling/)

vLLM makes the reasoning parser and tool parser explicit server configuration:

```bash
vllm serve <model> \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser <model-specific-parser>
```

The important design point is that vLLM separates reasoning from tool parsing.
Its reasoning docs state that tool calling parses functions from the `content`
field, not from the reasoning field. This means a tool call hidden inside active
reasoning is intentionally not parsed.

That rule is exactly the right safety boundary, but it also means the reasoning
parser has to close at the correct point. If Qwen emits:

```text
</think>
<tool_call><function=read_file>...</function></tool_call>
```

then the content/tool-call side must receive the `<tool_call>` text. If the
server keeps the whole suffix in reasoning, vLLM-style behavior would lose the
tool call too.

vLLM also distinguishes between forced and automatic tool calls:

- `tool_choice="required"` and named tool choices use the structured outputs
  backend, so arguments are constrained to valid JSON for the function schema.
- `tool_choice="auto"` lets the model generate freely, then a selected parser
  extracts tool calls from raw text. Arguments can still be malformed or fail the
  function schema.
- The `strict` field is accepted but does not currently constrain decoding in
  vLLM auto mode.

Implication for llama.cpp:

The empty Copilot turn is not explained by Qwen's missing `read_file`
parameters alone. vLLM's design would treat malformed arguments as a model or
schema-enforcement problem, but post-`</think>` tool text would still need to be
classified as content before the tool parser can extract anything.

## SGLang

Primary docs:

- [SGLang tool parser](https://docs.sglang.io/docs/advanced_features/tool_parser)
- [SGLang structured outputs for reasoning models](https://docs.sglang.io/docs/advanced_features/structured_outputs_for_reasoning_models)

SGLang also exposes the model-specific parser choice:

```bash
python3 -m sglang.launch_server \
  --model-path Qwen/Qwen2.5-7B-Instruct \
  --tool-call-parser qwen25
```

Its docs show three useful implementation patterns:

1. The server can parse generated text into `normal_text` plus function calls.
2. The same parser can be used offline through `FunctionCallParser`.
3. `tool_choice="required"` and named tool choice are implemented with EBNF
   grammar, using the Xgrammar backend by default.

For reasoning models, SGLang's structured-output docs explicitly describe
allowing free-form text inside `<think>...</think>` while enforcing grammar
constraints after the reasoning section. The `--reasoning-parser` option decides
the thinking end token, such as `</think>`.

Implication for llama.cpp:

SGLang treats reasoning-boundary detection as part of structured decoding and
parsing, not as an incidental string split. A llama.cpp fix should make the
thinking close token part of `common_chat_parser_params` or equivalent parser
state so grammar and tool parsing agree on when the visible assistant channel
begins.

## Hugging Face Transformers

Primary docs:

- [Transformers chat templates](https://huggingface.co/docs/transformers/v4.48.0/chat_templating)

Transformers is lower level than vLLM or SGLang. Its chat template API converts
a list of role/content messages into the exact prompt format expected by a
model-specific tokenizer:

```python
tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    tools=tools,
)
```

The docs also show that tool JSON schemas can be passed directly to
`apply_chat_template`. In other words, Transformers helps render the prompt and
template-specific tool schema, but the caller or serving layer still has to
interpret the generated text and turn it into OpenAI-compatible `tool_calls`.

Implication for llama.cpp:

Qwen native tags are model/template syntax. Returning those tags in the wrong
OpenAI-compatible field is not a Transformers-style "model limitation"; it is a
missing or incorrect translation step in the server.

## Hugging Face TGI

Primary docs:

- [TGI OpenAI Messages API](https://huggingface.co/docs/text-generation-inference/reference/api_reference)
- [TGI guidance, JSON, and tools](https://huggingface.co/docs/text-generation-inference/main/en/basic_tutorials/using_guidance)

TGI exposes an OpenAI-compatible `/v1/chat/completions` API. Its tools guide
describes tool/function schemas as JSON schema values passed to the Messages
API, with `tool_choice` modes such as `auto`, `none`, `required`, and a specific
tool.

TGI also uses grammar guidance through the outlines integration for JSON and
regex constraints, while tools are available on the chat completions endpoint.
The public docs do not go as deep as vLLM/SGLang on Qwen reasoning parser
boundaries, but they follow the same broad pattern: the serving layer is
responsible for translating model/template-specific output into the OpenAI
message shape.

## Cross-Framework Comparison

| Framework | Reasoning Handling | Tool Parser Location | Schema Constraint | Lesson For llama.cpp |
| --- | --- | --- | --- | --- |
| vLLM | Explicit `--reasoning-parser`; reasoning returned separately | Explicit `--tool-call-parser`; auto mode parses raw content | Required/named constrained; auto mode parser-only | Parse tools from content after reasoning closes; do not strand post-close tags in reasoning |
| SGLang | Explicit `--reasoning-parser`; grammar can be disabled inside thinking | `--tool-call-parser` and reusable offline parser | Required/named use EBNF/Xgrammar | Make thinking close tokens parser state, then apply content/tool grammar after the boundary |
| Transformers | Chat template renders model-specific prompt | Caller/server must interpret generated text | Template/schema prompt only unless caller adds constraints | Native Qwen tags need server translation into OpenAI `tool_calls` |
| TGI | OpenAI Messages API with model chat templates | Server exposes OpenAI tool fields | Grammar guidance and tool choice modes | OpenAI compatibility implies model syntax must be normalized before returning |

## Recommended llama.cpp Fix Direction

1. Add explicit thinking start/end tags to `common_chat_parser_params`, not only
   to prompt rendering.
2. In the Qwen tagged tool-call parser, recognize the model's generated
   `</think>` as closing the prompt-injected `<think>` block even when the
   generated text does not include a fresh `<think>` opener.
3. Parse tool calls only from the visible content suffix after reasoning closes.
4. Keep tool-like text inside an open reasoning block hidden from `tool_calls`.
5. For forced or required tool paths, use grammar/schema constraints where
   possible so required arguments like `startLine` and `endLine` are not left to
   best-effort model compliance.
6. If parsing fails after seeing post-reasoning tool syntax, expose an explicit
   parse error or raw visible content. Do not emit a clean empty assistant turn
   with `finish_reason: "stop"`.

## What This Means For The Copilot Failure

The failure is not "only Qwen cannot tool-call." The captured response contains
Qwen's native tool-call syntax, which means the model attempted to call a tool.

There are two separable issues:

- Model compliance issue: the latest `read_file` call omitted required line
  arguments.
- llama.cpp serving issue: post-thinking tool-call syntax was returned as
  reasoning and never translated to OpenAI-compatible `tool_calls`.

The second issue is squarely in llama.cpp's OpenAI compatibility layer.
