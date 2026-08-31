import Foundation

/// Snap a dragged markup rect to the WORDS it touches (Daniel, 2026-08-30:
/// "will underline, highlight, strikethrough use the word boundaries?").
///
/// The recognised geometry is the substrate: a drag selects the word boxes it
/// intersects, grouped into one snapped rect per LINE it crosses — so a
/// highlight hugs the text the way it does in any PDF reader, and a
/// multi-line drag yields one strip per line instead of a page-blotting
/// union. A drag touching no words stays a free-form rect (an image margin
/// is annotatable too). Pure, for unit tests.
enum AnnotationWordSnap {
    /// - Parameters:
    ///   - drag: normalized `[x, y, w, h]`.
    ///   - words: word-level boxes (normalized bboxes).
    ///   - lines: line-level boxes; when empty, words group by vertical
    ///     overlap instead.
    /// - Returns: one or more normalized rects, in reading order.
    static func snappedRects(
        drag: [Double], words: [OCRGeometryBox], lines: [OCRGeometryBox]
    ) -> [[Double]] {
        guard drag.count >= 4 else { return [drag] }
        let touched = words.filter { intersects(drag, $0.bbox) }
        guard !touched.isEmpty else { return [drag] }

        var runs: [[[Double]]]
        if lines.isEmpty {
            runs = groupByVerticalOverlap(touched.map(\.bbox))
        } else {
            var byLine: [Int: [[Double]]] = [:]
            var homeless: [[Double]] = []
            for word in touched {
                if let idx = lines.firstIndex(where: { verticalOverlap($0.bbox, word.bbox) > 0.5 }) {
                    byLine[idx, default: []].append(word.bbox)
                } else {
                    homeless.append(word.bbox)
                }
            }
            runs = byLine.sorted { $0.key < $1.key }.map(\.value)
            if !homeless.isEmpty { runs += groupByVerticalOverlap(homeless) }
        }
        return runs.map(union).sorted { $0[1] != $1[1] ? $0[1] < $1[1] : $0[0] < $1[0] }
    }

    static func intersects(_ lhs: [Double], _ rhs: [Double]) -> Bool {
        guard lhs.count >= 4, rhs.count >= 4 else { return false }
        return lhs[0] < rhs[0] + rhs[2] && rhs[0] < lhs[0] + lhs[2]
            && lhs[1] < rhs[1] + rhs[3] && rhs[1] < lhs[1] + lhs[3]
    }

    /// Fraction of the smaller height shared vertically — the "same line" test.
    static func verticalOverlap(_ lhs: [Double], _ rhs: [Double]) -> Double {
        guard lhs.count >= 4, rhs.count >= 4 else { return 0 }
        let top = max(lhs[1], rhs[1])
        let bottom = min(lhs[1] + lhs[3], rhs[1] + rhs[3])
        let overlap = bottom - top
        let minHeight = min(lhs[3], rhs[3])
        guard overlap > 0, minHeight > 0 else { return 0 }
        return overlap / minHeight
    }

    private static func groupByVerticalOverlap(_ boxes: [[Double]]) -> [[[Double]]] {
        var runs: [[[Double]]] = []
        for box in boxes.sorted(by: { $0[1] != $1[1] ? $0[1] < $1[1] : $0[0] < $1[0] }) {
            if var last = runs.last, let anchor = last.first,
               verticalOverlap(anchor, box) > 0.5 {
                last.append(box)
                runs[runs.count - 1] = last
            } else {
                runs.append([box])
            }
        }
        return runs
    }

    private static func union(_ boxes: [[Double]]) -> [Double] {
        let minX = boxes.map { $0[0] }.min() ?? 0
        let minY = boxes.map { $0[1] }.min() ?? 0
        let maxX = boxes.map { $0[0] + $0[2] }.max() ?? 0
        let maxY = boxes.map { $0[1] + $0[3] }.max() ?? 0
        return [minX, minY, maxX - minX, maxY - minY]
    }
}
