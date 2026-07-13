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
    /// Drives the image reader toolbar's edit button. `nil` greys the tool out
    /// (e.g. PDFs, which have no in-app editor). Threaded down to the image
    /// viewer so the edit control lives in the bottom reader toolbar instead of
    /// floating over the split control (#2421).
    var isEditing: Binding<Bool>?

    enum Content {
        /// A backend storage display image, resolved by document id.
        case imageStorageDisplay(documentId: String)
        /// A backend-rendered PlatformImage (editor mode — may be nil while loading).
        case imageRendered(image: PlatformImage?, documentId: String)
        /// A PDF document at a given page index.
        case pdf(documentId: String, pageIndex: Int)
        /// A text/Markdown representation (#2264) — e.g. a `convert` artifact.
        case markdown(text: String)
    }

    var body: some View {
        switch content {
        case .imageStorageDisplay(let docId):
            StorageDisplayImageCanvas(
                documentId: docId,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing
            )
        case .imageRendered(let nsImage, let docId):
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing
            )
        case .pdf(let documentId, let pageIndex):
            PDFPageWithToolbar(
                documentId: documentId,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange
            )
        case .markdown(let text):
            MarkdownCanvas(text: text)
        }
    }
}

/// Renders a Markdown representation as scrollable, selectable text (#2264).
///
/// Native rendering only — `AttributedString(markdown:)` for inline + block
/// syntax, falling back to the raw text if it doesn't parse. Heavier Markdown
/// (tables, images) can graduate to a web view later if a corpus needs it.
private struct MarkdownCanvas: View {
    let text: String

    private var attributed: AttributedString {
        (try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(text)
    }

    var body: some View {
        ScrollView {
            Text(attributed)
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
        }
    }
}

private struct StorageDisplayImageCanvas: View {
    let documentId: String
    var onNavigateToDocument: ((String) -> Void)?
    var isEditing: Binding<Bool>?

    @Environment(StorageServiceGenerated.self) private var storageService
    @State private var image: PlatformImage?
    @State private var loadError: Error?

    var body: some View {
        ZStack {
            if image != nil {
                DocumentCanvas(
                    content: .imageRendered(image: image, documentId: documentId),
                    onNavigateToDocument: onNavigateToDocument,
                    isEditing: isEditing
                )
            } else if let loadError {
                // Surface the failure with a message + Retry instead of a mute
                // icon (#3210), matching QuickLookDownloadView in the same pane
                // (raise-not-silent).
                ContentUnavailableView {
                    Label("Couldn't load image", systemImage: "photo")
                } description: {
                    Text(loadError.localizedDescription)
                } actions: {
                    Button("Retry") { Task { await loadImage() } }
                }
            } else {
                // ★ EVERY FRAME PERFECT (#3616): a sized skeleton filling the
                // reserved pane instead of a bare spinner, so the image/PDF page
                // cross-fades in (below) with no blank frame or pop.
                SkeletonPlaceholder()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // Cross-fade the branch swap as the loaded image replaces the skeleton.
        .animation(.easeOut(duration: 0.25), value: image == nil)
        .task(id: documentId) { await loadImage() }
    }

    private func loadImage() async {
        image = nil
        loadError = nil
        do {
            image = try await storageService.getDisplayPlatformImage(documentId)
        } catch {
            loadError = error
        }
    }
}
