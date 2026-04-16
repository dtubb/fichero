import AppKit
import PDFKit
import SwiftUI

/// Renders a thumbnail of a PDF page locally using PDFKit.
/// - For a PDF file itself: renders page 0 (first page).
/// - For a page Document (child of a PDF): renders the specific page.
///   Pass `pageIndex = sequence - 1` (PDFKit is 0-indexed, our sequence is 1-based).
/// Used as a fallback when the backend hasn't generated a PDF thumbnail.
struct PDFThumbnailView: View {
    let path: String
    let size: CGSize
    var pageIndex: Int = 0

    @State private var image: NSImage?

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                // Placeholder while rendering.
                Image(systemName: "doc.richtext")
                    .font(.system(size: min(size.width, size.height) * 0.35))
                    .foregroundStyle(.secondary)
            }
        }
        .task(id: "\(path):\(pageIndex)") {
            image = await Self.renderThumbnail(at: path, pageIndex: pageIndex, size: size)
        }
    }

    /// Render a specific page of a PDF at the requested pixel size.
    /// Runs off the main actor — PDFKit can do the render on any thread.
    static func renderThumbnail(at path: String, pageIndex: Int = 0, size: CGSize) async -> NSImage? {
        await Task.detached(priority: .userInitiated) {
            guard let pdf = PDFDocument(url: URL(fileURLWithPath: path)),
                  pageIndex >= 0, pageIndex < pdf.pageCount,
                  let page = pdf.page(at: pageIndex) else {
                return nil
            }
            return page.thumbnail(of: size, for: .mediaBox)
        }.value
    }
}
