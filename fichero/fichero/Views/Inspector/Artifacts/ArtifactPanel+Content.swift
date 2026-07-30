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
            } else if onSave != nil {
                TextEditor(text: $draftText)
                    .editorScaledFont()
                    .focused($isEditorFocused)
                    .scrollContentBackground(.hidden)
                    .frame(maxWidth: .infinity, maxHeight: fillsHeight ? .infinity : nil)
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
}
