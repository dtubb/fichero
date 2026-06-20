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

    /// Whether the canvas is showing the editing surface (tools) rather than
    /// the plain zoom/loupe preview. Off by default so chrome stays minimal
    /// until the user opts into editing (#1453). Reset whenever the document
    /// changes so a new selection always opens in view mode.
    @State private var isEditing = false
    @Environment(\.openURL) private var openURL

    var body: some View {
        Group {
            if let doc = document {
                documentPreview(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 300)
        .onChange(of: document?.id) { _, _ in
            isEditing = false
        }
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
        }
    }

    // MARK: - Header Bar

    private func headerBar(_ doc: Document) -> some View {
        HStack {
            // Icon and name
            Image(systemName: doc.fileType?.icon ?? doc.docType.icon)
                .foregroundColor(.accentColor)

            Text(doc.name)
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
                }
                #endif

                Button(
                    action: { openWithDefault(doc) },
                    label: {
                        Image(systemName: "arrow.up.forward.square")
                    }
                )
                .buttonStyle(.plain)
                .help("Open with default app")
            }
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Preview Content

    enum PreviewRoute: Equatable {
        case container
        case storageDisplay(documentId: String)
        case imageEditor(documentId: String)
        case quickLook

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
        return .container
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
        case .container:
            containerPlaceholder(doc)
        case .storageDisplay(let documentId):
            #if os(macOS)
            ZStack(alignment: .topTrailing) {
                DocumentCanvas(content: .imageStorageDisplay(documentId: documentId))
                editModeToggle
            }
            #else
            DocumentCanvas(content: .imageStorageDisplay(documentId: documentId))
            #endif
        case .imageEditor:
            ImageEditorView(
                document: doc,
                onNavigate: onNavigateToDocument,
                selectedDocumentIDs: selectedDocumentIDs
            )
        case .quickLook:
            QuickLookDownloadView(document: doc)
        }
    }

    private func containerPlaceholder(_ doc: Document) -> some View {
        ContentUnavailableView(
            doc.name,
            systemImage: doc.docType.icon,
            description: Text("No selection")
        )
    }

    // MARK: - Edit-mode Toggle

    /// Far-corner toggle that flips the image canvas between view and edit
    /// mode. Floats at the top-trailing edge so it is visible whether or not
    /// the document header is shown (the reading surface hides the header). (#1453)
    #if os(macOS)
    private var editModeToggle: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                isEditing.toggle()
            }
        } label: {
            // Plain icon button matching the canvas toolbar convention (the
            // PDF loupe toggle): a filled/outline `pencil.circle` pair shows the
            // selected state via accent tint instead of a grey filled circle, at
            // the same default icon size as its neighbours. (#1528)
            Image(systemName: isEditing ? "pencil.circle.fill" : "pencil.circle")
        }
        .buttonStyle(.plain)
        .foregroundColor(isEditing ? .accentColor : .primary)
        .help(isEditing ? "Done — return to viewing" : "Edit image (crop, rotate, enhance, remove background)")
        .accessibilityIdentifier("canvasEditModeToggle")
        // Center within the canvas toolbar's standard band and inset from the
        // trailing edge so the edit icon sits on the same baseline as the zoom /
        // loupe icons in the mini-toolbar, instead of floating slightly high
        // with its own padding (#1556).
        .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight, alignment: .center)
        .padding(.trailing, 12)
    }
    #endif

    // MARK: - Text Preview

    private func textPreview(_ doc: Document) -> some View {
        ScrollView {
            if let content = doc.pageContent {
                Text(content)
                    .font(.system(.body, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
            } else {
                Text("No content available")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color(red: 253/255, green: 253/255, blue: 253/255, opacity: 1))
    }

    // MARK: - Generic Preview

    private func genericPreview(_ doc: Document) -> some View {
        VStack(spacing: 16) {
            Image(systemName: doc.fileType?.icon ?? "doc")
                .font(.system(size: 64))
                .foregroundColor(.secondary)

            Text(doc.name)
                .font(.headline)

            if let fileType = doc.fileType {
                Text(fileType.rawValue.uppercased())
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.secondary.opacity(0.2))
                    .cornerRadius(4)
            }

            // Show content if available
            if let content = doc.pageContent {
                ScrollView {
                    Text(content)
                        .font(.body)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 200)
                .background(Color(red: 253/255, green: 253/255, blue: 253/255, opacity: 1))
                .cornerRadius(8)
                .padding(.horizontal)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

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
}

// MARK: - Preview

#Preview("Empty") {
    EditorView(document: nil)
        .frame(width: 500, height: 400)
}
// ZoomableImageView retired in #1402 — all image display now routes through DocumentCanvas.
