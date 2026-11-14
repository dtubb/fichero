@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.cut-marks-editable`. A line's cut marks sit
/// where each word after the first begins, in reading order; a press near one takes it; letting it go sends ONE
/// `segment.move_cut` with the place along the line's baseline. What breaks without these: a mark drawn where no cut
/// is, a drag that moves the wrong boundary, or a cut sent in screen points.
@MainActor
@Suite(.tags(.paleography))
struct CutMarksTests {
    private let line: [[Double]] = [[0.1, 0.3], [0.9, 0.3]]

    @Test("the marks sit where each word after the first begins, in reading order, whatever order the words came in")
    func marks() {
        let marks = CutMarks.marks(lineBaseline: line, pieces: [
            (id: "nombre", baseline: [[0.5, 0.3], [0.85, 0.3]]),
            (id: "en", baseline: [[0.1, 0.3], [0.2, 0.3]]),
            (id: "el", baseline: [[0.3, 0.3], [0.4, 0.3]])
        ])
        #expect(marks.map(\.firstId) == ["en", "el"])
        #expect(marks.map(\.secondId) == ["el", "nombre"])
        #expect(abs(marks[1].place - 0.5) < 1e-9)
    }

    @Test("a point off the baseline projects onto it; a press near a mark takes that mark and no other")
    func projectionAndPick() {
        #expect(abs(CutMarks.fraction(of: [0.5, 0.35], along: line) - 0.5) < 1e-9)
        #expect(CutMarks.fraction(of: [0.0, 0.3], along: line) == 0)
        let marks = [CutMarks.Mark(firstId: "a", secondId: "b", place: 0.25), CutMarks.Mark(firstId: "b", secondId: "c", place: 0.5)]
        #expect(CutMarks.mark(near: [0.49, 0.31], marks: marks, lineBaseline: line, reach: 0.02)?.secondId == "c")
        #expect(CutMarks.mark(near: [0.4, 0.31], marks: marks, lineBaseline: line, reach: 0.02) == nil)
    }

    @Test("letting a mark go is one segment.move_cut with the two pieces' versions and the place along the line")
    func oneCall() throws {
        let call = try SegmentEdit.moveCut(firstId: "el", secondId: "nombre", place: 0.5, versions: ["el": 2, "nombre": 3]).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.move_cut")
        #expect(params["first_id"] as? String == "el")
        #expect(params["second_id"] as? String == "nombre")
        #expect(params["at"] as? Double == 0.5)
        #expect(params["expected_versions"] as? [String: Int] == ["el": 2, "nombre": 3])
        #expect(SegmentEdit.moveCut(firstId: "el", secondId: "nombre", place: 0.5, versions: ["el": 2]) == .failure(.versionUnknown))
    }
}
