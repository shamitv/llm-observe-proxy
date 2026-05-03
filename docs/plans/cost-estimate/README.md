# Cost Estimate Plan

## Goal

Help users understand what captured LLM traffic costs, both at capture time and after the
fact. The proxy should keep the current record-only behavior: every request is forwarded
to upstream, and cost analysis is derived from captured request/response data.

The feature now includes run-level what-if pricing. A run detail page such as
`/admin/runs/1` should answer questions like:

- What would this run have cost with GPT-5.5?
- What would this run have cost with GPT-5.4 Mini?
- Which requests were included or skipped because token usage was missing?

What-if estimates are analysis only. They must not mutate historical request cost
snapshots.

## Current Implementation

The `feature/cost-estimator` branch already adds capture-time cost estimates.

Implemented data model:

- `model_providers`: editable provider records with slug, name, upstream URL, and
  currency.
- `model_prices`: editable model token rates with provider, model, aliases, display
  name, input USD per 1M tokens, output USD per 1M tokens, active flag, and notes.
- `request_records` billing snapshot fields:
  - provider slug and name
  - billing model
  - input, output, and total tokens
  - input, output, and total estimated USD cost
  - pricing snapshot JSON

Implemented behavior:

- SQLite initialization seeds editable OpenAI, Anthropic, and Google Gemini provider and
  price rows.
- Seed rows are inserted only when missing, so user edits are preserved.
- The proxy estimates cost after non-streaming responses when usage data is available.
- The proxy estimates cost after streaming responses when a final usage event is present.
- Model routing can provide the billing provider/model when a route rewrites the upstream
  model.
- If no route metadata is available, provider resolution falls back to an exact upstream
  base URL match.
- Historical request rows keep their original pricing snapshot and are not recalculated
  when settings change.
- The admin settings page can create, update, and delete providers and model prices.
- Request tables, request detail pages, and run detail pages expose captured token and
  cost totals where available.
- Run detail pages can compare captured run token usage against selected active model
  prices with repeated `what_if` query parameters.

Current pricing formula:

```text
cost = (input_tokens * input_rate + output_tokens * output_rate) / 1,000,000
```

Current limitations:

- Pricing is static seeded data plus manual UI edits.
- There is no LiteLLM pricing/model-info sync.
- Estimates ignore cache, batch/flex/priority tiers, tool fees, image/audio pricing,
  regional premiums, and long-context premiums.
- Unknown local models show token totals but no cost unless a matching provider/model
  price is configured.
- What-if estimates are not persisted and do not recalculate historical request
  snapshots.

## Run What-If Pricing

The run detail page includes a what-if cost panel. For a run like the one shown at
`/admin/runs/1`, the page should be able to compare the run's captured token totals
against selected configured model prices.

Example scenarios:

- GPT-5.5
- GPT-5.4 Mini

Using the rounded screenshot totals as an illustration only:

```text
input tokens:  1.97M
output tokens: 25.9k

GPT-5.5 at $5.00 input / $30.00 output per 1M:
  approx $10.63

GPT-5.4 Mini at $0.75 input / $4.50 output per 1M:
  approx $1.59
```

The implementation should use exact stored per-request token counts, not rounded display
values.

## User Experience

Add a compact **What-if cost** section on `GET /admin/runs/{id}`.

Initial UI:

- Show two default comparison rows when those prices exist:
  - OpenAI / `gpt-5.5`
  - OpenAI / `gpt-5.4-mini`
- Allow the user to choose other active `model_prices` from a form on the same page.
- Keep the result server-rendered and bookmarkable with query parameters.
- Do not require JavaScript for the first version.

Suggested query shape:

```text
/admin/runs/1?what_if=openai:gpt-5.5&what_if=openai:gpt-5.4-mini
```

Suggested table columns:

- Scenario
- Input tokens
- Output tokens
- Input rate
- Output rate
- Input cost
- Output cost
- Total cost
- Requests included
- Requests missing usage

Behavior details:

- Include only requests in the selected run.
- Include a request when both input and output token counts are known.
- Count requests with missing input or output tokens separately.
- Show the selected price source/notes in a compact detail row or tooltip.
- Do not change `request_records.billing_total_cost_usd`.
- Do not write new rows for what-if calculations in the first version.

## Backend Plan

### `costing.py`

Add pure helpers that can be tested without FastAPI:

- `RunCostScenario`
- `estimate_run_cost(records, price)`
- optional `estimate_run_costs(records, prices)`

The helper should return:

- provider slug/name
- model and display name
- input/output rates
- summed input/output/total tokens
- input/output/total cost
- included request count
- missing usage request count

Use `Decimal` for all money math and the existing per-1M token formula.

### `database.py`

No schema change is required for the first version.

Add small query helpers only if they keep `admin.py` readable:

- load a run with its request records
- load active prices by `(provider_slug, model)` pairs
- load default what-if prices

Inactive prices should not appear as selectable scenarios unless a future UI explicitly
supports historical/inactive comparisons.

### `admin.py`

Extend the run detail route:

1. Parse repeated `what_if` query values.
2. Resolve values shaped like `provider_slug:model`.
3. If no values are provided, default to `openai:gpt-5.5` and
   `openai:gpt-5.4-mini` when present.
4. Ignore unknown or inactive scenarios and show a small validation message when useful.
5. Pass active prices, selected scenario keys, and computed scenario rows to the template.

Keep the existing run stats unchanged.

### Templates and CSS

Update `templates/run_detail.html` with a compact panel below the current KPI/stat cards
or near the existing cost KPI.

UI constraints:

- Keep the page operational and dense.
- Avoid a marketing-style explanation block.
- Make missing usage visible without drowning out the main comparison.
- Use existing table, pill, KPI, and form styles where possible.

## Tests

Add focused coverage in `tests/test_rendering_and_cli.py` or a new costing test module:

- A run what-if estimate uses exact per-request token counts.
- Input and output costs are split and summed correctly.
- Requests with missing usage are excluded and counted.
- Decimal values are stable for small token counts.

Add coverage in `tests/test_admin_ui.py`:

- Run detail defaults to GPT-5.5 and GPT-5.4 Mini when prices exist.
- Run detail accepts repeated `what_if` query params.
- Unknown scenario keys do not crash the page.
- Inactive model prices are not used.
- The rendered page shows total cost, included request count, and missing usage count.

Update `docs/tests/README.md` after implementation.

## Future Work

Possible follow-ups after run what-if:

- LiteLLM pricing/model-info import as an explicit sync action.
- Saved named comparison sets, such as `OpenAI default comparison`.
- Per-request what-if deltas for the most expensive requests in a run.
- CSV export for run what-if comparisons.
- Optional recalculation command for historical rows, clearly separated from immutable
  capture-time snapshots.
- More detailed pricing dimensions for cached input, batch tiers, image/audio, and
  provider-specific surcharges.
