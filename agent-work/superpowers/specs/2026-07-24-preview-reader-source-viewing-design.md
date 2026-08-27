# Preview → Reader Source-Viewing Milestone Design

## Goal

Complete the source-viewing journey: a Library selection opens the original source in Preview; Reader renders derived readable content for that source; Reader source links return to the exact original document and location in Preview. iPhone supports native Quick Look for formats without a native Preview renderer. Embedded macOS proves one real UDS-backed source-viewing request.

## Surface contract

- **Preview** renders the original source with source-specific native tools: image, PDF, media, extracted text where appropriate, or Quick Look.
- **Reader** renders the derived transcript and knowledge representation. It never embeds an image/PDF Preview canvas as its default content.
- **Inspector** remains the editing, metadata, and curation surface.
- **Library** supplies stable selected-document identity; this milestone does not redesign its layout or selection model.

## Scope

### Preview format routing and iOS Quick Look

`EditorView` remains the single routing decision point. Existing native macOS Preview, PDF, image, and media routes remain unchanged.

For iPhone and iPad, a document routed to Quick Look must use the existing `PreviewDownloadService` to obtain a correctly named local cache file, then present native UIKit `QLPreviewController` through a SwiftUI bridge. The existing downloaded filename/extension is preserved because Quick Look uses it to select a renderer. Download, cancellation, selection replacement, and preview errors must surface explicitly without stale content or a stuck loading state.

Folders and absent selections continue to use the existing no-selection state; they never enter Quick Look.

### Reader transcript and source reveal

Reader remains the transcript/knowledge surface. Parent documents with readable child documents render child transcripts in deterministic source order instead of incorrectly reporting no transcript. Empty states distinguish not-yet-extracted content, absent readable text, and request failures.

A passage or claim that contains source identity must emit an exact source-reveal payload: document identity plus page/anchor when present. Preview opens that exact source. `DocumentScrollSyncState` remains the only cross-surface synchronization arbiter; no timing-based side channels are added.

Reader keeps existing fail-closed remote WebKit behavior. This milestone does not expose engine credentials to WebKit or make remote authenticated WebKit loading more permissive.

### Navigation seam

The existing state-backed compact Library entry route is verified rather than redesigned. A selected leaf document opens the intended Preview/Reader flow; folders and invalidated selections do not spuriously push. Returning restores stable Library selection.

### Embedded UDS proof

The transport/startup lane adds real runtime proof separate from in-memory routing tests: a clean Dev Embedded launch selects UDS, reaches `library.content.ready`, and completes a source-viewing-relevant authenticated request through the spawned engine. This is distinct from Preview/Reader UI code and is required before final milestone completion.

## Deliberate exclusions

- Library/Inspector layout redesigns, folder preview restructuring, Canvas, export preview, image-editing strategy, Research browser, and agent browser.
- Remote WebKit enablement or token-relaxation.
- iOS embedded engine support; iOS remains a remote-engine client.
- Replacing native Quick Look, PDFKit, AVFoundation, WebKit, or the existing download service.
- Treating in-memory transport tests, source inspection, or external Debug-engine success as UDS proof.

## Workstream ownership

1. **Preview lane** owns `Views/Preview/**`, `PreviewDownloadService`, and Preview-only tests.
2. **Reader lane** owns `Views/Reader/Page/**`, `Views/Reader/Knowledge/**`, the specific backend reader view route, and Reader/API tests.
3. **Shell lane** owns compact navigation state and its focused tests.
4. **Connection lane** owns embedded launch/UDS transport and UI/integration harness tests.

No lane edits another lane's production or test files. The integration owner reconciles contracts only after each lane is committed and reviewed.

## Acceptance criteria

1. Preview routes image, PDF, supported media, text, unknown/binary, folder, no selection, and download error states correctly without regression.
2. iPhone/iPad opens a native Quick Look controller for a Quick Look-routed document and preserves its filename extension; failure/cancellation produces an explicit state.
3. Reader defaults to readable derived content, not a source image/PDF viewer.
4. Parent documents show ordered child transcripts when available.
5. A Reader source reveal reaches the exact Preview document and page/anchor, never an unrelated approximation.
6. Compact Library navigation preserves leaf identity and does not push folders or stale/deleted selections.
7. An unlocked macOS session proves a spawned embedded engine handles one authenticated source-viewing request over UDS; an in-memory/loopback substitute cannot satisfy this criterion.
8. Final validation includes focused tests, `verify_all --standard`, isolated iOS compile, serial macOS build/tests, interactive macOS validation, and iPhone Quick Look validation. All parsed results must report zero failures.

## Risks and safeguards

- Preserve the Preview/Reader/Inspector boundary in tests to prevent surface collapse.
- Reuse `PreviewDownloadService`; no raw URLSession or local-path UI.
- Bound Reader parent/child queries with large fixtures; do not assume prior issue closure proves performance.
- Keep remote WebKit fail-closed pending a separate security design.
- A headless macOS XCUITest timeout is inconclusive, never a passing UDS/runtime check.
