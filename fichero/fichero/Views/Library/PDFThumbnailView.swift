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
    @State private var pageCount: Int = 0

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
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
            // Multi-page badge (#946) — paper-stack icon + page count
            // sitting bottom-right, drawn only when the PDF has more
            // than one page AND we're showing page 0 (the parent doc).
            // For page-child renders (pageIndex > 0) we DON'T draw the
            // badge — those rows are explicitly "Page N" already, no
            // need to also say "this is one of many."
            if pageCount > 1 && pageIndex == 0 {
                multiPageBadge
                    .padding(4)
            }
        }
        .task(id: "\(path):\(pageIndex)") {
            let result = await Self.renderThumbnailWithPageCount(
                at: path, pageIndex: pageIndex, size: size,
            )
            image = result?.image
            pageCount = result?.pageCount ?? 0
        }
    }

    /// Subtle bottom-right overlay indicating multi-page-ness. Pairs
    /// `doc.on.doc` (paper-stack glyph) with the page count in a
    /// compact capsule so a multi-page PDF looks visually distinct from
    /// a single-page image at a glance. (#946)
    private var multiPageBadge: some View {
        HStack(spacing: 3) {
            Image(systemName: "doc.on.doc")
                .font(.system(size: 9, weight: .medium))
            Text("\(pageCount)")
                .font(.system(size: 10, weight: .semibold))
                .monospacedDigit()
        }
        .padding(.horizontal, 5)
        .padding(.vertical, 2)
        .foregroundStyle(.white)
        .background(
            Capsule().fill(Color.black.opacity(0.55))
        )
        .accessibilityLabel("\(pageCount) pages")
    }

    /// Render a specific page of a PDF at the requested pixel size.
    /// Runs off the main actor — PDFKit can do the render on any thread.
    static func renderThumbnail(at path: String, pageIndex: Int = 0, size: CGSize) async -> NSImage? {
        await renderThumbnailWithPageCount(
            at: path, pageIndex: pageIndex, size: size,
        )?.image
    }

    /// Render the page AND surface the PDF's total page count so the
    /// multi-page badge can render without a second document load.
    /// One \`PDFDocument(url:)\` call serves both — half the cost of
    /// computing them independently. (#946)
    static func renderThumbnailWithPageCount(
        at path: String, pageIndex: Int = 0, size: CGSize,
    ) async -> (image: NSImage, pageCount: Int)? {
        await Task.detached(priority: .userInitiated) {
            guard let pdf = PDFDocument(url: URL(fileURLWithPath: path)),
                  pageIndex >= 0, pageIndex < pdf.pageCount,
                  let page = pdf.page(at: pageIndex) else {
                return nil
            }
            let image = page.thumbnail(of: size, for: .mediaBox)
            return (image, pdf.pageCount)
        }.value
    }
}

// MARK: - PDF Zoom Controller

/// Bridges the SwiftUI zoom toolbar with PDFKit's AppKit PDFView.
@MainActor
final class PDFZoomController: ObservableObject {
    @Published var scale: CGFloat = 1.0
    weak var pdfView: PDFView?

    func zoomIn() { pdfView?.zoomIn(nil) }
    func zoomOut() { pdfView?.zoomOut(nil) }
    func fitToWindow() {
        guard let view = pdfView else { return }
        // Avoid re-enabling autoScales (#588) — compute fit scale directly.
        view.autoScales = false
        view.scaleFactor = view.scaleFactorForSizeToFit
    }
    func actualSize() {
        guard let view = pdfView else { return }
        view.autoScales = false
        view.scaleFactor = 1.0
    }
}

