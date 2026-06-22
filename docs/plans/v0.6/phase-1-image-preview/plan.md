# Phase 1 — Image Dimensions & Preview

[← Back to Master Plan](../implementation_plan.md)

## Goal

Improve the request detail image gallery so users can see each image's intrinsic
dimensions and inspect it in a modal without navigating away from the captured request.

## Current State

The request detail API returns each captured image's kind, MIME type, source, and
base64 payload. `static/app.js` rebuilds the gallery from that response during every
one-second detail-page poll.

Each thumbnail currently:

- uses a fixed `4 / 3` presentation area;
- shows only the MIME type or image kind;
- is not an interactive control; and
- has no enlarged preview.

The database does not store dimensions, and adding stored metadata is unnecessary
because browsers expose decoded image dimensions through `naturalWidth` and
`naturalHeight`.

## Implementation Changes

### 1. Polling-Safe Image Gallery

Update the request detail image renderer in `static/app.js`.

- Give the image list a stable identity derived from the ordered image sources.
- Reuse the existing gallery when that identity has not changed instead of replacing
  its DOM during every poll.
- Rebuild the gallery only when the request's image list changes.
- Keep the preview modal outside the live-rendered gallery container so polling cannot
  close or replace an open preview.
- Continue rendering no gallery section when a request has no captured images.

This preservation applies only to the image gallery. Other live request-detail regions
continue using the existing polling behavior.

### 2. Thumbnail Dimensions

Render each thumbnail as a keyboard-accessible button within its figure.

- Keep descriptive alternative text in the form `Request image N`.
- On image load, read `naturalWidth` and `naturalHeight`.
- Display caption metadata as MIME type or image kind plus
  `<width> × <height> px`.
- While decoding is incomplete, show a non-disruptive `Loading dimensions…` state.
- If the image fails to load or has no usable intrinsic dimensions, show
  `Dimensions unavailable` and a visible unavailable-image state.
- Do not fetch, decode, inspect, or transform image bytes on the server.
- Do not use canvas APIs, so remote images do not require CORS permission merely to
  report dimensions.

The thumbnail remains constrained by the current gallery layout and uses
`object-fit: contain`; intrinsic dimensions describe the source image, not its rendered
thumbnail size.

### 3. Preview Modal

Create one reusable image preview modal from `static/app.js` and append it to the
document body when the request detail page initializes.

The modal must include:

- a dialog title such as `Request image N`;
- MIME type and intrinsic dimensions;
- the selected image;
- an `Actual size` toggle;
- a clearly labelled close button; and
- a scrollable image viewport.

Opening a thumbnail:

- records the control that opened the modal;
- updates the modal source, title, alternative text, and metadata;
- starts in fit-to-window mode every time; and
- moves focus to the close button.

Fit-to-window mode constrains the image to the available modal viewport while
preserving aspect ratio. Actual-size mode removes those constraints and renders the
image at its intrinsic CSS-pixel dimensions; the viewport scrolls in both directions
when the image exceeds the available space.

Disable actual-size mode when intrinsic dimensions are unavailable. Do not add
zooming, rotation, downloading, next/previous navigation, or image editing in Phase 1.

### 4. Accessibility And Interaction

- Use native buttons for thumbnail activation and modal controls.
- Give the dialog `role="dialog"`, `aria-modal="true"`, and labelled title/metadata.
- Close on the close button, Escape, or backdrop click.
- Keep clicks inside the modal from dismissing it.
- Trap Tab and Shift+Tab within the open modal.
- Restore focus to the opening thumbnail when the modal closes and that control still
  exists.
- Lock page scrolling while the modal is open and restore the previous document state
  on close.
- Expose visible focus indicators for thumbnails, close, and actual-size controls.
- Do not rely on color alone for unavailable, selected, or active states.

### 5. Responsive Styling

Add scoped styles in `static/styles.css`.

- Preserve the dense auto-filling thumbnail grid on desktop.
- Keep thumbnail buttons full-width with no browser-default button chrome.
- Size the modal within the viewport and reserve room for its header and controls.
- On narrow screens, use nearly the full viewport width and height while keeping close
  and actual-size controls reachable.
- Keep overflow inside the preview viewport; opening actual-size mode must not create
  page-level horizontal scrolling.
- Avoid changing the shared confirmation modal's sizing or destructive-action styles.

### 6. Documentation And Screenshot

- Update `design.md` with the durable request-image gallery and modal behavior.
- Update `README.md` and `README.pypi.md` so the image-gallery feature description
  includes dimensions and previews.
- Update `docs/tests/README.md` with the new UI coverage.
- Regenerate `docs/screenshots/images.png` only through the seeded demo database and
  screenshot harness.
- Reuse the two existing `640 × 420` seeded SVG images as the deterministic visual
  dimension check; no private traffic or new demo payload is required.
- If screenshot timing needs adjustment, make the capture script wait for image
  dimensions to render before capturing the image-detail page.

## Interfaces And Compatibility

- The admin request-detail JSON response remains unchanged.
- The `image_assets` table remains unchanged.
- Existing databases and captured request rows require no migration.
- Data URL and remote URL images continue using their stored source directly.
- Failure to load one image does not prevent other thumbnails or the rest of the
  request detail page from rendering.
- The shared one-second request-detail poll remains enabled while the modal is open.

## Test Plan

### Automated Contract Tests

Extend `tests/test_admin_ui.py` to verify:

- request detail still exposes captured data URL and remote URL images;
- the client script contains the gallery identity/preservation path;
- thumbnails are created as labelled interactive controls;
- loaded dimensions use `naturalWidth` and `naturalHeight`;
- unavailable dimensions have explicit fallback text;
- the preview uses accessible dialog semantics;
- fit and actual-size modes have distinct state/classes;
- Escape, backdrop dismissal, focus trapping, focus restoration, and scroll locking
  are wired; and
- the stylesheet includes scoped thumbnail, modal viewport, actual-size, failure, and
  responsive rules.

Keep proxy extraction coverage in `tests/test_proxy_capture.py`; no extraction behavior
changes are expected.

### Seeded Browser Verification

Using the seeded screenshot database:

1. Confirm both demo thumbnails report `640 × 420 px`.
2. Open each thumbnail and confirm fit-to-window mode is the default.
3. Toggle actual size and confirm the viewport scrolls without page overflow.
4. Close using the button, Escape, and backdrop; confirm focus returns to the opener.
5. Use Tab and Shift+Tab to confirm focus remains inside the modal.
6. Leave the modal open for multiple poll cycles and confirm it stays open and stable.
7. Repeat at desktop and mobile viewport widths.
8. Simulate or use an unreachable remote image and confirm the gallery reports the
   failure without breaking other content.

### Verification Commands

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/python -m compileall -q src tests scripts
.venv/bin/pytest -q
git diff --check
```

## Acceptance Criteria

- Every successfully loaded request image shows its intrinsic width and height.
- Clicking or keyboard-activating a thumbnail opens the correct image in a modal.
- The modal defaults to fit-to-window and offers a working actual-size mode.
- Large actual-size images scroll within the modal instead of overflowing the page.
- The modal remains open and unchanged across request-detail polling updates.
- All close paths, focus behavior, keyboard controls, and scroll locking work.
- Failed remote images degrade gracefully.
- No API, schema, dependency, capture, or proxy-forwarding behavior changes.
- Documentation and the seeded image screenshot match the implemented behavior.
