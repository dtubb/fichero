import SwiftUI

#if os(macOS)  // RegionInteractionLayer is Mac-only (an AppKit event layer)

/// A cut mark being dragged: the mark, its line's baseline, and where along it the pointer is now.
struct CutMarkDrag: Equatable {
    let mark: CutMarks.Mark
    let line: [[Double]]
    var place: Double
}

/// The cut marks in Edit Segments (`segment-editor.cut-marks-editable`): a short mark across the baseline where each
/// word of the selection's line begins; dragging one moves the cut, sent once on release (`onMoveCut`).
extension RegionInteractionLayer {
    /// The lines whose marks are shown, each with its baseline and its marks: a selected line's, or a selected word's.
    var shownCutMarks: [(line: [[Double]], marks: [CutMarks.Mark])] {
        guard drawsSegments, onMoveCut != nil, let artifactId, selection.artifactId == artifactId else { return [] }
        let selected = selection.resolvedIndices(in: allBoxes).map { allBoxes[$0] }
        let lineIds = Set(selected.compactMap { box in box.level == "line" ? box.segmentId : box.parentSegmentId })
        return allBoxes.compactMap { line -> (line: [[Double]], marks: [CutMarks.Mark])? in
            guard line.level == "line", let id = line.segmentId, lineIds.contains(id), let baseline = baseline(of: line)
            else { return nil }
            let pieces = allBoxes.compactMap { word -> (id: String, baseline: [[Double]])? in
                guard word.parentSegmentId == id, word.level == "word", let wordId = word.segmentId,
                      let wordBaseline = self.baseline(of: word) else { return nil }
                return (wordId, wordBaseline)
            }
            let marks = CutMarks.marks(lineBaseline: baseline, pieces: pieces)
            return marks.isEmpty ? nil : (baseline, marks)
        }
    }

    private func baseline(of box: OCRGeometryBox) -> [[Double]]? {
        for shape in box.shapes { if case .baseline(let points) = shape, points.count >= 2 { return points } }
        return nil
    }

    /// True when the event belongs to a cut mark's drag (so nothing else acts on it).
    func handleCutMark(_ event: PreviewPointerEvent, in size: CGSize) -> Bool {
        let point = [Double(event.point.x), Double(event.point.y)]
        switch event.phase {
        case .pressed:
            guard event.clickCount == 1, size.width > 0 else { return false }
            let reach = 6 / Double(size.width) * Double(visible.width)
            for shown in shownCutMarks {
                if let mark = CutMarks.mark(near: point, marks: shown.marks, lineBaseline: shown.line, reach: reach) {
                    cutDrag = CutMarkDrag(mark: mark, line: shown.line, place: mark.place)
                    return true
                }
            }
            return false
        case .dragged:
            guard var drag = cutDrag else { return false }
            drag.place = CutMarks.fraction(of: point, along: drag.line)
            cutDrag = drag
            return true
        case .released:
            guard let drag = cutDrag else { return false }
            cutDrag = nil
            if abs(drag.place - drag.mark.place) > 0.002 {
                onMoveCut?(drag.mark.firstId, drag.mark.secondId, drag.place)
            }
            return true
        }
    }

    /// The marks, each a short stroke across its line's baseline; the one being dragged follows the pointer.
    @ViewBuilder
    func liveCutMarks(in size: CGSize) -> some View {
        let shown = shownCutMarks
        if !shown.isEmpty, visible.width > 0, visible.height > 0 {
            Path { path in
                for line in shown {
                    for mark in line.marks {
                        let place = cutDrag?.mark == mark ? cutDrag?.place ?? mark.place : mark.place
                        let foot = CutMarks.point(at: place, along: line.line)
                        let centre = CGPoint(x: (foot[0] - visible.minX) / visible.width * size.width,
                                             y: (foot[1] - visible.minY) / visible.height * size.height)
                        path.move(to: CGPoint(x: centre.x, y: centre.y - 8))
                        path.addLine(to: CGPoint(x: centre.x, y: centre.y + 4))
                    }
                }
            }
            .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 2, lineCap: .round))
            .accessibilityIdentifier("segmentEditor.cutMarks")
        }
    }
}

#endif
