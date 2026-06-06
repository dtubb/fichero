import PDFKit
import SwiftUI

/// One canonical canvas for image and PDF documents (#1402).
///
/// Replaces the three parallel zoom wrappers (ZoomableImageView, and the
/// since-removed ZoomableNSImageView) with a single entry point that reuses
/// the existing viewer stack:
///   • image local file   → ZoomableImagePreview(url:)  — full loupe/zoom/magnifier
///   • image rendered     → ZoomableImagePreview(renderedImage:) — same stack, NSImage override
///   • PDF                → PDFPageWithToolbar
///
/// Plain preview, folder-page reading surface, and the editor all route here.
struct DocumentCanvas: View {
    let content: Content
    /// Fired when the user navigates to a different PDF page within the canvas.
    var onPageIndexChange: ((Int) -> Void)?

    enum Content {
        /// A local file image (ZoomableImagePreview URL path).
        case imageFile(url: URL, documentId: String?)
        /// A backend storage display image, resolved by document id.
        case imageStorageDisplay(documentId: String)
        /// A backend-rendered NSImage (editor mode — may be nil while loading).
        case imageRendered(image: NSImage?, documentId: String)
        /// A PDF document at a given page index.
        case pdf(path: String, pageIndex: Int)
    }

    var body: some View {
        switch content {
        case .imageFile(let url, let docId):
            ZoomableImagePreview(url: url, documentId: docId)
        case .imageStorageDisplay(let docId):
            StorageDisplayImageCanvas(documentId: docId)
        case .imageRendered(let nsImage, let docId):
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage
            )
        case .pdf(let path, let pageIndex):
            PDFPageWithToolbar(
                path: path,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange
            )
        }
    }
}

private struct StorageDisplayImageCanvas: View {
    let documentId: String

    @EnvironmentObject private var storageService: StorageServiceGenerated
    @State private var image: NSImage?
    @State private var loadError: Error?

    var body: some View {
        ZStack {
            if image != nil {
                DocumentCanvas(
                    content: .imageRendered(image: image, documentId: documentId)
                )
            } else if loadError != nil {
                Image(systemName: "photo")
                    .font(.system(size: 48))
                    .foregroundStyle(.secondary)
            } else {
                ProgressView()
                    .controlSize(.small)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: documentId) {
            image = nil
            loadError = nil
            do {
                image = try await storageService.getDisplayNSImage(documentId)
            } catch {
                loadError = error
            }
        }
    }
}
