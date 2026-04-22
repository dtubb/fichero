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

/// Interactive PDF preview using PDFKit's `PDFView`.
///
/// Where `PDFThumbnailView` renders a flat `NSImage` (cheap, cacheable, fine
/// for grid/sidebar thumbnails), `PDFPageView` uses the full AppKit `PDFView`
/// so users get **selectable text, copy, find, and links** — everything a real
/// PDF reader provides. Used in the main preview pane for `.page` documents
/// (#578) and for top-level `.file`+`.pdf` documents.
///
/// Always uses `.singlePage` mode (#595): the page is the canonical unit.
/// Horizontal trackpad swipe navigates to the next/previous page when the
/// document is at fit-scale; when zoomed in, swipe pans normally.
struct PDFPageView: NSViewRepresentable {
    let path: String
    let pageIndex: Int
    /// Fires when the user swipes to a different page.
    /// The index is 0-based into the PDF document.
    var onPageIndexChange: ((Int) -> Void)?

    func makeCoordinator() -> Coordinator {
        Coordinator(owner: self)
    }

    func makeNSView(context: Context) -> PDFView {
        let view = PDFView()
        view.displayMode = .singlePage
        view.displaysPageBreaks = false
        // #588: autoScales re-fits the document to the pane on every layout
        // pass, which silently undoes user pinch-zoom. We keep autoScales=true
        // only long enough for PDFKit to compute the initial fit; the scale
        // observer below flips it off the first time scaleFactor changes.
        view.autoScales = true
        view.backgroundColor = NSColor(red: 253/255, green: 253/255, blue: 253/255, alpha: 1)
        view.delegate = context.coordinator
        context.coordinator.pdfView = view
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.pageDidChange(_:)),
            name: .PDFViewPageChanged,
            object: view
        )
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.scaleDidChange(_:)),
            name: .PDFViewScaleChanged,
            object: view
        )
        // Horizontal pan at fit-scale = page turn (#595).
        let pan = NSPanGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handlePan(_:))
        )
        pan.delegate = context.coordinator
        view.addGestureRecognizer(pan)
        loadAndNavigate(view)
        return view
    }

    func updateNSView(_ view: PDFView, context: Context) {
        context.coordinator.owner = self
        loadAndNavigate(view)
    }

    static func dismantleNSView(_ view: PDFView, coordinator: Coordinator) {
        NotificationCenter.default.removeObserver(coordinator)
    }

    /// Load the PDF document (if not already loaded) and navigate to the
    /// requested page. Only replaces `document` when the path actually changes
    /// — re-assigning the same document resets the user's zoom/selection state.
    private func loadAndNavigate(_ view: PDFView) {
        let fileURL = URL(fileURLWithPath: path)
        if view.document?.documentURL != fileURL {
            // #588: re-engage autoScales for the new document's initial fit.
            view.autoScales = true
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

    /// Bridges AppKit notifications / delegate into the SwiftUI callback.
    final class Coordinator: NSObject, PDFViewDelegate, NSGestureRecognizerDelegate {
        var owner: PDFPageView
        weak var pdfView: PDFView?
        // Accumulated horizontal translation for the current pan gesture.
        private var panAccumulated: CGFloat = 0

        init(owner: PDFPageView) {
            self.owner = owner
        }

        @objc
        func pageDidChange(_ notification: Notification) {
            guard let view = notification.object as? PDFView,
                  let page = view.currentPage,
                  let doc = view.document else { return }
            let index = doc.index(for: page)
            guard index != owner.pageIndex else { return }
            // PDFViewPageChanged is always posted on the main thread.
            owner.onPageIndexChange?(index)
        }

        /// #588: PDFKit's `autoScales` keeps re-fitting the document to the
        /// pane on every layout pass, which undoes user pinch-zoom. The first
        /// scale change disables autoScales so the current `scaleFactor`
        /// sticks through subsequent resizes and layout passes.
        @objc
        func scaleDidChange(_ notification: Notification) {
            guard let view = notification.object as? PDFView else { return }
            view.autoScales = false
        }

        /// Horizontal pan at fit-scale turns pages; at zoom-in PDFKit pans normally.
        /// A 60pt horizontal threshold prevents accidental flips on small swipes.
        @objc
        func handlePan(_ recognizer: NSPanGestureRecognizer) {
            guard let view = pdfView else { return }
            let fitScale = view.scaleFactorForSizeToFit
            // Only intercept when not meaningfully zoomed in (within 10%).
            guard view.scaleFactor <= fitScale * 1.1 else { return }

            let translation = recognizer.translation(in: view)
            switch recognizer.state {
            case .began:
                panAccumulated = 0
            case .changed:
                panAccumulated += translation.x
                recognizer.setTranslation(.zero, in: view)
                if panAccumulated < -60 {
                    panAccumulated = 0
                    view.goToNextPage(nil)
                } else if panAccumulated > 60 {
                    panAccumulated = 0
                    view.goToPreviousPage(nil)
                }
            default:
                panAccumulated = 0
            }
        }

        /// Allow the pan recognizer to coexist with PDFKit's built-in gestures
        /// so pinch-zoom and text selection still work.
        func gestureRecognizer(
            _ gestureRecognizer: NSGestureRecognizer,
            shouldRecognizeSimultaneouslyWith other: NSGestureRecognizer
        ) -> Bool {
            true
        }
    }
}
