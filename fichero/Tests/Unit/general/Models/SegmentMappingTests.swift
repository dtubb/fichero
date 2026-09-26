@testable import Fichero
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import Testing

/// source-model App slice A stage 1 (#4954): `Segment`/`SegmentPassValue`/
/// `SourceAnchorValue` are the app's hand-written draw-side mirrors of the
/// generated `SegmentRead`/`PassRead`/`SourceAnchorOutput`. Behaviour:
/// `source.app.one-segment-store` (one shape, whichever store it came from —
/// the mapping is what makes that promise honest).
struct SegmentMappingTests {

    // MARK: - Coverage: the CONTRACT's own field set, not guessed

    /// Thrown rather than returning an empty set: a guard that cannot read
    /// what it guards must FAIL, not pass quietly. An empty set would make
    /// every comparison below vacuously true, which is the shape #4365 became
    /// -- a suite no gate could see was skipped.
    private struct ContractUnreadable: Error, CustomStringConvertible {
        let schema: String
        let url: URL

        var description: String {
            """
            SegmentMappingTests: BLIND — no properties for schema '\(schema)'.
              read from: \(url.path)
            The coverage guards below compare against this set, so an empty \
            one would pass them all while guarding nothing.
            """
        }
    }

    /// The property names the CONTRACT declares for one schema.
    ///
    /// WHY NOT `Mirror` (2026-09-26, slice 7 / #4925). These three guards
    /// used `Mirror(reflecting:).children` to read the generated struct's
    /// field set. Slice 7 took `SourceAnchor-Output` from eleven properties
    /// to thirteen, swift-openapi-generator crossed its size threshold and
    /// switched the struct to copy-on-write STORAGE INDIRECTION — every field
    /// became a computed property over one stored `storage`. `Mirror`
    /// enumerates only STORED properties, so it returned `["storage"]` and
    /// the technique was defeated by a schema simply growing. Any of these
    /// three schemas can cross that threshold next.
    ///
    /// So ask the contract instead of the struct. This reads the very
    /// `openapi.json` the generated client is built FROM, which is the
    /// question these guards were always meant to ask: "what does the wire
    /// declare, and has the mapping accounted for all of it?" It cannot be
    /// defeated by a codegen strategy, and — unlike encoding a value and
    /// reading its keys — it does not depend on a field being non-nil to be
    /// seen, so a new OPTIONAL field still fails the guard.
    private static func contractProperties(of schema: String) throws -> Set<String> {
        // `sibling` rather than a `deletingLastPathComponent()` chain: that
        // chain is the exact thing `AppSource.sibling` was added to stop, and
        // it names `fichero-api-client` as the example.
        //
        // There is only ONE `openapi.json` in the package, and both
        // generations of the client — Xcode's build-tool plugin and SwiftPM's
        // — are produced from it. So this reads the single source of truth,
        // which is also why it is sounder than reading generated Swift.
        //
        // Same idiom as `DocumentConverterFieldSourceTests.typedDocumentKeys`
        // and `WorkflowStreamConnectionTests`. That one is private and fixed
        // to `Document`; this one takes the schema name. If a third appears,
        // move THIS one onto `AppSource` and re-point both — one resolver
        // with two shapes, as that file's own note puts it.
        let url = try AppSource.sibling("fichero-api-client")
            .appendingPathComponent("Sources/FicheroAPIClient/openapi.json")
        let root = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        let schemas = (root?["components"] as? [String: Any])?["schemas"] as? [String: Any]
        let properties = (schemas?[schema] as? [String: Any])?["properties"] as? [String: Any] ?? [:]
        let names = Set(properties.keys)
        if names.isEmpty { throw ContractUnreadable(schema: schema, url: url) }
        return names
    }

