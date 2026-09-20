@testable import Fichero
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import Testing

/// source-model App slice A stage 1 (#4954): `Segment`/`SegmentPass`/
/// `SourceAnchorValue` are the app's hand-written draw-side mirrors of the
/// generated `SegmentRead`/`PassRead`/`SourceAnchorOutput`. Behaviour:
/// `source.app.one-segment-store` (one shape, whichever store it came from —
/// the mapping is what makes that promise honest).
struct SegmentMappingTests {

    // MARK: - Coverage: the generated type's own field set, not guessed

    /// Same idiom as `DocumentEqualityTests`' `Mirror`-based coverage check:
    /// if the generated `SegmentRead` gains a field, this set grows and the
    /// test fails, naming exactly what `Segment.init(generated:)` (and this
    /// test) have not yet accounted for.
    @Test("SegmentRead's generated field set is exactly what Segment.init(generated:) maps")
    func segmentReadFieldCoverage() {
        let generated = Components.Schemas.SegmentRead(
            id: "s1", provisional: true, documentId: "doc-1", passId: "legacy:a1",
            kind: "line", kindRaw: "textline", provenanceKind: .human,
            anchor: Components.Schemas.SourceAnchorOutput(documentId: "doc-1"),
            baseline: [[0, 0]], text: "hi", confidence: 0.9,
            sourceArtifactId: "a1", boxIndex: 0, pageIndex: 0, metadata: nil
        )
        let mapped = Set(Mirror(reflecting: generated).children.compactMap(\.label))
        let accounted: Set<String> = [
            "id", "provisional", "documentId", "passId", "kind", "kindRaw",
            "provenanceKind", "anchor", "baseline", "text", "confidence",
            "sourceArtifactId", "boxIndex", "pageIndex", "metadata"
        ]
        #expect(
            mapped == accounted,
            "SegmentRead's fields changed. Unaccounted: \(mapped.subtracting(accounted).sorted()). Update Segment.init(generated:) and this set together."
        )
    }

    @Test("SourceAnchorOutput's generated field set is exactly what SourceAnchorValue.init(generated:) maps or deliberately drops")
    func sourceAnchorOutputFieldCoverage() {
        let generated = Components.Schemas.SourceAnchorOutput(documentId: "doc-1")
        let mapped = Set(Mirror(reflecting: generated).children.compactMap(\.label))
        // `refines` and `additionalProperties` are DELIBERATELY dropped — see
        // `SourceAnchorValue.init(generated:)`'s own doc comment for why.
        let accounted: Set<String> = [
            "documentId", "pageId", "renditionId", "space", "rect", "polygon",
            "rotation", "charStart", "charEnd", "granularity", "refines",
            "additionalProperties"
        ]
        #expect(
            mapped == accounted,
            "SourceAnchorOutput's fields changed. Unaccounted: \(mapped.subtracting(accounted).sorted())."
        )
    }

    @Test("PassRead's generated field set is exactly what SegmentPass.init(generated:) maps")
    func passReadFieldCoverage() {
        let generated = Components.Schemas.PassRead(
            id: "legacy:a1", provisional: true, documentId: "doc-1", name: "transcription",
            provenanceKind: .workflow, provider: "sonnet-5.1", model: "claude", runId: "r1",
            createdAt: Date(), text: "the pass's own result text",
            sourceArtifactId: "a1", artifactType: "transcription"
        )
        let mapped = Set(Mirror(reflecting: generated).children.compactMap(\.label))
        let accounted: Set<String> = [
            "id", "provisional", "documentId", "name", "provenanceKind",
            "provider", "model", "runId", "createdAt", "text", "sourceArtifactId", "artifactType"
        ]
        #expect(mapped == accounted, "PassRead's fields changed. Unaccounted: \(mapped.subtracting(accounted).sorted()).")
    }

    /// `PassRead.text` (slice 1b, 77aa741c3) — the pass's own result text,
    /// which char spans on a box will index into once stage 2 stops
    /// rebuilding `OCRGeometry.text` by joining box texts. Mapped here,
    /// not yet READ anywhere in `SegmentDisplay`.
    @Test("SegmentPass.init(generated:) carries PassRead.text through")
    func passMappingKeepsText() {
        let generated = Components.Schemas.PassRead(
            id: "legacy:a1", provisional: true, documentId: "doc-1", name: "transcription",
            provenanceKind: .workflow, text: "the pass's own result text"
        )
        #expect(SegmentPass(generated: generated).text == "the pass's own result text")
    }

    // MARK: - The mapping itself keeps every value, not just every key

    @Test("Segment.init(generated:) carries every field's VALUE through, not just its presence")
    func segmentMappingKeepsValues() throws {
        let anchor = Components.Schemas.SourceAnchorOutput(
            documentId: "doc-1", renditionId: "r9", rect: [0.1, 0.2, 0.3, 0.4],
            charStart: 5, charEnd: 9, granularity: "line"
        )
        let metadata = try Components.Schemas.SegmentRead.MetadataPayload(
            additionalProperties: OpenAPIObjectContainer(unvalidatedValue: [
                "raw_polygon_px": "[[1,2],[3,4]]",
                "geometry_problem": "polygon_px could not be normalized"
            ])
        )
        let generated = Components.Schemas.SegmentRead(
            id: "legacy:a1:0", provisional: true, documentId: "doc-1", passId: "legacy:a1",
            kind: "line", kindRaw: "textline",
            provenanceKind: Components.Schemas.ProvenanceKind.human, anchor: anchor,
            baseline: [[0.0, 0.5], [1.0, 0.5]], text: "hola", confidence: 0.87,
            sourceArtifactId: "a1", boxIndex: 3, pageIndex: 1, metadata: metadata
        )

        let segment = Segment(generated: generated)

        #expect(segment.id == "legacy:a1:0")
        #expect(segment.provisional)
        #expect(segment.documentId == "doc-1")
        #expect(segment.passId == "legacy:a1")
        #expect(segment.kind == "line")
        #expect(segment.kindRaw == "textline")
        #expect(segment.provenanceKind == Components.Schemas.ProvenanceKind.human)
        #expect(segment.isHandCurated)
        #expect(segment.anchor.documentId == "doc-1")
        #expect(segment.anchor.renditionId == "r9")
        #expect(segment.anchor.rect == [0.1, 0.2, 0.3, 0.4])
        #expect(segment.anchor.charStart == 5)
        #expect(segment.anchor.charEnd == 9)
        #expect(segment.anchor.granularity == "line")
        #expect(segment.baseline == [[0.0, 0.5], [1.0, 0.5]])
        #expect(segment.text == "hola")
        #expect(segment.confidence == 0.87)
        #expect(segment.sourceArtifactId == "a1")
        #expect(segment.boxIndex == 3)
        // Mapped, not yet READ (slice 1b, 77aa741c3) — SegmentDisplay still
        // sets pageIndex: nil on every box it draws; using this to filter a
        // PDF page's boxes is stage 2.
        #expect(segment.pageIndex == 1)
        let rawPolygon: String? = segment.metadata?["raw_polygon_px"]?.value as? String
        #expect(rawPolygon == "[[1,2],[3,4]]")
        let geometryProblem: String? = segment.metadata?["geometry_problem"]?.value as? String
        #expect(geometryProblem == "polygon_px could not be normalized")
    }

    @Test("a segment with provenanceKind other than human is NOT hand-curated")
    func nonHumanProvenanceIsNotHandCurated() {
        let generated = Components.Schemas.SegmentRead(
            id: "s1", provisional: true, documentId: "doc-1", passId: "legacy:a1",
            kind: "word", provenanceKind: .workflow,
            anchor: Components.Schemas.SourceAnchorOutput(documentId: "doc-1")
        )
        #expect(!Segment(generated: generated).isHandCurated)
    }

    // MARK: - Degenerate geometry (unset rect, never invented) — the update's own gap

    @Test("a segment with no rect maps with anchor.rect == nil, never a synthesized rect")
    func unsetRectStaysUnset() {
        let anchor = Components.Schemas.SourceAnchorOutput(documentId: "doc-1", rect: nil)
        let generated = Components.Schemas.SegmentRead(
            id: "legacy:a1:2", provisional: true, documentId: "doc-1", passId: "legacy:a1",
            kind: "word", provenanceKind: .unknown, anchor: anchor
        )
        #expect(Segment(generated: generated).anchor.rect == nil)
    }
}
