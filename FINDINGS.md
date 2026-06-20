# Kimi lane — iOS reader: pinch-zoom + folder image nav

Branch: `worker/reader-zoom-nav`

## #2417 — iOS pinch-to-zoom

### What changed
- `fichero/fichero/Views/Library/ImageWithCursorTracking.swift`
  - Fixed the UIKit path so `UIScrollView` pinch-zoom actually works:
    - Sets `contentSize` to the image size when the image is loaded or changed.
    - Centers undersized images using `contentInset` instead of overriding the
      zoom view's frame (which broke the zoom transform).
    - Adds `isUserMagnifying` and the `scrollViewWillBeginZooming` /
      `scrollViewDidEndZooming` hooks to prevent `updateUIView` from reverting
      the user's pinch mid-gesture (#748 pattern).
    - Accounts for `contentInset` in `updateVisibleRect`, `scrollToNormalizedPosition`,
      and `panBy`.
- `fichero/fichero/Views/Library/ImageViewerComponents.swift`
  - Replaced the placeholder iOS `ZoomableImagePreview` (`ScrollView` + `Image`)
    with the fixed `ImageWithCursorTracking` representable, giving the folder
    image viewer pinch/pan/zoom on touch.
- `fichero/fichero/Views/Library/DocumentKGWebPane.swift`
  - Enabled pinch-to-zoom in the iOS web pane by injecting a viewport meta that
    allows user scaling (`user-scalable=yes`, `minimum-scale=0.5`,
    `maximum-scale=5.0`).
  - Reset `lastAppliedZoom` when the document changes so the viewport is
    injected even when the default zoom is `1.0`.

### What was skipped
- Loupe/magnifier is disabled on iOS in this pass (`loupeEnabled: false`).
  The underlying `TrackingImageView` iOS stub does not render the loupe;
  enabling the flag would show no UI. The Mac loupe path is unchanged.
- Programmatic toolbar zoom controls on iOS were not added; pinch is the
  primary touch interaction requested.

## #2420 — Folder image left/right navigation

### What changed
- `fichero/fichero/Views/ContentView+Actions.swift`
  - Extracted `navigableFolderSiblings(for:in:)` (unit-testable) and used it
    in `navigateSiblingPrevious/Next`.
  - When the current detail document is an image or page, window-level
    Command+Left/Right and the trackpad swipe now step through image/page
    siblings only, matching the editor's existing prev/next set.
- `fichero/fichero/Views/Library/DocumentCanvas.swift`
  - Added `onNavigateToDocument` parameter and forwarded it to
    `StorageDisplayImageCanvas` / `ZoomableImagePreview`.
- `fichero/fichero/Views/Library/EditorView.swift`
  - Passes `onNavigateToDocument` into `DocumentCanvas` for image/page
    `storageDisplay` routes.
- `fichero/fichero/Views/Library/ImageViewerComponents.swift`
  - iOS `ZoomableImagePreview` resolves image/page siblings from the
    `DocumentStore` environment and shows a floating prev/next button overlay
    when navigation is available.

### What was skipped
- A native swipe gesture on the iOS image canvas was not added because the
    underlying `UIScrollView` already owns pan/pinch gestures; the overlay
    buttons satisfy the "swipe/buttons on touch" requirement without gesture
    conflicts.
- The Mac key handling is unchanged; plain Left/Right still pan the zoomed
    image, while Command+Left/Right now scopes to image siblings.

## Tests

- Added unit tests in `fichero/fichero-tests/DocumentModelTests.swift` for
  `navigableFolderSiblings(for:in:)`:
  - image siblings only when current is image
  - page siblings only when current is page
  - all siblings when current is non-image/page
  - display order preservation
- Did not run the test suite because the brief explicitly forbids `xcodebuild`.
  swiftlint passed on all touched files.

## Validation

```bash
swiftlint lint ./fichero/fichero/Views/ContentView+Actions.swift \
  ./fichero/fichero/Views/Library/ImageViewer/ImageWithCursorTracking.swift \
  ./fichero/fichero/Views/Library/ImageViewerComponents.swift \
  ./fichero/fichero/Views/Library/DocumentCanvas.swift \
  ./fichero/fichero/Views/Library/DocumentKGWebPane.swift \
  ./fichero/fichero/Views/Library/EditorView.swift \
  ./fichero/fichero-tests/DocumentModelTests.swift
```

All touched files lint clean (only pre-existing `file_length` / `type_body_length`
warnings in `DocumentKGWebPane.swift`).

## Commits

1. `fe22598b` — fix(ios): pinch-to-zoom on image/PDF canvas and WebKit (#2417)
2. `d0bc4d35` — feat(views): folder image prev/next navigation (#2420)
3. (this findings file + tests)

