import SwiftUI
#if os(macOS)
import PDFKit
#endif

/// Magnifier loupe overlay for PDF pages.
///
/// Renders a circular magnified region at the cursor position using a cached
/// page thumbnail rendered via PDFKit. Takes a PDF path + page index rather
/// than a live PDFView reference to keep SwiftUI ownership clear.
#if os(macOS)
struct PDFLoupeOverlay: NSViewRepresentable {
    let documentId: String
    let pageIndex: Int
    /// Normalized 0–1 in AppKit coordinates (y = 0 at bottom of view).
    let cursorPosition: CGPoint
    let magnification: CGFloat
    let loupeSize: CGFloat
    @Environment(StorageServiceGenerated.self) private var storageService

    func makeNSView(context: Context) -> PDFLoupeNSView {
        let view = PDFLoupeNSView()
        view.wantsLayer = true
        return view
    }

    func updateNSView(_ nsView: PDFLoupeNSView, context: Context) {
        nsView.documentId = documentId
        nsView.pageIndex = pageIndex
        nsView.cursorPosition = cursorPosition
        nsView.magnification = magnification
        nsView.loupeSize = loupeSize
        nsView.refreshPageImageIfNeeded(storageService: storageService)
        nsView.needsDisplay = true
    }
}

// MARK: - PDFLoupeNSView

final class PDFLoupeNSView: NSView {
    var documentId: String = ""
    var pageIndex: Int = 0
    var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    var magnification: CGFloat = 3.0
    var loupeSize: CGFloat = 150.0

    private var cachedPageImage: NSImage?
    private var cachedKey: String = ""
    private var loadTask: Task<Void, Never>?

    deinit {
        loadTask?.cancel()
    }

    /// Re-renders the page thumbnail only when document or page index changes.
    func refreshPageImageIfNeeded(storageService: StorageServiceGenerated) {
        let key = "\(documentId):\(pageIndex)"
        guard key != cachedKey else { return }
        cachedKey = key
        cachedPageImage = nil
        loadTask?.cancel()
        guard !documentId.isEmpty else { return }
        let documentId = documentId
        let pageIndex = pageIndex
        loadTask = Task { [weak self] in
            guard let self else { return }
            do {
                // Shared source bytes (#3209): the viewer/thumbnails already
                // downloaded this PDF; reuse them instead of a second download.
                // Decode stays off-main (own transient doc) — a PDFDocument can't
                // be rendered off-main while the viewer renders it on main.
                let data = try await storageService.pdfCache.data(for: documentId)
                let image = await Self.renderPageImage(data: data, pageIndex: pageIndex)
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    self.cachedPageImage = image
                    self.needsDisplay = true
                }
            } catch {
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    self.needsDisplay = true
                }
            }
        }
    }

    private static func renderPageImage(data: Data, pageIndex: Int) async -> NSImage? {
        await Task.detached(priority: .userInitiated) {
            guard let doc = PDFDocument(data: data),
                  pageIndex >= 0, pageIndex < doc.pageCount,
                  let page = doc.page(at: pageIndex) else { return nil }
            let pageRect = page.bounds(for: .mediaBox)
            let renderSize = CGSize(width: pageRect.width * 2.0, height: pageRect.height * 2.0)
            return page.thumbnail(of: renderSize, for: .mediaBox)
        }.value
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let pdfImage = cachedPageImage else { return }

        let loupeRadius = loupeSize / 2

        // Loupe center: cursor maps directly to AppKit view coords (y = 0 at bottom, no flip).
        let loupeCenter = CGPoint(
            x: cursorPosition.x * bounds.width,
            y: cursorPosition.y * bounds.height
        )

        // Source region in NSImage coords: NSImage uses y = 0 at top, so flip Y.
        let imageW = pdfImage.size.width
        let imageH = pdfImage.size.height
        let srcW = loupeSize / magnification
        let srcH = loupeSize / magnification
        var srcRect = NSRect(
            x: cursorPosition.x * imageW - srcW / 2,
            y: (1.0 - cursorPosition.y) * imageH - srcH / 2,
            width: srcW,
            height: srcH
        )
        srcRect.origin.x = max(0, min(srcRect.origin.x, imageW - srcW))
        srcRect.origin.y = max(0, min(srcRect.origin.y, imageH - srcH))

        let circleRect = NSRect(
            x: loupeCenter.x - loupeRadius,
            y: loupeCenter.y - loupeRadius,
            width: loupeSize,
            height: loupeSize
        )
        let circlePath = NSBezierPath(ovalIn: circleRect)

        NSGraphicsContext.current?.saveGraphicsState()
        circlePath.addClip()
        pdfImage.draw(in: circleRect, from: srcRect, operation: .copy, fraction: 1.0)
        NSGraphicsContext.current?.restoreGraphicsState()

        // Outline ring
        NSColor.controlAccentColor.withAlphaComponent(0.8).setStroke()
        circlePath.lineWidth = 2.0
        circlePath.stroke()

        // Crosshair at center
        NSColor.controlAccentColor.withAlphaComponent(0.5).setStroke()
        let crosshairPath = NSBezierPath()
        let crossSize: CGFloat = 8
        crosshairPath.move(to: NSPoint(x: loupeCenter.x - crossSize, y: loupeCenter.y))
        crosshairPath.line(to: NSPoint(x: loupeCenter.x + crossSize, y: loupeCenter.y))
        crosshairPath.move(to: NSPoint(x: loupeCenter.x, y: loupeCenter.y - crossSize))
        crosshairPath.line(to: NSPoint(x: loupeCenter.x, y: loupeCenter.y + crossSize))
        crosshairPath.lineWidth = 1.0
        crosshairPath.stroke()
    }
}
#endif

/// iOS placeholder — the macOS PDF loupe uses NSViewRepresentable;
/// an iPad-native loupe belongs in the iPad UI pass.
#if !os(macOS)
struct PDFLoupeOverlay: View {
    let documentId: String
    let pageIndex: Int
    let cursorPosition: CGPoint
    let magnification: CGFloat
    let loupeSize: CGFloat

    var body: some View { Color.clear }
}
#endif
