#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import PDFKit
import SwiftUI

/// Renders a thumbnail of a PDF page locally using PDFKit.
/// - For a PDF file itself: renders page 0 (first page).
/// - For a page Document (child of a PDF): renders the specific page.
///   Pass `pageIndex = sequence - 1` (PDFKit is 0-indexed, our sequence is 1-based).
/// Used as a fallback when the backend hasn't generated a PDF thumbnail.
struct PDFThumbnailView: View {
    let documentId: String
    let size: CGSize
    var pageIndex: Int = 0

    @Environment(StorageService.self) private var storageService
    @State private var image: PlatformImage?
    @State private var pageCount: Int = 0

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            Group {
                if let image {
                    Image(platformImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                } else {
                    // ★ EVERY FRAME PERFECT (#3616): a sized skeleton at the
                    // surface color instead of a bare icon while PDFKit renders,
                    // cross-fading to the page image below (ties #3210).
                    SkeletonPlaceholder(cornerRadius: 4)
                }
            }
            .animation(FrameAnimation.crossfade, value: image == nil)
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
        .task(id: "\(documentId):\(pageIndex)") {
            // Shared source bytes (#3209): reuse the already-downloaded PDF
            // instead of a per-thumbnail download; decode stays off-main.
            guard let data = try? await storageService.pdfCache.data(for: documentId) else {
                image = nil
                pageCount = 0
                return
            }
            let result = await Self.renderThumbnailWithPageCount(
                from: data, pageIndex: pageIndex, size: size
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
                .font(.system(.caption2, weight: .medium))
            Text("\(pageCount)")
                .font(.system(.caption2, weight: .semibold))
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
    ///
    /// `nonisolated` is LOAD-BEARING, and was also the only thing making the
    /// line above TRUE: a static on a `View` inherits the type's MainActor
    /// isolation under the macOS 26 SDK, so without it this hopped back to the
    /// main actor, and the Swift Testing suite calling it off-main SIGTRAPped
    /// the whole test process (#4201).
    nonisolated static func renderThumbnail(from data: Data, pageIndex: Int = 0, size: CGSize) async -> PlatformImage? {
        await renderThumbnailWithPageCount(
            from: data, pageIndex: pageIndex, size: size
        )?.image
    }

    /// Render the page AND surface the PDF's total page count so the
    /// multi-page badge can render without a second document load.
    /// One \`PDFDocument(data:)\` call serves both — half the cost of
    /// computing them independently. (#946)
    /// `nonisolated` transitively with `renderThumbnail`, which awaits it: a
    /// MainActor callee would drag the caller back on-main (#4201).
    nonisolated static func renderThumbnailWithPageCount(
        from data: Data, pageIndex: Int = 0, size: CGSize
    ) async -> (image: PlatformImage, pageCount: Int)? {
        await Task.detached(priority: .userInitiated) {
            guard let pdf = PDFDocument(data: data),
                  pageIndex >= 0, pageIndex < pdf.pageCount,
                  let page = pdf.page(at: pageIndex) else {
                return nil
            }
            let image = page.thumbnail(of: size, for: .mediaBox)
            return (image, pdf.pageCount)
        }.value
    }
}
