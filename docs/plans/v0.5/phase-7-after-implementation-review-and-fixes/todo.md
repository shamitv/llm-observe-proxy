# Phase 7 — After-Implementation Review & Fixes — TODO

[← Phase 7 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Firefox Fallback Controls

- [ ] Extract fallback defaults into a shared Jinja macro
- [ ] Add `return_to` to Server, Routing, and Providers fallback forms
- [ ] Validate allowed return paths in `/admin/settings/upstream-defaults`
- [ ] Redirect fallback saves back to the originating tab
- [ ] Add enhanced fallback provider menu markup
- [ ] Add click, keyboard, Escape, and viewport-aware open direction behavior
- [ ] Keep native select submission and no-JS fallback working

## Icon Parity

- [ ] Add `_icons.html` with inline SVG macros
- [ ] Replace Settings sidebar initials with icons
- [ ] Replace Settings tab initials with icons
- [ ] Replace connection summary initials with icons
- [ ] Add generic provider badges keyed by provider slug
- [ ] Add icons to add/delete/test/search/info-style controls where used in mockups
- [ ] Preserve accessible names for icon controls

## Tests

- [ ] Test fallback forms render provider options and `return_to`
- [ ] Test fallback saves redirect to Server, Routing, and Providers respectively
- [ ] Test invalid `return_to` falls back to Server
- [ ] Test Settings pages render SVG icons
- [ ] Test enhanced fallback select markup and native select sync hook

## Validation

- [ ] Run `ruff check src tests scripts`
- [ ] Run `python -m compileall -q src tests scripts`
- [ ] Run `pytest -q`
- [ ] Manually validate in Firefox at `1440x900`
- [ ] Manually validate in Firefox at `1366x768`
