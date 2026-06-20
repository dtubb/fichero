import PDFKit
import SwiftUI

/// One canonical canvas for image and PDF documents (#1402).
///
/// Replaces the three parallel zoom wrappers (ZoomableImageView, and the
/// since-removed ZoomableNSImageView) with a single entry point that reuses
/// the existing viewer stack:
///   • image storage      → StorageDisplayImageCanvas — full loupe/zoom/magnifier via HTTP
///   • image rendered     → ZoomableImagePreview(renderedImage:) — same stack, NSImage override
///   • PDF                → PDFPageWithToolbar
///
/// Plain preview, folder-page reading surface, and the editor all route here.
struct DocumentCanvas: View {
    let content: Content
    /// Fired when the user navigates to a different PDF page within the canvas.
    var onPageIndexChange: ((Int) -> Void)?
    /// Fired when the user steps to a sibling image in the folder image viewer.
    var onNavigateToDocument: ((String) -> Void)?

    enum Content {
        /// A backend storage display image, resolved by document id.
        case imageStorageDisplay(documentId: String)
        /// A backend-rendered PlatformImage (editor mode — may be nil while loading).
        case imageRendered(image: PlatformImage?, documentId: String)
        /// A PDF document at a given page index.
        case pdf(documentId: String, pageIndex: Int)
    }

    var body: some View {
        switch content {
        case .imageStorageDisplay(let docId):
            StorageDisplayImageCanvas(
                documentId: docId,
                onNavigateToDocument: onNavigateToDocument
            )
        case .imageRendered(let nsImage, let docId):
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage,
                onNavigateToDocument: onNavigateToDocument
            )
        case .pdf(let documentId, let pageIndex):
            PDFPageWithToolbar(
                documentId: documentId,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange
            )
        }
    }
}

private struct StorageDisplayImageCanvas: View {
    let documentId: String
    var onNavigateToDocument: ((String) -> Void)?

    @EnvironmentObject private var storageService: StorageServiceGenerated
    @State private var image: PlatformImage?
    @State private var loadError: Error?

    var body: some View {
        ZStack {
            if image != nil {
                DocumentCanvas(
                    content: .imageRendered(image: image, documentId: documentId),
                    onNavigateToDocument: onNavigateToDocument
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
                image = try await storageService.getDisplayPlatformImage(documentId)
            } catch {
                loadError = error
            }
        }
    }
}
