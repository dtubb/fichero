import CoreGraphics
import Foundation
import Observation

/// EPHEMERAL marquee selections drawn over the Preview image (Daniel,
/// 2026-08-29): rubber-band rects that exist BEFORE anything is persisted.
///
/// A drawn marquee has two exits, neither of which is drawing it:
/// - "New Region(s)" promotes each marquee to its own persisted region, in
///   reading order — the diary-entry pattern, one entry per box per page.
/// - The workflow bar reads the set as a run SCOPE and runs a tool on just
///   those crops, without ever persisting a node (the bar-side consumption
///   is the selection-scope lane; THIS is the seam it reads).
///
/// Per-window: an instance rides on `WindowState` (`previewMarquees`), the
/// same per-window home as the document-selection scope seams, so two
/// windows' marquees never mix. Esc / click-away clears the set.
@MainActor
@Observable
final class PreviewMarqueeSelection {
    /// The document the marquees were drawn over. Marquees are meaningless on
    /// any other page, so a document switch clears them (see `add`).
    private(set) var documentId: String?

    /// Normalized `[x, y, w, h]` image rects, in DRAW order. Reading order is
    /// a presentation of this list (`readingOrderRects`), not a mutation of
    /// it — the user's draw order stays inspectable.
    private(set) var rects: [[Double]] = []

    /// Human label for the document, so the workflow bar's subject chip can
    /// name the scope without a store lookup (nil falls back to the detail
    /// document's name in the policy).
    private(set) var documentName: String?

    /// The source image's pixel dimensions the rects were measured against —
    /// what lets ▶ denormalize into `image.crop_child`'s pixel coordinates.
    private(set) var imagePixelSize: CGSize?

    /// Marquee picked for individual deletion (click one, press Delete).
    var selectedIndex: Int?

    init() {}

    var isEmpty: Bool { rects.isEmpty }
    var count: Int { rects.count }

    /// Append a marquee. Drawing on a different document abandons the old
    /// set — stale rects over a new page would be plausible and wrong.
    func add(
        _ rect: [Double], documentId: String,
        documentName: String? = nil, imagePixelSize: CGSize? = nil
    ) {
        if self.documentId != documentId {
            rects = []
            selectedIndex = nil
            self.documentId = documentId
        }
        if let documentName { self.documentName = documentName }
        if let imagePixelSize { self.imagePixelSize = imagePixelSize }
        rects.append(rect)
    }

    func removeSelected() {
        guard let index = selectedIndex, rects.indices.contains(index) else { return }
        rects.remove(at: index)
        selectedIndex = nil
        if rects.isEmpty { documentId = nil; documentName = nil; imagePixelSize = nil }
    }

    func clear() {
        documentId = nil
        documentName = nil
        imagePixelSize = nil
        rects = []
        selectedIndex = nil
    }

    /// The set in reading order: top-to-bottom, then left-to-right — the
    /// order promotion creates one region per marquee in.
    var readingOrderRects: [[Double]] {
        Self.readingOrder(rects)
    }

    /// Pure and static so the ordering rule is unit-testable without a view.
    static func readingOrder(_ rects: [[Double]]) -> [[Double]] {
        rects.filter { $0.count >= 4 }.sorted {
            $0[1] != $1[1] ? $0[1] < $1[1] : $0[0] < $1[0]
        }
    }

    /// Reading-order rects as CGRects — what the workflow bar's scope ladder
    /// and ▶-press materialization consume (each rect its own crop child).
    var readingOrderCGRects: [CGRect] {
        readingOrderRects.map {
            CGRect(x: $0[0], y: $0[1], width: $0[2], height: $0[3])
        }
    }

    /// The scope's identity rect for the policy snapshot: the first marquee
    /// in reading order. The RUN acts on the whole set; this only labels it.
    var firstReadingOrderRect: CGRect? { readingOrderCGRects.first }
}
