# v0.4 Implementation TODO

This checklist tracks implementation work for v0.4 pricing catalog and cached-token
seed improvements. Keep each commit scoped and verify the relevant tests before moving
to the next task.

## Commit Plan

- [x] `docs: add v0.4 pricing catalog plan`
- [x] `feat: add tiered model pricing schema`
- [x] `feat: extract provider cache usage fields`
- [x] `feat: apply tiered cached pricing`
- [x] `feat: manage model price tiers in settings`
- [x] `feat: seed current cached and open-weight pricing`
- [x] `docs: document v0.4 pricing behavior`
- [ ] `chore: bump version to 0.4.0`

## Feature Tasks

### 1. Pricing Plan Docs

- [x] Create branch `feature/v0.4-pricing-catalog`.
- [x] Add `docs/plans/v0.4/README.md`.
- [x] Add this `docs/plans/v0.4/TODO.md`.
- [x] Do not change implementation code in this commit.
- [x] Commit as `docs: add v0.4 pricing catalog plan`.

### 2. Tiered Model Pricing Schema

- [x] Add a tier storage model linked to `model_prices`.
- [x] Include nullable min and max input-token bounds.
- [x] Include input, cached-input, and output USD-per-million rates.
- [x] Add source metadata fields needed for seeded data.
- [x] Add SQLite upgrade support for existing databases.
- [x] Preserve existing scalar `model_prices` rows and user edits.
- [x] Add schema and seed-preservation tests.
- [x] Run `pytest -q tests/test_rendering_and_cli.py`.
- [x] Commit as `feat: add tiered model pricing schema`.

### 3. Provider Cache Usage Extraction

- [x] Add redacted JSON fixtures from live OpenAI Chat Completions, OpenAI Responses,
  Hugging Face Router, and OpenRouter probes.
- [x] Add extraction for DeepSeek-style `prompt_cache_hit_tokens`.
- [x] Treat cache miss tokens as prompt/input tokens when the provider reports only
  hit/miss counters.
- [x] Add Qwen/router cache fields when verified from current response examples,
  including OpenRouter `prompt_tokens_details.cached_tokens`.
- [x] Preserve OpenRouter `cache_write_tokens` in fixtures or snapshots without
  treating it as cached-read input cost.
- [x] Ensure streaming extraction handles both OpenAI/HF `choices: []` usage events
  and OpenRouter final-delta events with attached `usage`.
- [x] Keep existing OpenAI cached token extraction behavior unchanged.
- [x] Add extraction tests for each supported provider shape.
- [x] Run `pytest -q tests/test_rendering_and_cli.py`.
- [x] Commit as `feat: extract provider cache usage fields`.

### 4. Tiered Cached Pricing

- [x] Select a model price tier from each request's input token count.
- [x] Fall back to scalar model price fields when a model has no tiers.
- [x] Apply cached-input rates from the matched tier when cached tokens are present.
- [x] Add tier details and source metadata to pricing snapshots.
- [x] Update run what-if calculations to estimate each request independently before
  summing totals.
- [x] Add tests for scalar fallback, tier selection, cached tier pricing, and run
  what-if tier math.
- [x] Run `pytest -q tests/test_rendering_and_cli.py tests/test_proxy_capture.py tests/test_admin_ui.py`.
- [x] Commit as `feat: apply tiered cached pricing`.

### 5. Settings UI For Tiers

- [x] Display tier rows on `/admin/settings`.
- [x] Add compact no-JS create and delete forms for tiers.
- [x] Validate tier bounds and decimal rates in admin actions.
- [x] Keep settings templates defensive for older or empty data.
- [x] Add admin UI tests for rendering, creation, validation, and deletion.
- [x] Run `pytest -q tests/test_admin_ui.py`.
- [x] Commit as `feat: manage model price tiers in settings`.

### 6. Current Cached And Open-Weight Pricing Seeds

- [x] Re-check first-party pricing sources before entering seed values.
- [x] Re-check live router model IDs against OpenRouter and Hugging Face Router before
  adding fallback seed aliases.
- [x] Add first-party providers and prices for verified Alibaba/Qwen, DeepSeek, Z.ai,
  Moonshot, and Mistral open-weight model families.
- [x] Add router fallback providers and prices only for models without first-party
  per-token API pricing.
- [x] Include aliases for common official API IDs and router IDs.
- [x] Include source URLs, checked dates, release dates, and concise notes.
- [x] Add seed tests for provider/model presence, cached rates, tiers, aliases, and
  non-overwriting behavior.
- [x] Document skipped candidates here with reason and source checked.
- [x] Run `pytest -q tests/test_rendering_and_cli.py`.
- [x] Commit as `feat: seed current cached and open-weight pricing`.

Skip notes:

- IBM Granite 4.0 and OpenAI gpt-oss have release sources but no first-party
  per-token API pricing; they are seeded under `openrouter` and/or
  `huggingface-router`.

### 7. Documentation

- [x] Update `README.md`.
- [x] Update `README.pypi.md`.
- [x] Update `docs/tests/README.md`.
- [x] Remove stale language saying cost estimates ignore cache.
- [x] Document tiered pricing, cache behavior, source policy, and router fallback.
- [x] Run `pytest -q tests/test_rendering_and_cli.py tests/test_admin_ui.py`.
- [x] Commit as `docs: document v0.4 pricing behavior`.

### 8. Version And Release Checks

- [ ] Bump `pyproject.toml` to `0.4.0`.
- [ ] Update README version strings.
- [ ] Run `ruff check src tests scripts`.
- [ ] Run `python -m compileall -q src tests scripts`.
- [ ] Run `pytest -q`.
- [ ] Run `python scripts/publish_pypi.py --dry-run`.
- [ ] Commit as `chore: bump version to 0.4.0`.

## Acceptance Checklist

- [x] Existing scalar pricing behavior remains compatible.
- [x] Tiered pricing applies per request, not from aggregate run totals.
- [x] Cached input tokens use cached rates only when configured.
- [x] Seeded prices are source-attributed and do not overwrite user edits.
- [x] Recent open-weight models are seeded from first-party prices where available.
- [x] Router fallback prices are stored under router providers.
- [x] Settings UI can manage tier rows without JavaScript.
- [x] Documentation reflects actual cache and tier behavior.
- [ ] Full test suite and release dry run pass.
