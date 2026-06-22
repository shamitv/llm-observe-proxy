# Phase 1 — Image Dimensions & Preview — TODO

[← Phase 1 Plan](plan.md) | [← Master Plan](../implementation_plan.md)

## Commit Plan

- [x] `docs: add v0.6 image preview plan`
- [x] `feat: add request image dimensions and preview modal`
- [x] `test: cover request image preview behavior`
- [x] `docs: document request image previews`

## Planning And Branch Setup

- [x] Create `feature/image-dimensions-preview` from
  `feature/admin-fallback-clarity`.
- [x] Add the v0.6 master implementation plan.
- [x] Add the Phase 1 plan and TODO.
- [x] Keep this planning commit free of application-code changes.

## Polling-Safe Gallery

- [x] Add a stable identity for the ordered request image list.
- [x] Skip gallery DOM replacement when the image identity is unchanged.
- [x] Rebuild the gallery when images are added, removed, reordered, or replaced.
- [x] Keep the preview modal outside the live gallery container.
- [x] Verify an open modal survives multiple one-second polling cycles.

## Thumbnail Dimensions

- [x] Render each thumbnail as a labelled native button.
- [x] Read `naturalWidth` and `naturalHeight` after image load.
- [x] Show MIME type or image kind with `<width> × <height> px`.
- [x] Show a temporary dimensions-loading state.
- [x] Show `Dimensions unavailable` when loading or decoding fails.
- [x] Add a visible unavailable-image treatment without breaking the grid.

## Preview Modal

- [x] Create one reusable request-image dialog on request detail initialization.
- [x] Populate the selected source, title, alternative text, MIME type, and dimensions.
- [x] Open in fit-to-window mode by default.
- [x] Add an `Actual size` toggle.
- [x] Render actual size at intrinsic CSS-pixel dimensions.
- [x] Keep oversized actual-size images inside a scrollable viewport.
- [x] Disable actual-size mode when dimensions are unavailable.
- [x] Add a labelled close button.
- [x] Close on backdrop click.
- [x] Close on Escape.
- [x] Do not close for clicks inside the modal.

## Accessibility

- [x] Add `role="dialog"`, `aria-modal`, and title/description relationships.
- [x] Move focus into the modal when it opens.
- [x] Trap Tab and Shift+Tab within the modal.
- [x] Restore focus to the opening thumbnail on close.
- [x] Lock body scrolling while open and restore it on close.
- [x] Add visible focus states to thumbnails and modal controls.
- [x] Ensure active, unavailable, and failure states have text labels.
- [x] Verify keyboard-only operation.

## Responsive Styling

- [x] Preserve the compact auto-filling desktop gallery.
- [x] Remove default button chrome from thumbnail controls.
- [x] Keep thumbnail imagery contained and aspect-ratio safe.
- [x] Constrain the preview modal to the viewport.
- [x] Keep actual-size overflow inside the preview viewport.
- [x] Verify close and size controls remain reachable on mobile.
- [x] Confirm no page-level horizontal scroll at supported breakpoints.
- [x] Confirm shared confirmation modal styling is unchanged.

## Automated Tests

- [x] Extend request image API assertions without changing the response contract.
- [x] Add static UI contract assertions for gallery preservation.
- [x] Add assertions for interactive thumbnail creation.
- [x] Add assertions for intrinsic dimension and fallback handling.
- [x] Add assertions for dialog semantics and fit/actual-size states.
- [x] Add assertions for Escape, backdrop, focus trap, focus restoration, and scroll
  locking.
- [x] Add assertions for scoped modal and responsive CSS.
- [x] Keep existing proxy image-extraction tests passing unchanged.
- [x] Run `.venv/bin/pytest -q tests/test_admin_ui.py tests/test_proxy_capture.py`.

## Browser Verification And Screenshot

- [x] Seed the demo database with `scripts/seed_demo_db.py`.
- [x] Confirm both seeded images display `640 × 420 px`.
- [x] Verify fit-to-window and actual-size modes at desktop width.
- [x] Verify fit-to-window and actual-size modes at mobile width.
- [x] Verify all close and focus paths.
- [x] Verify the modal remains stable through polling.
- [x] Verify an unreachable remote image degrades gracefully.
- [x] Update screenshot timing only if dimensions are not ready at capture time.
- [x] Regenerate only `docs/screenshots/images.png` from the seeded harness.
- [x] Confirm the screenshot contains no private request data.

## Documentation

- [x] Update `design.md` with the image gallery and modal interaction pattern.
- [x] Update `README.md` with dimensions and preview behavior.
- [x] Update `README.pypi.md` with the same user-facing feature description.
- [x] Update `docs/tests/README.md` with image preview coverage.
- [x] Keep `README.pypi.md` free of local screenshot references.

## Final Verification

- [ ] `.venv/bin/ruff check src tests scripts`
- [ ] `.venv/bin/python -m compileall -q src tests scripts`
- [ ] `.venv/bin/pytest -q`
- [ ] `git diff --check`
- [ ] Confirm no database migration or dependency change.
- [ ] Confirm no public or admin request-detail API shape change.
- [ ] Confirm record-only forwarding behavior is unchanged.
- [ ] Review the final branch diff for unrelated changes.
