# Kimi lane — iOS reader: pinch-zoom (#2417) + folder image left/right nav (#2420)
Branch worker/reader-zoom-nav. Do NOT run xcodebuild. Do NOT push. Iterate, never replace. swiftlint touched files.
Register new .swift with ruby scripts/add-swift-file.rb.

## Tasks (additive, size-class/platform adaptive — keep Mac behavior)
1. #2417 pinch-to-zoom on iOS/iPad: the image/PDF canvas + WebKit use macOS-only `allowsMagnification`
   (ImageWithCursorTracking.swift:72, DocumentKGWebPane.swift:277, TrackingImageView.swift). Add an iOS
   path: `MagnificationGesture` (or UIScrollView pinch / webView.scrollView zoom) so pinch-zoom works on touch.
   Gate macOS vs iOS; don't break Mac.
2. #2420 folder image viewer left/right: when viewing an image that's a child of a folder, allow prev/next
   navigation to sibling images (arrow keys on Mac, swipe/buttons on touch). Reuse the existing prev/next
   nav (#1265) scoped to folder image siblings.
Add tests where unit-testable. Commit each fix separately. Write FINDINGS.md. Do not push.
