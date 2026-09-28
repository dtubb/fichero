@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #5152: move, delete and Join on an imported page as the audited segment actions. What breaks
/// without these: an edit sent with no version (so it can overwrite somebody's newer change), a moved
/// box whose outline stays behind, or a Join that keeps a segment nobody picked first.
struct SegmentEditTests {
    private func segment(_ id: String, version: Int?, rect: [Double], polygon: [[Double]]? = nil) -> Segment {
        var anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: rect))
        anchor.polygon = polygon
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    private func json(_ call: SegmentEdit.Call) throws -> [String: Any] {
        let data = try JSONEncoder().encode(call.params)
        return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    @Test("a move sends segment.update with the version read, and the outline moves with the box")
    func moveCarriesVersionAndShiftsTheOutline() throws {
        let line = segment("l1", version: 3, rect: [0.1, 0.2, 0.5, 0.05],
                           polygon: [[0.1, 0.2], [0.6, 0.2], [0.6, 0.25], [0.1, 0.25]])
        let call = try SegmentEdit.move(line, to: [0.15, 0.3, 0.5, 0.05]).get()
        #expect(call.action == "segment.update")
        let params = try json(call)
        #expect(params["segment_id"] as? String == "l1")
        #expect(params["expected_version"] as? Int == 3)
        let anchor = try #require(params["anchor"] as? [String: Any])
        #expect(anchor["rect"] as? [Double] == [0.15, 0.3, 0.5, 0.05])
        let polygon = try #require(anchor["polygon"] as? [[Double]])
        #expect(abs(polygon[0][0] - 0.15) < 1e-12 && abs(polygon[0][1] - 0.3) < 1e-12)
        #expect(abs(polygon[2][0] - 0.65) < 1e-12 && abs(polygon[2][1] - 0.35) < 1e-12)
        #expect(anchor["document_id"] as? String == "page-1")
    }

    @Test("a move shifts every extra shape with the box, never leaving one behind (it was refused before)")
    func moveShiftsExtraShapesToo() throws {
        var line = segment("l1", version: 2, rect: [0.1, 0.2, 0.5, 0.05])
        line.anchor.shapes = [AnchorShapeValue(generated: Components.Schemas.AnchorShape(kind: .point, points: [[0.3, 0.22]]))]
        let anchor = try #require(try json(SegmentEdit.move(line, to: [0.2, 0.3, 0.5, 0.05]).get())["anchor"] as? [String: Any])
        let shapes = try #require(anchor["shapes"] as? [[String: Any]])
        let point = try #require((shapes.first?["points"] as? [[Double]])?.first)
        #expect(shapes.first?["kind"] as? String == "point")
        #expect(abs(point[0] - 0.4) < 1e-12 && abs(point[1] - 0.32) < 1e-12)
    }

    @Test("Join sends segment.merge keeping the first picked, every id with its version")
    func joinKeepsTheFirstPicked() throws {
        let call = try SegmentEdit.join([
            segment("l2", version: 1, rect: [0, 0.3, 1, 0.05]), segment("l1", version: 2, rect: [0, 0.2, 1, 0.05])
        ]).get()
        #expect(call.action == "segment.merge")
        let params = try json(call)
        #expect(params["segment_ids"] as? [String] == ["l2", "l1"])
        #expect(params["keep_id"] as? String == "l2")
        #expect(params["expected_versions"] as? [String: Int] == ["l2": 1, "l1": 2])
    }

    @Test("delete sends segment.delete with each version")
    func deleteCarriesVersions() throws {
        let call = try SegmentEdit.delete([segment("l1", version: 5, rect: [0, 0, 1, 1])]).get()
        #expect(call.action == "segment.delete")
        #expect(try json(call)["expected_versions"] as? [String: Int] == ["l1": 5])
    }

    @Test("nothing is sent without a version, for Join with one segment, or for delete with none")
    func refusals() {
        #expect(SegmentEdit.move(segment("p", version: nil, rect: [0, 0, 1, 1]), to: [0, 0, 1, 1]) == .failure(.versionUnknown))
        #expect(SegmentEdit.join([segment("l1", version: 1, rect: [0, 0, 1, 1])]) == .failure(.tooFew))
        #expect(SegmentEdit.delete([]) == .failure(.tooFew))
        #expect(SegmentEdit.join([
            segment("l1", version: 1, rect: [0, 0, 1, 1]), segment("p", version: nil, rect: [0, 0, 1, 1])
        ]) == .failure(.versionUnknown))
    }

    @Test("the Segment menu sets one fact on every selected segment in ONE update_many, each with its version")
    func setIsOneCallForTheWholeSelection() throws {
        let call = try SegmentEdit.set(.direction("rtl"), on: [
            segment("l1", version: 2, rect: [0, 0, 1, 0.1]), segment("l2", version: 5, rect: [0, 0.1, 1, 0.1])
        ]).get()
        #expect(call.action == "segment.update_many")
        let updates = try #require(try json(call)["updates"] as? [[String: Any]])
        #expect(updates.count == 2)
        #expect(updates[0]["segment_id"] as? String == "l1" && updates[0]["expected_version"] as? Int == 2)
        #expect(updates[1]["segment_id"] as? String == "l2" && updates[1]["expected_version"] as? Int == 5)
        #expect(updates.allSatisfy { $0["direction"] as? String == "rtl" })
        // Only the fact being set is sent: an absent key is "unchanged", a null would be "clear it".
        #expect(updates.allSatisfy { Set($0.keys) == ["segment_id", "expected_version", "direction"] })
    }

    @Test("the Segment menu sends nothing for an empty selection or a segment with no version")
    func setRefusals() {
        #expect(SegmentEdit.set(.kind("line"), on: []) == .failure(.tooFew))
        #expect(SegmentEdit.set(.furniture(true), on: [segment("p", version: nil, rect: [0, 0, 1, 1])]) == .failure(.versionUnknown))
    }
}
