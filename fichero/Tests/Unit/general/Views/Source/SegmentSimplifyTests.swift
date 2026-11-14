@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.vertices`. Simplify sends the whole
/// selection as one `segment.simplify`, with the versions read and a tolerance in image pixels, so it is one undo and
/// means the same on every page. What breaks without these: a simplify per segment, or a tolerance read as a fraction
/// of the page that flattens every line.
@MainActor
@Suite(.tags(.paleography))
struct SegmentSimplifyTests {
    private func line(_ id: String, version: Int?) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0, 0.2, 1, 0.05])
        )
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    @Test("the selection is one segment.simplify, with versions and a tolerance in pixels")
    func oneCall() throws {
        let call = try SegmentEdit.simplify([line("a", version: 2), line("b", version: 5)]).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.simplify")
        #expect(params["segment_ids"] as? [String] == ["a", "b"])
        #expect(params["expected_versions"] as? [String: Int] == ["a": 2, "b": 5])
        #expect(params["tolerance"] as? Double == SegmentEdit.simplifyTolerance)
        #expect(SegmentEdit.simplifyTolerance >= 1, "pixels, not a fraction of the page")
    }

    @Test("nothing selected, or a segment not saved yet, sends nothing")
    func refusals() {
        #expect(SegmentEdit.simplify([]) == .failure(.tooFew))
        #expect(SegmentEdit.simplify([line("a", version: nil)]) == .failure(.versionUnknown))
    }
}

/// Spec: `segment-editor.cut-words-from-positions`. Cut Words sends the selected lines as one `segment.cut_words` with
/// their versions; a line with no baseline is refused before anything is sent, and the page says how many lines the
/// engine could not cut. What breaks without these: a cut per line, or lines silently left whole.
@MainActor
@Suite(.tags(.paleography))
struct CutWordsTests {
    private func line(_ id: String, version: Int?, baseline: [[Double]]? = [[0.1, 0.3], [0.9, 0.3]]) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0.1, 0.2, 0.8, 0.1])
        )
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: baseline, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    @Test("the selected lines are one segment.cut_words with their versions")
    func oneCall() throws {
        let call = try SegmentEdit.cutWords([line("a", version: 1), line("b", version: 3)]).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.cut_words")
        #expect(params["segment_ids"] as? [String] == ["a", "b"])
        #expect(params["expected_versions"] as? [String: Int] == ["a": 1, "b": 3])
    }

    @Test("a line with no baseline is refused; the notice says how many lines were not cut, and nothing when all were")
    func refusalsAndNotice() {
        #expect(SegmentEdit.cutWords([line("a", version: 1, baseline: nil)]) == .failure(.noBaseline))
        #expect(SegmentEdit.cutWords([]) == .failure(.tooFew))
        #expect(SegmentEdit.cutWordsNotice(made: 9, leftAlone: 0) == nil)
        #expect(SegmentEdit.cutWordsNotice(made: 3, leftAlone: 2)?.contains("2 lines") == true)
    }
    @Test("the slider shows the engine's shapes while held and, let go, asks for ONE simplify at its tolerance")
    func theSlider() throws {
        let window = WindowState(libraryId: UUID())
        window.simplifyTolerance = 4
        window.simplifyPreview = [[[0, 0], [1, 1]]]
        window.letGoOfSimplifySlider(at: 4)
        #expect(window.simplifyTolerance == nil)
        #expect(window.simplifyPreview.isEmpty, "the live shapes go when the slider is let go")
        let first = try #require(window.simplifyRelease)
        #expect(first.tolerance == 4)
        window.letGoOfSimplifySlider(at: 4)
        #expect(window.simplifyRelease != first, "the same tolerance let go twice is two releases")

        let call = try SegmentEdit.simplify([line("a", version: 2)], tolerance: 4).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(params["tolerance"] as? Double == 4)
    }

    @Test("the preview's outlines are drawn closed, its baselines open, and an unchanged shape not at all")
    func thePreviewPaths() {
        let paths = SimplifyRelease.paths(
            polygons: [[[0, 0], [1, 0], [1, 1]], nil], baselines: [nil, [[0, 0.5], [1, 0.5]]]
        )
        #expect(paths == [[[0, 0], [1, 0], [1, 1], [0, 0]], [[0, 0.5], [1, 0.5]]])
    }
    /// `segment-editor.cut-characters`: Cut Characters sends the selected WORDS, with their versions, as one call.
    @Test("Cut Characters is one segment.cut_characters on the selected words alone")
    func cutCharacters() throws {
        var word = line("w", version: 4)
        word.kind = "word"
        let call = try SegmentEdit.cutCharacters([line("l", version: 1), word]).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.cut_characters")
        #expect(params["segment_ids"] as? [String] == ["w"])
        #expect(params["expected_versions"] as? [String: Int] == ["w": 4])
        #expect(SegmentEdit.cutCharacters([line("l", version: 1)]) == .failure(.tooFew))
    }
}
