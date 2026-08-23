import Foundation

// MARK: - Reader ↔ preview word linking (Daniel, 2026-08-23: "ideally, we
// could click on a word in the reader and have it highlight into the preview.
// or select multiple in reader and ditto")

extension Notification.Name {
    /// Posted by the reader when its text selection changes. userInfo:
    /// `documentId` (String) and, unless the selection cleared, `charStart` /
    /// `charEnd` (Int, UTF-16 offsets into the displayed transcript — the
    /// same space OCRGeometryBox.charStart/charEnd index).
    static let readerTextSelection = Notification.Name("readerTextSelection")
}

/// The word boxes whose character spans intersect the reader's selection.
/// Interval overlap, not containment: selecting half a word still lights it —
/// a reader selects by meaning, and the box either shows or it doesn't.
/// File scope so Swift Testing exercises it off-main.
func wordBoxes(intersecting range: Range<Int>, in geometry: OCRGeometry) -> [[Double]] {
    guard !range.isEmpty else { return [] }
    return geometry.wordBoxes.compactMap { box in
        guard let start = box.charStart, let end = box.charEnd, end > start else { return nil }
        return (start < range.upperBound && end > range.lowerBound) ? box.bbox : nil
    }
}
