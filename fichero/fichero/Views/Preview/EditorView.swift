import SwiftUI

// Document preview/editor view
struct EditorView: View {
    let document: Document?
    var showHeader: Bool = true
    /// Optional callback fired when the user scrolls to a different page within
    /// a PDF preview. Parent wires this to update grid selection to the
    /// matching page sibling (#586).
    var onPDFPageIndexChange: ((Int) -> Void)?
    /// Forwarded to the image editor so prev/next can sync app selection,
    /// keeping the window-level inspector pointed at the displayed image (#1265).
    var onNavigateToDocument: ((String) -> Void)?
    /// Current multi-file selection — drives batch-apply in the image editor (#1265).
    var selectedDocumentIDs: Set<String> = []

    /// Edit mode is the Inspector's "Edits" facet — the Lightroom "Develop
    /// module" model (#3593, 2026-07-12): selecting it makes the Preview
    /// the live editing canvas AND shows the controls in the Inspector, driven by
    /// the one per-window `@SceneStorage` key the Inspector already owns. Reused
    /// here (not a second state) so the two panes can never disagree. Persists
    /// across documents, like Lightroom's Develop module, rather than resetting.
    @SceneStorage("inspectorSelectedTab") private var inspectorSelectedTab: InspectorTab = .content
    @Environment(\.openURL) private var openURL
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(WindowState.self) private var windowState

