import SwiftUI

/// The WINDOW-level annotation bar (Daniel, 2026-08-30, Preview.app as the
/// model): below the toolbar, above the workflow bar, toggled by the
/// toolbar's pencil. Annotation is not a preview-pane feature — the same
/// verbs (select, marquee, line, highlight, note, star) should reach an
/// image, a PDF, the reader, an entity, an artifact, a row in library or
/// data-entry view. The bar is the one home for those verbs; surfaces
/// consume its notifications (`.previewAnnotateTool` / `.previewRegionVerb`)
/// as they learn to. Today the preview canvases answer; the rest join
/// without the bar moving.
struct AnnotationBar: View {
    /// Labels beneath the glyphs — driven by the same switch as the workflow
    /// bar's labels (Daniel, 2026-08-30: "text underneath that is shown if I
    /// show it in the top toolbar").
    var showsLabels = false

    var body: some View {
        HStack(spacing: 10) {
            Spacer(minLength: 0)
            PreviewMarkupToolsRow(showsLabels: showsLabels)
            Spacer(minLength: 0)
        }
        // Real margins (Daniel, 2026-08-30: "left right margins should be
        // more") — the row breathes instead of hugging the pane edges.
        .padding(.horizontal, 28)
        // Shared with the workflow bar (2026-09-02): the two bars are one
        // stack under one toolbar, so one table owns their height.
        .frame(height: ToolbarMetrics.rowHeight(showsLabels: showsLabels))
        .frame(maxWidth: .infinity)
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
        .accessibilityIdentifier("annotationBar")
        // ONE applier per window — mounted here so split reader panes can
        // never double-save the same span.
        .background { ReaderMarkupApplier() }
    }
}

// MARK: - Coding v1 (Daniel, 2026-08-30, ruling 4)

/// The highlight chevron menus' tag entries: "Tag Next Highlight…" opens the
/// popover; while tags are pending, a second entry shows them and clears.
struct MarkupTagMenuEntries: View {
    @Binding var showTagPopover: Bool
    @Environment(WindowState.self) private var windowState: WindowState?

    var body: some View {
        Button("Tag Next Highlight…") { showTagPopover = true }
        if let windowState, !windowState.pendingMarkupTags.isEmpty {
            Button("Clear Pending Tags (\(windowState.pendingMarkupTags.joined(separator: ", ")))") {
                windowState.pendingMarkupTags = []
            }
        }
    }
}

/// Comma-separated tag entry. The parsed tags land on
/// `WindowState.pendingMarkupTags` and ride the NEXT saved highlight /
/// underline / strikethrough / check (`addNote(tags:)`), then clear.
struct MarkupTagPopover: View {
    @Environment(WindowState.self) private var windowState: WindowState?
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Tags for the next highlight")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField("code, theme, follow-up", text: $text)
                .textFieldStyle(.roundedBorder)
                .frame(width: 220)
                .onSubmit(apply)
                .accessibilityIdentifier("markupTagField")
            HStack {
                Spacer()
                Button("Apply", action: apply)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(12)
        .onAppear { text = windowState?.pendingMarkupTags.joined(separator: ", ") ?? "" }
    }

    private func apply() {
        windowState?.pendingMarkupTags = AnnotationTagParsing.parse(text)
        dismiss()
    }
}

/// Applies the bar's highlight/underline/strikethrough to the READER's live
/// text selection as a char-span annotation (Daniel, 2026-08-30: "we can
/// highlight in reader… even in an artifact or a content"). The selection
/// arrives on the same seam the native readers and the WebKit bridge post.
private struct ReaderMarkupApplier: View {
    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore?
    /// Coding v1 (Daniel, 2026-08-30, ruling 4): pending tags ride the next
    /// highlight-family save here too — the reader is a markup surface.
    @Environment(WindowState.self) private var windowState: WindowState?

    @State private var selectionDocumentId: String?
    @State private var selectionRange: Range<Int>?

    var body: some View {
        Color.clear
            .frame(width: 0, height: 0)
            .onReceive(NotificationCenter.default.publisher(for: .readerTextSelection)) { note in
                let info = note.userInfo ?? [:]
                guard let docId = info["documentId"] as? String, !docId.isEmpty,
                      let start = info["charStart"] as? Int,
                      let end = info["charEnd"] as? Int, end > start else {
                    selectionRange = nil
                    return
                }
                selectionDocumentId = docId
                selectionRange = start..<end
            }
            .onReceive(NotificationCenter.default.publisher(for: .previewAnnotateTool)) { note in
                guard let raw = note.object as? String,
                      let tool = PreviewMarkupTool(rawValue: raw),
                      tool == .highlight,
                      let docId = selectionDocumentId,
                      let range = selectionRange,
                      let annotationStore else { return }
                let style = PreviewHighlightStyle(
                    rawValue: UserDefaults.standard.string(
                        forKey: PreviewHighlightStyle.storageKey) ?? ""
                )
                let kind: AnnotationKind = switch style {
                case .underline: .underline
                case .strikethrough: .strikethrough
                default: .highlight
                }
                let color = kind == .highlight ? style?.persistedColor : nil
                let tags = windowState?.takePendingMarkupTags() ?? []
                Task {
                    _ = await annotationStore.addNote(
                        scope: .document(docId),
                        text: "",
                        charStart: range.lowerBound,
                        charEnd: range.upperBound,
                        kind: kind,
                        color: color,
                        tags: tags
                    )
                }
            }
    }
}
