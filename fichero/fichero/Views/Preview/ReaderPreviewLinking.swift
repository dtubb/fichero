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

/// Post a reader selection change — the shared producer for every reader
/// surface (PageContentPane, DocumentTextReader). Sends offsets, the owning
/// document, and the SELECTED TEXT: the text is the cross-document anchor.
@MainActor
func postReaderSelection(_ range: Range<Int>?, documentId: String?, content: String) {
    var info: [String: Any] = ["documentId": documentId ?? ""]
    if let range, !range.isEmpty {
        info["charStart"] = range.lowerBound
        info["charEnd"] = range.upperBound
        let utf16 = Array(content.utf16)
        if range.lowerBound >= 0, range.upperBound <= utf16.count,
           let text = String(utf16CodeUnits: Array(utf16[range]), count: range.count) as String? {
            info["text"] = text
        }
    }
    NotificationCenter.default.post(name: .readerTextSelection, object: nil, userInfo: info)
}

/// Locate `selectedText` inside the geometry's own transcript and return the
/// UTF-16 range there — the anchor when the reader's document is NOT the
/// previewed one (an entry's reader over its source page). First occurrence,
/// case- and diacritic-insensitive; nil for empty or unfindable text — no
/// highlight beats a guessed one.
func geometryRange(of selectedText: String, in geometryText: String) -> Range<Int>? {
    let trimmed = selectedText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.count >= 3,
          let found = geometryText.range(
              of: trimmed, options: [.caseInsensitive, .diacriticInsensitive]
          ) else { return nil }
    let start = geometryText.utf16.distance(
        from: geometryText.utf16.startIndex,
        to: found.lowerBound.samePosition(in: geometryText.utf16) ?? geometryText.utf16.startIndex
    )
    let length = geometryText[found].utf16.count
    return start..<(start + length)
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