    var body: some View {
        Group {
            if let doc = document {
                documentPreview(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 300)
    }

    /// True when the Preview should present the editing canvas: the Inspector's
    /// Edits facet is selected. Only meaningful for editable surfaces — the
    /// preview route re-checks the document type before mounting the editor.
    private var isEditing: Bool {
        inspectorSelectedTab == .edits
    }

    /// The Preview's own edit toggle just flips the shared facet, so turning it
    /// on shows the Inspector controls and turning it off leaves edit mode.
    private var editModeBinding: Binding<Bool> {
        Binding(
            get: { inspectorSelectedTab == .edits },
            set: { inspectorSelectedTab = $0 ? .edits : .content }
        )
    }

    // MARK: - Document Preview

    @ViewBuilder
    private func documentPreview(_ doc: Document) -> some View {
        VStack(spacing: 0) {
            if showHeader {
                headerBar(doc)
                Divider()
            }
            previewContent(doc)
                // ★ EVERY FRAME PERFECT (#3619): cross-fade when edit mode
                // overtakes the Preview (#3593) — the source canvas dissolves into
                // the editor canvas instead of a jump-cut, with the shared timing.
                .animation(FrameAnimation.crossfade, value: isEditing)
        }
    }

    // MARK: - Header Bar

    private func headerBar(_ doc: Document) -> some View {
        HStack {
            // Icon and name
            Image(systemName: doc.fileType?.icon ?? doc.docType.icon)
                .foregroundColor(.accentColor)

            // #4416: the editor header is a document-name surface too.
            Text(DocumentTitle.displayName(for: doc))
                .font(.headline)
                .lineLimit(1)

            Spacer()

            // Actions — "Reveal in Finder" only makes sense when the engine
            // is on this Mac; hide it entirely for remote engines (#1881).
            HStack(spacing: 12) {
                #if os(macOS)
                if EngineConfig.engineIsLocal {
                    Button(
                        action: { openInFinder(doc) },
                        label: {
                            Image(systemName: "folder")
                        }
                    )
                    .buttonStyle(.plain)
                    .help("Reveal in Finder")

                    Button(
                        action: { openWithDefault(doc) },
                        label: {
                            Image(systemName: "arrow.up.forward.square")
                        }
                    )
                    .buttonStyle(.plain)
                    .help("Open with default app")
                } else {
                    Button(
                        action: { downloadCopy(doc) },
                        label: {
                            Image(systemName: "square.and.arrow.down")
                        }
                    )
                    .buttonStyle(.plain)
                    .help("Download a Copy…")
                }
                #else
                Button(
                    action: { openWithDefault(doc) },
                    label: {
                        Image(systemName: "arrow.up.forward.square")
                    }
                )
                .buttonStyle(.plain)
                .help("Open with default app")
                #endif
            }
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Preview Content

    enum PreviewRoute: Equatable {
        /// A selected container has no previewable source asset. Present the same
        /// centered no-selection state as an empty selection (#1855).
        case noSelection
        case storageDisplay(documentId: String)
        case imageEditor(documentId: String)
        case text(content: String)
        /// Audio/video streamed via AVPlayer against the storage endpoint (#3208).
        case media(documentId: String)
        case quickLook
        /// A plain folder previews like a PDF: its items are its "pages" (#25).
        /// Shows the first previewable child; swiping then steps through the
        /// folder via the ContentView sibling navigation.
        case folderContents(folderId: String)
        /// A calm large-symbol placeholder for nodes that have nothing to
        /// preview by design (workflow mirrors) — never an error state.
        case glyph(systemImage: String, title: String)

        var usesImageEditingPreviewForViewing: Bool {
            if case .imageEditor = self {
                return true
            }
            return false
        }
    }

    private static var supportsImageEditingPreview: Bool {
        #if os(macOS)
        true
        #else
        false
        #endif
    }

    static func previewRoute(for doc: Document, isEditing: Bool) -> PreviewRoute {
        if doc.isWorkflowNode {
            // A workflow mirror has NO source file — the Quick Look route
            // showed a scary "Preview unavailable / Source file not
            // available / Retry" (Daniel, 2026-08-10: "say something better
            // than that, or just do the folder icon"). A calm glyph is the
            // honest preview: workflows are edited, not previewed.
            return .glyph(systemImage: doc.displaySymbol(), title: doc.name)
        }
        if doc.docType == .folder {
            return folderPreviewRoute(for: doc, isEditing: isEditing)
        }
        if doc.docType == .page {
            return pagePreviewRoute(for: doc, isEditing: isEditing)
        }
        if doc.fileType == .pdf {
            return .storageDisplay(documentId: doc.id)
        }
        if doc.fileType == .image {
            if isEditing && supportsImageEditingPreview {
                return .imageEditor(documentId: doc.id)
            }
            return .storageDisplay(documentId: doc.id)
        }
        // Audio/video stream progressively via AVPlayer (#3208) instead of the
        // whole-file QuickLook download. Formats AVFoundation can't play
        // (mkv/avi/…) fall through to the QuickLook fallback below.
        if doc.fileType == .audio || doc.fileType == .video, MediaStreamPreview.canStream(doc) {
            return .media(documentId: doc.id)
        }
        // Text-bearing documents (txt / docx / md) render as annotatable text
        // so highlight + note work on the body (#2458 slice 3). Falls back to
        // Quick Look when there's no extracted text.
        if let content = doc.pageContent, !content.isEmpty {
            return .text(content: content)
        }
        return .quickLook
    }

    private static func folderPreviewRoute(for doc: Document, isEditing: Bool) -> PreviewRoute {
        if doc.fileType == .image {
            if isEditing && supportsImageEditingPreview {
                return .imageEditor(documentId: doc.id)
            }
            return .storageDisplay(documentId: doc.id)
        }
        if doc.fileType == .pdf {
            return .storageDisplay(documentId: doc.id)
        }
        return .folderContents(folderId: doc.id)
    }

    private static func pagePreviewRoute(
        for doc: Document,
        isEditing: Bool
    ) -> PreviewRoute {
        if isEditing {
            return .imageEditor(documentId: doc.id)
        }
        return .storageDisplay(documentId: doc.id)
    }

    @ViewBuilder
    private func previewContent(_ doc: Document) -> some View {
        switch Self.previewRoute(for: doc, isEditing: isEditing) {
        case .noSelection:
            emptyState
        case .storageDisplay(let documentId):
            let supportsFolderNav = doc.fileType == .image || doc.docType == .page
            // Image editing is only meaningful for image-backed previews. Passing
            // the `isEditing` binding into the canvas surfaces the edit control in
            // the unified bottom reader toolbar (greyed for PDFs) instead of a
            // floating toggle that overlapped the split control (#2421). On PDFs
            // and non-mac platforms the binding is nil, so the tool greys out.
            let isImageEditable = (doc.fileType == .image || doc.docType == .page)
                && Self.supportsImageEditingPreview
            DocumentCanvas(
                content: .imageStorageDisplay(documentId: documentId),
                onNavigateToDocument: supportsFolderNav ? onNavigateToDocument : nil,
                isEditing: isImageEditable ? editModeBinding : nil
            )
        case .imageEditor:
            ImageEditorView(
                document: doc,
                onNavigate: onNavigateToDocument,
                selectedDocumentIDs: selectedDocumentIDs
            )
        case .text(let content):
            DocumentTextReader(document: doc, content: content)
        case .media(let documentId):
            MediaStreamPreview(document: doc)
                .id(documentId)
        case .quickLook:
            QuickLookDownloadView(document: doc)
        case .folderContents(let folderId):
            FolderContentsPreview(
                folderId: folderId,
                onNavigateToDocument: onNavigateToDocument
            )
        case .glyph(let systemImage, let title):
            GlyphPreviewPlaceholder(systemImage: systemImage, title: title)
        }
    }

    // MARK: - Edit-mode Toggle
    //
    // The edit toggle moved out of this floating overlay and into the unified
    // bottom reader toolbar (`ReaderToolbar`), driven by the `isEditing` binding
    // threaded through `DocumentCanvas`. This removed the overlap with the split
    // control (#2421). See `previewContent(_:)` `.storageDisplay`.

    // MARK: - Empty State

    private var emptyState: some View {
        Text("No selection")
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Actions

    #if os(macOS)
    private func openInFinder(_ doc: Document) {
        guard let path = doc.path else { return }
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
    #endif

    private func openWithDefault(_ doc: Document) {
        guard let path = doc.path else { return }
        let url = URL(fileURLWithPath: path)
        openURL(url)
    }

    #if os(macOS)
    private func downloadCopy(_ doc: Document) {
        guard let storageService = libraryManager.getLibrary(id: windowState.libraryId)?.storageService
            ?? libraryManager.globalLibrary?.storageService else { return }
        Task {
            guard let tempURL = try? await storageService.downloadSourceFile(doc.id),
                  let destinationURL = await presentDownloadPanel(for: doc, suggestedFrom: tempURL) else { return }
            do {
                if FileManager.default.fileExists(atPath: destinationURL.path) {
                    try FileManager.default.removeItem(at: destinationURL)
                }
                try FileManager.default.copyItem(at: tempURL, to: destinationURL)
            } catch {
                return
            }
        }
    }

    private func presentDownloadPanel(for doc: Document, suggestedFrom tempURL: URL) async -> URL? {
        await withCheckedContinuation { continuation in
            let panel = NSSavePanel()
            panel.nameFieldStringValue = doc.name.isEmpty ? tempURL.lastPathComponent : doc.name
            panel.canCreateDirectories = true
            panel.begin { result in
                continuation.resume(returning: result == .OK ? panel.url : nil)
            }
        }
    }
    #endif
}

// MARK: - Preview

#Preview("Empty") {
    EditorView(document: nil)
        .frame(width: 500, height: 400)
}

// Compact reader variant (#3019) — how the reader presents on iPhone: pushed
// full-width inside the library NavigationStack (compactLibraryReaderStack),
// not in a preview split.
#Preview("Reader — Compact (iPhone)") {
    NavigationStack {
        EditorView(document: nil)
            .navigationTitle("Reader")
    }
    .environment(\.horizontalSizeClass, .compact)
    .frame(width: 390, height: 780)
}
// ZoomableImageView retired in #1402 — all image display now routes through DocumentCanvas.

/// Calm large-symbol preview for nodes with nothing to preview by design
/// (workflow mirrors) — never an error state (Daniel, 2026-08-10).
private struct GlyphPreviewPlaceholder: View {
    let systemImage: String
    let title: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 56))
                .foregroundStyle(.secondary)
            Text(title)
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