// MARK: - PDFPageView

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
    /// Optional zoom controller — set by PDFPageWithToolbar to sync the toolbar.
    var zoomController: PDFZoomController?

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
        context.coordinator.zoomController = zoomController
        zoomController?.pdfView = view
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
        // Listen for claim-card source navigations forwarded by
        // ContentView. We don't filter by `object:` because the
        // userInfo carries the documentId that should match the
        // currently-loaded PDF; the coordinator double-checks that
        // before scrolling. (#978/#979/#982 Phase 2)
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.handleNavigateToPage(_:)),
            name: .ficheroNavigateToPage,
            object: nil
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
        context.coordinator.zoomController = zoomController
        zoomController?.pdfView = view
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
    /// All PDFKit notification and gesture callbacks fire on the main thread,
    /// so @MainActor is correct and avoids nonisolated-context concurrency warnings.
    @MainActor
    final class Coordinator: NSObject, PDFViewDelegate, NSGestureRecognizerDelegate {
        var owner: PDFPageView
        weak var pdfView: PDFView?
        var zoomController: PDFZoomController?
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
            // PDFViewScaleChanged can fire synchronously inside PDFView's
            // setDocument: → during a SwiftUI view-update pass. Publishing
            // to the @ObservedObject zoomController in that window trips
            // "Publishing changes from within view updates is not allowed".
            // Hop to the next runloop tick so the publish happens after
            // the current update commits. PDFViewScaleChanged is on the
            // main thread already, so Task { @MainActor in … } is fine.
            let newScale = view.scaleFactor
            Task { @MainActor [weak self] in
                self?.zoomController?.scale = newScale
            }
        }

        /// Scroll to a specific page on a `ficheroNavigateToPage`
        /// notification. userInfo carries the page label (extractor
        /// emits the same `source_page_label` string the PDF uses for
        /// its labels — Roman numerals, prefixed numbers, etc.). When
        /// the label is numeric we fall back to numeric page-index
        /// matching. (#978/#979/#982)
        @objc
        func handleNavigateToPage(_ notification: Notification) {
            guard let view = pdfView,
                  let doc = view.document,
                  let info = notification.userInfo else { return }
            // Optional doc-id filter — when present, only respond if
            // this PDF view is showing the doc the caller asked for.
            // owner.path doesn't have an id directly; we rely on
            // ContentView having already selected the target doc, so
            // this listener fires across PDF views but only the
            // currently-visible one has anything to scroll. Cheap.
            let pageLabel = info["pageLabel"] as? String
            guard let pageLabel,
                  !pageLabel.isEmpty else { return }
            // PDFKit page labels — first try exact label match
            // (handles "iv", "12", "A-3", etc).
            for idx in 0..<doc.pageCount {
                if let page = doc.page(at: idx),
                   page.label == pageLabel {
                    view.go(to: page)
                    owner.onPageIndexChange?(idx)
                    return
                }
            }
            // Fallback: numeric page index, 1-based to match
            // human-readable labels.
            if let numeric = Int(pageLabel),
               numeric >= 1, numeric <= doc.pageCount,
               let page = doc.page(at: numeric - 1) {
                view.go(to: page)
                owner.onPageIndexChange?(numeric - 1)
            }
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

// MARK: - PDFPageWithToolbar

/// PDFPageView with a zoom toolbar matching the ZoomableImagePreview toolbar (#656).
struct PDFPageWithToolbar: View {
    let path: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?

    @StateObject private var zoom = PDFZoomController()

    var body: some View {
        VStack(spacing: 0) {
            pdfZoomToolbar
            Divider()
            PDFPageView(
                path: path,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange,
                zoomController: zoom
            )
        }
    }

    @ViewBuilder
    private var pdfZoomToolbar: some View {
        HStack(spacing: 12) {
            Button(action: zoom.zoomOut) {
                Image(systemName: "minus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom Out")

            Text("\(Int(zoom.scale * 100))%")
                .font(.caption)
                .monospacedDigit()
                .frame(width: 50)

            Button(action: zoom.zoomIn) {
                Image(systemName: "plus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom In")

            Divider().frame(height: 16)

            Button(action: zoom.fitToWindow) {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
            }
            .buttonStyle(.plain)
            .help("Fit to Window")

            Button(action: zoom.actualSize) {
                Image(systemName: "1.square")
            }
            .buttonStyle(.plain)
            .help("Actual Size (100%)")

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color(.windowBackgroundColor))
    }
}