    /// If the contract's `SegmentRead` gains a field, this set no longer
    /// matches and the test names exactly what `Segment.init(generated:)`
    /// (and this set) have not yet accounted for.
    @Test("SegmentRead's contract field set is exactly what Segment.init(generated:) maps")
    func segmentReadFieldCoverage() throws {
        let declared = try Self.contractProperties(of: "SegmentRead")
        let accounted: Set<String> = [
            "id", "provisional", "document_id", "pass_id", "kind", "kind_raw",
            "provenance_kind", "anchor", "baseline", "text", "confidence",
            "source_artifact_id", "box_index", "page_index", "metadata"
        ]
        #expect(
            declared == accounted,
            "SegmentRead's fields changed. Unaccounted: \(declared.subtracting(accounted).sorted()). Update Segment.init(generated:) and this set together."
        )
    }

    @Test("SourceAnchor-Output's contract field set is exactly what SourceAnchorValue.init(generated:) maps or deliberately drops")
    func sourceAnchorOutputFieldCoverage() throws {
        let declared = try Self.contractProperties(of: "SourceAnchor-Output")
        // `refines`, `shapes` and `media_ref` are DELIBERATELY dropped — see
        // `SourceAnchorValue.init(generated:)`'s own doc comment for each
        // reason. The anchor's `extra="allow"` catch-all is dropped too, but
        // it is not listed here because it is not a declared PROPERTY: it is
        // `additionalProperties` on the schema, and the contract is what this
        // set is compared against.
        let accounted: Set<String> = [
            "document_id", "page_id", "rendition_id", "space", "rect", "polygon",
            "rotation", "char_start", "char_end", "granularity", "refines",
            "shapes", "media_ref"
        ]
        #expect(
            declared == accounted,
            "SourceAnchor-Output's fields changed. Unaccounted: \(declared.subtracting(accounted).sorted())."
        )
    }

    @Test("PassRead's contract field set is exactly what SegmentPassValue.init(generated:) maps")
    func passReadFieldCoverage() throws {
        let declared = try Self.contractProperties(of: "PassRead")
        let accounted: Set<String> = [
            "id", "provisional", "document_id", "name", "provenance_kind",
            "provider", "model", "run_id", "created_at", "text",
            "source_artifact_id", "artifact_type"
        ]
        #expect(declared == accounted, "PassRead's fields changed. Unaccounted: \(declared.subtracting(accounted).sorted()).")
    }

    /// The reader is not blind to the very fields that defeated the old
    /// technique. `shapes` and `media_ref` are slice 7's additions to the
    /// anchor, and a guard that could not see them is precisely the failure
    /// this rewrite exists to prevent — so it is asserted, not assumed.
    @Test("the contract reader sees slice 7's new anchor fields")
    func theReaderSeesTheNewAnchorFields() throws {
        let declared = try Self.contractProperties(of: "SourceAnchor-Output")
        #expect(declared.isSuperset(of: ["shapes", "media_ref"]))
    }

    /// The `PassRead` analogue of `segmentMappingKeepsValues` below (test
    /// audit F20): the field-coverage test above proves the NAME set
    /// matches; this proves every one of those twelve names actually
    /// routes to the right property, each with a value distinct from every
    /// other field's, so an unmapped or transposed field fails BY VALUE —
    /// not just by a list this test itself maintains.
    @Test("SegmentPassValue.init(generated:) carries every PassRead field's VALUE through, not just its presence")
    func passMappingKeepsAllValues() {
        let createdAt = Date(timeIntervalSince1970: 1_700_000_000)
        let generated = Components.Schemas.PassRead(
            id: "legacy:a1", provisional: true, documentId: "doc-1", name: "transcription",
            provenanceKind: .workflow, provider: "anthropic", model: "sonnet-5.1", runId: "run-7",
            createdAt: createdAt, text: "the pass's own result text",
            sourceArtifactId: "art-9", artifactType: "text_geometry"
        )
        let pass = SegmentPassValue(generated: generated)
        #expect(pass.id == "legacy:a1")
        #expect(pass.provisional)
        #expect(pass.documentId == "doc-1")
        #expect(pass.name == "transcription")
        #expect(pass.provenanceKind == Components.Schemas.ProvenanceKind.workflow)
        #expect(pass.provider == "anthropic")
        #expect(pass.model == "sonnet-5.1")
        #expect(pass.runId == "run-7")
        #expect(pass.createdAt == createdAt)
        #expect(pass.text == "the pass's own result text")
        #expect(pass.sourceArtifactId == "art-9")
        #expect(pass.artifactType == "text_geometry")
    }

    // MARK: - The mapping itself keeps every value, not just every key

    @Test("Segment.init(generated:) carries every field's VALUE through, not just its presence")
    func segmentMappingKeepsValues() throws {
        // Every anchor field the coverage test above says IS mapped
        // (documentId/pageId/renditionId/space/rect/polygon/rotation/
        // charStart/charEnd/granularity — refines/additionalProperties are
        // the DELIBERATE drops, tested separately) gets its own distinct
        // value here, per F20: a name in the coverage set with no value
        // asserted here can silently go unmapped.
        let anchor = Components.Schemas.SourceAnchorOutput(
            documentId: "doc-1", pageId: "page-4", renditionId: "r9",
            space: .normalized, rect: [0.1, 0.2, 0.3, 0.4],
            polygon: [[0.1, 0.2], [0.3, 0.4]], rotation: 90,
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
        #expect(segment.anchor.pageId == "page-4")
        #expect(segment.anchor.renditionId == "r9")
        #expect(segment.anchor.space == "normalized")
        #expect(segment.anchor.rect == [0.1, 0.2, 0.3, 0.4])
        #expect(segment.anchor.polygon == [[0.1, 0.2], [0.3, 0.4]])
        #expect(segment.anchor.rotation == 90)
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
