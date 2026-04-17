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

/// Interactive PDF page preview using PDFKit's `PDFView`.
///
/// Where `PDFThumbnailView` renders a flat `NSImage` (cheap, cacheable, fine
/// for grid/sidebar thumbnails), `PDFPageView` uses the full AppKit `PDFView`
/// so users get **selectable text, copy, find, and links** — everything a real
/// PDF reader provides. Used in the main preview pane for `.page` documents
/// (see #578). Future annotation/highlight work hooks into this view's
/// `currentSelection` / `PDFAnnotation` APIs (#579).
struct PDFPageView: NSViewRepresentable {
    let path: String
    let pageIndex: Int

    func makeNSView(context: Context) -> PDFView {
        let view = PDFView()
        view.displayMode = .singlePage
        view.displaysPageBreaks = false
        view.autoScales = true
        view.backgroundColor = NSColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)
        loadAndNavigate(view)
        return view
    }

    func updateNSView(_ view: PDFView, context: Context) {
        loadAndNavigate(view)
    }

    /// Load the PDF document (if not already loaded) and navigate to the
    /// requested page. Only replaces `document` when the path actually changes
    /// — re-assigning the same document resets the user's zoom/selection state.
    private func loadAndNavigate(_ view: PDFView) {
        let fileURL = URL(fileURLWithPath: path)
        if view.document?.documentURL != fileURL {
            view.document = PDFDocument(url: fileURL)
        }
        guard let doc = view.document,
              pageIndex >= 0, pageIndex < doc.pageCount,
              let page = doc.page(at: pageIndex) else {
            return
        }
        if view.currentPage != page {
            view.go(to: page)
        }
    }
}
