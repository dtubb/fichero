import Foundation

/// The cut marks of a line (`segment-editor.cut-marks-editable`): one short mark across the line's baseline where each
/// word after the first begins, which a drag moves (`segment.move_cut`). Points are the page's fractions.
enum CutMarks {
    /// One mark: the two pieces it parts and where it sits on the line's baseline (0 to 1).
    struct Mark: Equatable {
        let firstId: String
        let secondId: String
        let place: Double
    }

    /// The marks between `pieces` (each a segment id with its own baseline), along `lineBaseline`, in reading order.
    static func marks(lineBaseline: [[Double]], pieces: [(id: String, baseline: [[Double]])]) -> [Mark] {
        let placed = pieces.compactMap { piece -> (id: String, start: Double)? in
            guard let first = piece.baseline.first else { return nil }
            return (piece.id, fraction(of: first, along: lineBaseline))
        }.sorted { $0.start < $1.start }
        return zip(placed, placed.dropFirst()).map { Mark(firstId: $0.id, secondId: $1.id, place: $1.start) }
    }

    /// How far along `baseline` (0 to 1, by length) the point nearest `point` lies.
    static func fraction(of point: [Double], along baseline: [[Double]]) -> Double {
        guard baseline.count >= 2, point.count >= 2 else { return 0 }
        let lengths = zip(baseline, baseline.dropFirst()).map { hypot($1[0] - $0[0], $1[1] - $0[1]) }
        let total = lengths.reduce(0, +)
        guard total > 0 else { return 0 }
        var best = (distance: Double.infinity, along: 0.0)
        var walked = 0.0
        for ((start, end), length) in zip(zip(baseline, baseline.dropFirst()), lengths) {
            let step = length > 0
                ? min(max(((point[0] - start[0]) * (end[0] - start[0]) + (point[1] - start[1]) * (end[1] - start[1]))
                    / (length * length), 0), 1)
                : 0
            let near = [start[0] + (end[0] - start[0]) * step, start[1] + (end[1] - start[1]) * step]
            let distance = hypot(point[0] - near[0], point[1] - near[1])
            if distance < best.distance { best = (distance, (walked + step * length) / total) }
            walked += length
        }
        return best.along
    }

    /// The point `place` (0 to 1) of the way along `baseline`.
    static func point(at place: Double, along baseline: [[Double]]) -> [Double] {
        guard let first = baseline.first else { return [0, 0] }
        let lengths = zip(baseline, baseline.dropFirst()).map { hypot($1[0] - $0[0], $1[1] - $0[1]) }
        let target = place * lengths.reduce(0, +)
        var walked = 0.0
        for ((start, end), length) in zip(zip(baseline, baseline.dropFirst()), lengths) where length > 0 {
            if walked + length >= target {
                let step = (target - walked) / length
                return [start[0] + (end[0] - start[0]) * step, start[1] + (end[1] - start[1]) * step]
            }
            walked += length
        }
        return baseline.last ?? first
    }

    /// The mark within `reach` (page fractions) of `point`, nearest first; nil when none is.
    static func mark(near point: [Double], marks: [Mark], lineBaseline: [[Double]], reach: Double) -> Mark? {
        marks.map { ($0, CutMarks.point(at: $0.place, along: lineBaseline)) }
            .map { ($0.0, hypot($0.1[0] - point[0], $0.1[1] - point[1])) }
            .filter { $0.1 <= reach }
            .min { $0.1 < $1.1 }?.0
    }
}
