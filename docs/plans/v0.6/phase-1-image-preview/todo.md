# Phase 1 — Image Dimensions & Preview — TODO

[← Phase 1 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Commit Plan

- [x] `docs: add v0.6 image preview plan`
- [ ] `feat: add request image dimensions and preview modal`
- [ ] `test: cover request image preview behavior`
- [ ] `docs: document request image previews`

## Planning And Branch Setup

- [x] Create `feature/image-dimensions-preview` from
  `feature/admin-fallback-clarity`.
- [x] Add the v0.6 master implementation plan.
- [x] Add the Phase 1 plan and TODO.
- [x] Keep this planning commit free of application-code changes.

## Polling-Safe Gallery

- [ ] Add a stable identity for the ordered request image list.
- [ ] Skip gallery DOM replacement when the image identity is unchanged.
- [ ] Rebuild the gallery when images are added, removed, reordered, or replaced.
- [ ] Keep the preview modal outside the live gallery container.
- [ ] Verify an open modal survives multiple one-second polling cycles.

## Thumbnail Dimensions

- [ ] Render each thumbnail as a labelled native button.
- [ ] Read `naturalWidth` and `naturalHeight` after image load.
- [ ] Show MIME type or image kind with `<width> × <height> px`.
- [ ] Show a temporary dimensions-loading state.
- [ ] Show `Dimensions unavailable` when loading or decoding fails.
- [ ] Add a visible unavailable-image treatment without breaking the grid.

## Preview Modal

- [ ] Create one reusable request-image dialog on request detail initialization.
- [ ] Populate the selected source, title, alternative text, MIME type, and dimensions.
- [ ] Open in fit-to-window mode by default.
- [ ] Add an `Actual size` toggle.
- [ ] Render actual size at intrinsic CSS-pixel dimensions.
- [ ] Keep oversized actual-size images inside a scrollable viewport.
- [ ] Disable actual-size mode when dimensions are unavailable.
- [ ] Add a labelled close button.
- [ ] Close on backdrop click.
- [ ] Close on Escape.
- [ ] Do not close for clicks inside the modal.

## Accessibility

- [ ] Add `role="dialog"`, `aria-modal`, and title/description relationships.
- [ ] Move focus into the modal when it opens.
- [ ] Trap Tab and Shift+Tab within the modal.
- [ ] Restore focus to the opening thumbnail on close.
- [ ] Lock body scrolling while open and restore it on close.
- [ ] Add visible focus states to thumbnails and modal controls.
- [ ] Ensure active, unavailable, and failure states have text labels.
- [ ] Verify keyboard-only operation.

## Responsive Styling

- [ ] Preserve the compact auto-filling desktop gallery.
- [ ] Remove default button chrome from thumbnail controls.
- [ ] Keep thumbnail imagery contained and aspect-ratio safe.
- [ ] Constrain the preview modal to the viewport.
- [ ] Keep actual-size overflow inside the preview viewport.
- [ ] Verify close and size controls remain reachable on mobile.
- [ ] Confirm no page-level horizontal scroll at supported breakpoints.
- [ ] Confirm shared confirmation modal styling is unchanged.

## Automated Tests

- [ ] Extend request image API assertions without changing the response contract.
- [ ] Add static UI contract assertions for gallery preservation.
- [ ] Add assertions for interactive thumbnail creation.
- [ ] Add assertions for intrinsic dimension and fallback handling.
- [ ] Add assertions for dialog semantics and fit/actual-size states.
- [ ] Add assertions for Escape, backdrop, focus trap, focus restoration, and scroll
  locking.
- [ ] Add assertions for scoped modal and responsive CSS.
- [ ] Keep existing proxy image-extraction tests passing unchanged.
- [ ] Run `.venv/bin/pytest -q tests/test_admin_ui.py tests/test_proxy_capture.py`.

## Browser Verification And Screenshot

- [ ] Seed the demo database with `scripts/seed_demo_db.py`.
- [ ] Confirm both seeded images display `640 × 420 px`.
- [ ] Verify fit-to-window and actual-size modes at desktop width.
- [ ] Verify fit-to-window and actual-size modes at mobile width.
- [ ] Verify all close and focus paths.
- [ ] Verify the modal remains stable through polling.
- [ ] Verify an unreachable remote image degrades gracefully.
- [ ] Update screenshot timing only if dimensions are not ready at capture time.
- [ ] Regenerate only `docs/screenshots/images.png` from the seeded harness.
- [ ] Confirm the screenshot contains no private request data.

## Documentation

- [ ] Update `design.md` with the image gallery and modal interaction pattern.
- [ ] Update `README.md` with dimensions and preview behavior.
- [ ] Update `README.pypi.md` with the same user-facing feature description.
- [ ] Update `docs/tests/README.md` with image preview coverage.
- [ ] Keep `README.pypi.md` free of local screenshot references.

## Final Verification

- [ ] `.venv/bin/ruff check src tests scripts`
- [ ] `.venv/bin/python -m compileall -q src tests scripts`
- [ ] `.venv/bin/pytest -q`
- [ ] `git diff --check`
- [ ] Confirm no database migration or dependency change.
- [ ] Confirm no public or admin request-detail API shape change.
- [ ] Confirm record-only forwarding behavior is unchanged.
- [ ] Review the final branch diff for unrelated changes.
