# v0.4 Pricing Catalog And Cached-Token Seed Plan

This plan tracks the pricing work intended for the `0.4.0` release branch.

## Release Goals

- Fill the current pricing gap for cached input tokens in seeded model prices.
- Add tiered pricing support for providers whose rates depend on per-request input
  token counts.
- Seed popular recent open-weight model families released since 2025-05-20.
- Prefer first-party pricing when available, and use router pricing only as a fallback
  when the model owner does not publish suitable per-token API pricing.
- Keep historical request pricing snapshots immutable unless a request is newly
  captured or explicitly recalculated by a future feature.

## Current State

The proxy already records token usage, including cached input tokens for OpenAI-style
usage payloads, and cost estimation already uses `cached_input_usd_per_million` when a
model price has that value configured.

The remaining gaps are:

- Seeded common model prices do not include cached-input rates.
- The `model_prices` table has only one input rate, one optional cached-input rate, and
  one output rate per model.
- Several current providers publish tiered pricing based on request input size, which
  cannot be represented accurately by the current scalar model price shape.
- Some provider cache-hit fields, such as DeepSeek prompt cache hit counts, are not yet
  extracted as cached input tokens.
- Documentation still contains older wording that says cache is ignored.

## Source Policy

Pricing sources must be checked during implementation, because model availability and
pricing change over time.

Use this precedence:

1. First-party API pricing from the model provider.
2. OpenRouter pricing when first-party per-token API pricing is unavailable.
3. Hugging Face Router or Inference Providers pricing when OpenRouter is unavailable or
   not a suitable source.

Seed router fallback rows under router providers such as `openrouter` or
`huggingface-router`, not under the model creator provider.

Reference sources to verify during implementation:

- Alibaba Cloud Model Studio model docs: <https://www.alibabacloud.com/help/en/model-studio/user-guide/model/>
- Alibaba Cloud Model Studio pricing: <https://www.alibabacloud.com/help/doc-detail/2987148.html>
- DeepSeek pricing: <https://api-docs.deepseek.com/quick_start/pricing/>
- DeepSeek cache usage: <https://api-docs.deepseek.com/guides/kv_cache>
- Z.ai GLM docs: <https://docs.z.ai/guides/llm/glm-4.5>
- Moonshot pricing: <https://platform.moonshot.ai/docs/pricing/chat>
- OpenRouter pricing policy: <https://openrouter.ai/pricing>
- Hugging Face Inference Providers pricing: <https://huggingface.co/docs/api-inference/en/pricing>
- IBM Granite 4.0 release: <https://www.ibm.com/new/announcements/ibm-granite-4-0-hyper-efficient-high-performance-hybrid-models>
- OpenAI gpt-oss release: <https://openai.com/index/introducing-gpt-oss>

## Pricing Model

Keep existing scalar `model_prices` fields for simple prices and backward
compatibility. Add tier support for providers with request-size-specific rates.

Planned tier fields:

```text
model_price_tiers
- model_price_id integer
- min_input_tokens integer nullable
- max_input_tokens integer nullable
- input_usd_per_million numeric
- cached_input_usd_per_million numeric nullable
- output_usd_per_million numeric
- label string nullable
- notes text nullable
```

Tier matching should be based on per-request input token count. This is important for
providers such as Qwen, where prices vary by context length. Run-level what-if totals
must estimate each request independently, then sum request-level costs.

If a price has no tiers, existing scalar pricing behavior remains unchanged.

## Cache Accounting

For providers with both implicit and explicit cache prices, v0.4 uses the default
automatic or implicit cache-hit rate for cost math unless usage data clearly identifies
explicit-cache tokens.

Extraction should continue supporting OpenAI-style cached usage fields and add provider
fields where response usage exposes cache hits. For example:

- `prompt_tokens_details.cached_tokens`
- `input_tokens_details.cached_tokens`
- `input_tokens_details.cache_read_tokens`
- `cached_input_tokens`
- `prompt_cache_hit_tokens`
- `prompt_cache_miss_tokens`

Cost calculation should clamp cached tokens to known input tokens, preserve uncached
token counts in snapshots, and include whether the scalar price or tier price supplied
the cached-input rate.

## Observed API Response Shapes

Live compatibility probes were run on 2026-05-20 with local `.env` keys for Hugging
Face Router, OpenRouter, and OpenAI. Secrets were not stored. Convert these observations
into checked-in JSON fixtures during implementation.

OpenAI Chat Completions:

