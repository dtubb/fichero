import AppKit
import PDFKit
import SwiftUI

/// Renders a thumbnail of a PDF's first page locally using PDFKit.
/// Used as a fallback when the backend hasn't generated a PDF thumbnail.
struct PDFThumbnailView: View {
    let path: String
    let size: CGSize

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
        .task(id: path) {
            image = await Self.renderThumbnail(at: path, size: size)
        }
    }

    /// Render the first page of a PDF at the requested pixel size.
    /// Runs off the main actor — PDFKit can do the render on any thread.
    static func renderThumbnail(at path: String, size: CGSize) async -> NSImage? {
        await Task.detached(priority: .userInitiated) {
            guard let pdf = PDFDocument(url: URL(fileURLWithPath: path)),
                  let page = pdf.page(at: 0) else {
                return nil
            }
            return page.thumbnail(of: size, for: .mediaBox)
        }.value
    }
}
