# v0.4 Implementation TODO

This checklist tracks implementation work for v0.4 pricing catalog and cached-token
seed improvements. Keep each commit scoped and verify the relevant tests before moving
to the next task.

## Commit Plan

- [ ] `docs: add v0.4 pricing catalog plan`
- [ ] `feat: add tiered model pricing schema`
- [ ] `feat: extract provider cache usage fields`
- [ ] `feat: apply tiered cached pricing`
- [ ] `feat: manage model price tiers in settings`
- [ ] `feat: seed current cached and open-weight pricing`
- [ ] `docs: document v0.4 pricing behavior`
- [ ] `chore: bump version to 0.4.0`

## Feature Tasks

### 1. Pricing Plan Docs

- [ ] Create branch `feature/v0.4-pricing-catalog`.
- [ ] Add `docs/plans/v0.4/README.md`.
- [ ] Add this `docs/plans/v0.4/TODO.md`.
- [ ] Do not change implementation code in this commit.
- [ ] Commit as `docs: add v0.4 pricing catalog plan`.

### 2. Tiered Model Pricing Schema

- [ ] Add a tier storage model linked to `model_prices`.
- [ ] Include nullable min and max input-token bounds.
- [ ] Include input, cached-input, and output USD-per-million rates.
- [ ] Add source metadata fields needed for seeded data.
- [ ] Add SQLite upgrade support for existing databases.
- [ ] Preserve existing scalar `model_prices` rows and user edits.
- [ ] Add schema and seed-preservation tests.
- [ ] Run `pytest -q tests/test_rendering_and_cli.py`.
- [ ] Commit as `feat: add tiered model pricing schema`.

### 3. Provider Cache Usage Extraction

- [ ] Add extraction for DeepSeek-style `prompt_cache_hit_tokens`.
- [ ] Treat cache miss tokens as prompt/input tokens when the provider reports only
  hit/miss counters.
- [ ] Add Qwen/router cache fields when verified from current response examples.
- [ ] Keep existing OpenAI cached token extraction behavior unchanged.
- [ ] Add extraction tests for each supported provider shape.
- [ ] Run `pytest -q tests/test_rendering_and_cli.py`.
- [ ] Commit as `feat: extract provider cache usage fields`.

### 4. Tiered Cached Pricing

- [ ] Select a model price tier from each request's input token count.
- [ ] Fall back to scalar model price fields when a model has no tiers.
- [ ] Apply cached-input rates from the matched tier when cached tokens are present.
- [ ] Add tier details and source metadata to pricing snapshots.
- [ ] Update run what-if calculations to estimate each request independently before
  summing totals.
- [ ] Add tests for scalar fallback, tier selection, cached tier pricing, and run
  what-if tier math.
- [ ] Run `pytest -q tests/test_rendering_and_cli.py tests/test_proxy_capture.py tests/test_admin_ui.py`.
- [ ] Commit as `feat: apply tiered cached pricing`.

### 5. Settings UI For Tiers

- [ ] Display tier rows on `/admin/settings`.
- [ ] Add compact no-JS create and delete forms for tiers.
- [ ] Validate tier bounds and decimal rates in admin actions.
- [ ] Keep settings templates defensive for older or empty data.
- [ ] Add admin UI tests for rendering, creation, validation, and deletion.
- [ ] Run `pytest -q tests/test_admin_ui.py`.
- [ ] Commit as `feat: manage model price tiers in settings`.

### 6. Current Cached And Open-Weight Pricing Seeds

- [ ] Re-check first-party pricing sources before entering seed values.
- [ ] Add first-party providers and prices for verified Alibaba/Qwen, DeepSeek, Z.ai,
  Moonshot, and Mistral open-weight model families.
- [ ] Add router fallback providers and prices only for models without first-party
  per-token API pricing.
- [ ] Include aliases for common official API IDs and router IDs.
- [ ] Include source URLs, checked dates, release dates, and concise notes.
- [ ] Add seed tests for provider/model presence, cached rates, tiers, aliases, and
  non-overwriting behavior.
- [ ] Document skipped candidates here with reason and source checked.
- [ ] Run `pytest -q tests/test_rendering_and_cli.py`.
- [ ] Commit as `feat: seed current cached and open-weight pricing`.

### 7. Documentation

- [ ] Update `README.md`.
- [ ] Update `README.pypi.md`.
- [ ] Update `docs/tests/README.md`.
- [ ] Remove stale language saying cost estimates ignore cache.
- [ ] Document tiered pricing, cache behavior, source policy, and router fallback.
- [ ] Run `pytest -q tests/test_rendering_and_cli.py tests/test_admin_ui.py`.
- [ ] Commit as `docs: document v0.4 pricing behavior`.

### 8. Version And Release Checks

- [ ] Bump `pyproject.toml` to `0.4.0`.
- [ ] Update README version strings.
- [ ] Run `ruff check src tests scripts`.
- [ ] Run `python -m compileall -q src tests scripts`.
- [ ] Run `pytest -q`.
- [ ] Run `python scripts/publish_pypi.py --dry-run`.
- [ ] Commit as `chore: bump version to 0.4.0`.

## Acceptance Checklist

- [ ] Existing scalar pricing behavior remains compatible.
- [ ] Tiered pricing applies per request, not from aggregate run totals.
- [ ] Cached input tokens use cached rates only when configured.
- [ ] Seeded prices are source-attributed and do not overwrite user edits.
- [ ] Recent open-weight models are seeded from first-party prices where available.
- [ ] Router fallback prices are stored under router providers.
- [ ] Settings UI can manage tier rows without JavaScript.
- [ ] Documentation reflects actual cache and tier behavior.
- [ ] Full test suite and release dry run pass.
