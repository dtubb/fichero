import Foundation

/// Pure helpers for rendering saved annotations as text highlights (#2458).
///
/// Kept separate from the views so the offset/bounds logic is unit-testable
/// without a running text view.
enum AnnotationHighlight {
    /// The valid, in-bounds UTF-16 highlight ranges for the char-span
    /// annotations on a page, given the rendered content length.
    ///
    /// Annotations without a usable span, or whose span falls outside the
    /// current content, are skipped — graceful degradation so a stale offset
    /// from an edited page never crashes or mis-highlights. Ranges are returned
    /// sorted by start so overlapping draws are deterministic.
    static func ranges(
        for annotations: [DocumentAnnotation],
        inUTF16Count count: Int
    ) -> [Range<Int>] {
        annotations
            .compactMap { annotation -> Range<Int>? in
                guard let start = annotation.charStart, let end = annotation.charEnd,
                      start >= 0, end > start, end <= count else { return nil }
                return start..<end
            }
            .sorted { $0.lowerBound < $1.lowerBound }
    }
}