- Non-streaming responses include top-level `choices`, `created`, `id`, `model`,
  `object`, `service_tier`, `system_fingerprint`, and `usage`.
- `usage` has `prompt_tokens`, `completion_tokens`, `total_tokens`,
  `prompt_tokens_details.cached_tokens`, `prompt_tokens_details.audio_tokens`, and
  `completion_tokens_details.reasoning_tokens`.
- Streaming responses use `text/event-stream`; intermediate events have `usage: null`,
  and the final usage event has `choices: []` plus the same `usage` shape.
- Current streaming events may include an `obfuscation` field that should be ignored by
  token extraction.

OpenAI Responses API:

- Non-streaming responses place usage at top-level `usage`.
- `usage` has `input_tokens`, `output_tokens`, `total_tokens`,
  `input_tokens_details.cached_tokens`, and
  `output_tokens_details.reasoning_tokens`.
- Output content is under an `output` array with message items, not under
  `choices[].message`.
- The observed endpoint rejected `max_output_tokens` below 16, so compatibility probes
  should use `max_output_tokens >= 16`.

Hugging Face Router:

- OpenAI-compatible base URL is `https://router.huggingface.co/v1`.
- Chat completion responses expose OpenAI-style `prompt_tokens`,
  `completion_tokens`, `total_tokens`, and
  `prompt_tokens_details.cached_tokens`.
- Streaming responses include SSE `data:` events, `[DONE]`, and a final usage event
  that current stream usage extraction can read.

OpenRouter:

- OpenAI-compatible base URL is `https://openrouter.ai/api/v1`.
- Non-streaming responses include top-level `provider`; choices include
  `native_finish_reason`; messages may include `reasoning`.
- Usage is returned when requested with `usage: {"include": true}`.
- `usage` has OpenAI-style token totals plus router-specific fields:
  `cost`, `is_byok`, `cost_details`, `prompt_tokens_details.cache_write_tokens`,
  `prompt_tokens_details.audio_tokens`, and `prompt_tokens_details.video_tokens`.
- Streaming responses may attach `usage` to the final delta event rather than emitting
  a separate `choices: []` usage-only event.
- `prompt_tokens_details.cached_tokens` should count as cached input tokens.
  `cache_write_tokens` should be preserved in fixtures/snapshots for future work, but
  should not be counted as cached-read tokens unless a later pricing model adds a
  separate cache-write cost dimension.

## Candidate Seed Families

Implementation should verify every candidate before seeding it. If a candidate source no
longer confirms open-weight release date, active API availability, and per-token pricing,
skip it and document the skip in `TODO.md`.

Likely first-party seeded providers:

- Alibaba Cloud / Qwen: Qwen3 Coder and related Qwen3 models with published tiered and
  cached-input pricing.
- DeepSeek: current official open models with cache-hit pricing.
- Z.ai: GLM-4.5 and GLM-4.5-Air where official API pricing is available.
- Moonshot AI: Kimi K2 and Kimi K2.5 where official API pricing is available.
- Mistral: recent open-weight general or coding models where official API pricing is
  available.

Likely router fallback rows:

- OpenAI gpt-oss models when no direct first-party API price exists for the open-weight
  model.
- IBM Granite 4.0 models if IBM does not provide a suitable per-token hosted API price.
- MiniMax M2.1 or similar recent open-weight models when the model owner lacks suitable
  first-party API pricing.

## User Experience

The admin settings page should remain compact and server-rendered:

- Existing scalar model price rows continue to render as they do now.
- Prices with tiers show tier rows below or near the parent model price.
- Add small create/delete tier forms without requiring JavaScript.
- Source metadata should be visible enough for users to understand where seed values
  came from, without making the table noisy.

## Compatibility

- Do not overwrite user-edited model prices or tiers when seeding defaults.
- Existing databases must upgrade in place with nullable tier tables and metadata
  columns.
- Existing request records and pricing snapshots remain readable.
- Existing scalar prices still work when no tiers are configured.
- The proxy remains record-only and continues forwarding every `/v1/*` request upstream.

## Acceptance Criteria

- Seeded model prices include cached-input pricing where reliable current source data is
  available.
- Tiered provider pricing can be represented and used in capture-time cost snapshots.
- Run what-if costs apply tiers per request and sum the results.
- Provider cache-hit usage fields are extracted when available.
- Settings UI can display and manage tier rows.
- README and PyPI docs no longer claim cache is ignored.
- Full tests and release dry run pass before the version bump.
