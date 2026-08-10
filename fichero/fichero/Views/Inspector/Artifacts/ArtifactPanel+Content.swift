import SwiftUI

extension ArtifactPanel {
    // MARK: - Content body
    //
    // ONE editor across Mac / iPad / iPhone: SwiftUI 26 `TextEditor(text:)`
    // working in `AttributedString` (#2453). The AppKit NSTextView/ruler
    // representable is retired. Native bold/italic/headings come from the OS;
    // there is no Mac-only ruler. Width clamps to the inspector pane via
    // `.frame(maxWidth: .infinity)` (#2477 — no more AppKit intrinsic overflow).
    // Storage stays portable RTF/plain; conversion happens only at the
    // ArtifactRichTextCodec boundary, never raw RTF in a view (#2454).
    @ViewBuilder
    var contentBody: some View {
        VStack(alignment: .leading, spacing: 4) {
            if isStructuredOutput {
                structuredOutputView
                    .frame(maxWidth: .infinity)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(4)
            } else if onSave != nil, rawArtifactContent.count > Self.liveEditorCharacterLimit {
                // BOOK-SIZED CONTENT NEVER ENTERS THE LIVE EDITOR (Daniel's
                // beachball, 2026-08-10 00:4x, backtrace in hand): SwiftUI's
                // AttributedString TextEditor lays out the ENTIRE document
                // synchronously inside sizeThatFits (AppKitRichTextEditorAdaptor
                // → NSTextLayoutManager.ensureLayoutForRange over the whole
                // string) — 'My Book / Shifting Livelihoods' froze the main
                // thread for minutes, on every layout pass. A parent document
                // holding a whole book's text is a READ surface; its PAGES are
                // where editing happens and they stay under the limit.
                oversizeContentPreview
            } else if onSave != nil {
                TextEditor(text: $draftText)
                    .editorScaledFont()
                    .focused($isEditorFocused)
                    .scrollContentBackground(.hidden)
                    // BOUNDED HEIGHT, never intrinsic (Daniel's live
                    // backtraces, 2026-08-10): an unbounded proposal makes
                    // the AttributedString editor's sizeThatFits run
                    // NSTextLayoutManager.ensureLayoutForRange over the WHOLE
                    // document on the main thread, per layout pass — the
                    // spinning wheel while 'navigating a pdf'. A concrete
                    // ceiling turns sizing O(1); the editor scrolls
                    // internally past it, exactly like the fillsHeight pane.
                    .frame(maxWidth: .infinity, maxHeight: fillsHeight ? .infinity : 420)
                    .frame(minHeight: 60)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(4)
                    .onChange(of: draftText) { _, _ in scheduleAutoSave() }
                    .onChange(of: isEditorFocused) { _, focused in
                        if focused {
                            // Register this editor's flush so an external
                            // navigation (image prev/next) or inspector tab
                            // switch can persist the in-flight edit BEFORE the
                            // focused document changes and the editor reseeds
                            // (#2476). Only the Page Content editor registers;
                            // it's the single editor the Content tab nav affects.
                            if isPageContent {
                                documentStore?.registerActivePageEdit { await flushAutoSave() }
                            }
                        } else {
                            Task { await flushAutoSave() }
                        }
                    }
            } else {
                // Read-only host (detached artifact window) — render the styled
                // text, still selectable, with no editor chrome.
                ScrollView {
                    Text(draftText)
                        .font(.body)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)
                }
                .frame(maxWidth: .infinity, maxHeight: fillsHeight ? .infinity : nil)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
            }
            if let saveError {
                Text(saveError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .task(id: rawArtifactContent) {
            // Re-seed when the stored content changes externally (workflow
            // re-run, navigation to a different doc, a remote edit). Skip when
            // it's our own save echoing back, detected by the lastLoadedRaw
            // watermark (#2478). Seeding also resets lastSavedEncoded so the
            // programmatic write below doesn't read as a user edit.
            guard watermarks.shouldReseed(from: rawArtifactContent) else { return }
            // A reseed IS a new editing session (document switch, workflow
            // re-run, remote edit). Drop the undo stack so ⌘Z cannot walk back
            // into the previous document's typing (#4354).
            undoManager?.removeAllActions()
            let decoded = ArtifactRichTextCodec.decodeAttributed(rawArtifactContent)
            draftText = decoded
            watermarks.seed(
                raw: rawArtifactContent,
                encoded: ArtifactRichTextCodec.encodeAttributed(decoded)
            )
        }
    }

    // MARK: - Oversize content (the live-editor beachball guard)

    /// Characters above which the LIVE editor is not mounted. ~100k is a very
    /// long chapter; books run to megabytes and TextKit walks every character
    /// on the main thread in the editor's sizing pass.
    static let liveEditorCharacterLimit = 60_000

    /// How much of an oversize document the read-only preview shows.
    static let oversizePreviewCharacters = 60_000

    @ViewBuilder
    private var oversizeContentPreview: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(
                "Large document — showing a preview. Edit its pages instead.",
                systemImage: "book.closed"
            )
            .font(.caption)
            .foregroundStyle(.secondary)
            ScrollView {
                // Plain-string prefix, deliberately: the whole point is that
                // no full-length AttributedString ever reaches layout.
                Text(String(rawArtifactContent.prefix(Self.oversizePreviewCharacters)))
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(6)
            }
            .frame(maxHeight: fillsHeight ? .infinity : 360)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
            Text(
                "\(rawArtifactContent.count.formatted()) characters total — "
                    + "preview shows the first \(Self.oversizePreviewCharacters.formatted())."
            )
            .font(.caption2)
            .foregroundStyle(.tertiary)
        }
    }
}
