import PDFKit
import Quartz
import SwiftUI

/// Document preview/editor view
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

    @EnvironmentObject private var documentStore: DocumentStore

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

            // Actions
            HStack(spacing: 12) {
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
            }
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Preview Content

    /// Resolve the parent PDF's on-disk path for a page-child document.
    /// Checks metadata["pdf_path"] first (set when ingest knows the path
    /// upfront), then the selected collection, then currentDocuments —
    /// mirrors LibraryListRow.resolvedParentPDFPath. (#890)
    private func resolvedParentPDFPath(for doc: Document) -> String? {
        let metadataPath = doc.metadata["pdf_path"]?.value as? String
        if let metadataPath, !metadataPath.isEmpty,
           !metadataPath.contains("/fichero-drop-"),
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        if let parentId {
            if let selected = documentStore.selectedCollection,
               selected.id == parentId,
               let selectedPath = selected.path,
               !selectedPath.isEmpty {
                return selectedPath
            }
            if let parent = documentStore.currentDocuments.first(where: { $0.id == parentId }),
               let parentPath = parent.path,
               !parentPath.isEmpty {
                return parentPath
            }
        }
        return metadataPath
    }

    @ViewBuilder
    private func previewContent(_ doc: Document) -> some View {
        if doc.docType == .folder {
            FolderContentsGrid(folder: doc)
        } else if doc.docType == .page,
                  let pdfPath = resolvedParentPDFPath(for: doc),
                  !pdfPath.isEmpty {
            // PDF page child — single-page view at the specific page (#595).
            // Swipe left/right at fit-scale to turn pages; onPageIndexChange
            // wires back so the grid's selected thumbnail follows (#586).
            //
            // Resolver checks metadata["pdf_path"] first, then falls back
            // to the parent doc via documentStore.selectedCollection /
            // currentDocuments — the metadata key isn't always set on
            // page children created by the ingest split (#890).
            let pageIndex = max(0, (doc.sequence ?? 1) - 1)
            PDFPageWithToolbar(
                path: pdfPath,
                pageIndex: pageIndex,
                onPageIndexChange: onPDFPageIndexChange
            )
        } else if doc.fileType == .pdf, let path = doc.path, !path.isEmpty {
            // Top-level PDF file — single-page view, starts at page 0 (#595).
            PDFPageWithToolbar(
                path: path,
                pageIndex: 0,
                onPageIndexChange: onPDFPageIndexChange
            )
        } else if doc.fileType == .image {
            // Raster images get the non-destructive editor (#469): server-rendered
            // preview with the original↔edited toggle, edit-chain ops, and the
            // chain inspector alongside.
            ImageEditorView(
                document: doc,
                onNavigate: onNavigateToDocument,
                selectedDocumentIDs: selectedDocumentIDs
            )
        } else {
            QuickLookDownloadView(document: doc)
        }
    }

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
        .background(Color(nsColor: NSColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)))
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
                .background(Color(nsColor: NSColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)))
                .cornerRadius(8)
                .padding(.horizontal)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("No Document Selected")
                .font(.headline)

            Text("Double-click a document to preview")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Actions

    private func openInFinder(_ doc: Document) {
        guard let path = doc.path else { return }
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    private func openWithDefault(_ doc: Document) {
        guard let path = doc.path else { return }
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.open(url)
    }
}

// MARK: - Zoomable Image View (with pinch/scroll zoom and pan)

struct ZoomableImageView: View {
    let document: Document

    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

    private let minScale: CGFloat = 0.5
    private let maxScale: CGFloat = 5.0

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Checkerboard background
                CheckerboardPattern()
                    .opacity(0.1)

                // Load from local path if available, otherwise from API
                if let path = document.path {
                    // Local file
                    if let nsImage = NSImage(contentsOfFile: path) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .scaleEffect(scale)
                            .offset(offset)
                            .gesture(zoomGesture)
                            .gesture(panGesture)
                            .onTapGesture(count: 2) { toggleZoom(in: geometry.size) }
                    } else {
                        failedView
                    }
                } else {
                    // Remote API - use LibraryImageView with library path header
                    LibraryImageView(documentId: document.id, imageType: .display)
                        .aspectRatio(contentMode: .fit)
                        .scaleEffect(scale)
                        .offset(offset)
                        .gesture(zoomGesture)
                        .gesture(panGesture)
                        .onTapGesture(count: 2) { toggleZoom(in: geometry.size) }
                }
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
            .clipped()
        }
        .background(Color(nsColor: NSColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)))
        // Scroll wheel zoom
        .onContinuousHover { _ in } // Enable scroll events
        .background(ScrollWheelZoomView(scale: $scale, minScale: minScale, maxScale: maxScale))
    }

    // MARK: - Gestures

    private var zoomGesture: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                let newScale = lastScale * value
                scale = min(max(newScale, minScale), maxScale)
            }
            .onEnded { _ in
                lastScale = scale
                // Reset offset if zoomed out
                if scale <= 1.0 {
                    withAnimation(.easeOut(duration: 0.2)) {
                        offset = .zero
                        lastOffset = .zero
                    }
                }
            }
    }

    private var panGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                if scale > 1.0 {
                    offset = CGSize(
                        width: lastOffset.width + value.translation.width,
                        height: lastOffset.height + value.translation.height
                    )
                }
            }
            .onEnded { _ in
                lastOffset = offset
            }
    }

    private func toggleZoom(in size: CGSize) {
        withAnimation(.easeInOut(duration: 0.3)) {
            if scale > 1.0 {
                scale = 1.0
                lastScale = 1.0
                offset = .zero
                lastOffset = .zero
            } else {
                scale = 2.0
                lastScale = 2.0
            }
        }
    }

    // MARK: - Subviews

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
            Text("Loading image...")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private var failedView: some View {
        VStack(spacing: 16) {
            Image(systemName: "photo")
                .font(.system(size: 64))
                .foregroundColor(.secondary)
            Text("Failed to load image")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Preview

#Preview("Empty") {
    EditorView(document: nil)
        .frame(width: 500, height: 400)
}
