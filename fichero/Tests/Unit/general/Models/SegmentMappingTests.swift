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
        // `refines` is the ONLY deliberate drop now — a recursive anchor
        // pointing at another anchor, which `segment_from_box` never sets for a
        // segment. `shapes` and `media_ref` moved from dropped to MAPPED with
        // #5050 (a faithful type is foundation; see
        // `SourceAnchorValue.init(generated:)`), and `segment_id` /
        // `representation_id` are slice 8's lasting references (#4932).
        //
        // THIS TEST CAUGHT SLICE 8 and did its job: it compares by equality, so
        // the contract gaining `segment_id` and `representation_id` failed it
        // until they were accounted for here. The anchor's `extra="allow"`
        // catch-all is still dropped and still absent from this set, because it
        // is `additionalProperties` rather than a declared property.
        let accounted: Set<String> = [
            "document_id", "page_id", "rendition_id", "space", "rect", "polygon",
            "rotation", "char_start", "char_end", "granularity", "refines",
            "shapes", "media_ref", "segment_id", "representation_id"
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
    /// Slice 8's `segment_id` / `representation_id` join them for the same
    /// reason.
    @Test("the contract reader sees slice 7's and slice 8's new anchor fields")
    func theReaderSeesTheNewAnchorFields() throws {
        let declared = try Self.contractProperties(of: "SourceAnchor-Output")
        #expect(declared.isSuperset(of: ["shapes", "media_ref"]))
        #expect(declared.isSuperset(of: ["segment_id", "representation_id"]))
    }

    // MARK: - #5050: the type is TOTAL over the contract's declared fields
    //
    // Round trips, not renderings. Each asserts that a shape SURVIVES the wire
    // mapping with its own values — the property a subset type could not have,
    // and the reason a renderer is not the right proof of a faithful type.

    /// A helper shaped like the engine's own answer, so each test below names
    /// only what it is about.
    private func anchor(
        rect: [Double]? = nil,
        polygon: [[Double]]? = nil,
        shapes: [Components.Schemas.AnchorShape]? = nil,
        mediaRef: String? = nil,
        segmentId: String? = nil,
        representationId: String? = nil
    ) -> Components.Schemas.SourceAnchorOutput {
        Components.Schemas.SourceAnchorOutput(
            documentId: "doc-1", rect: rect, polygon: polygon,
            shapes: shapes, mediaRef: mediaRef,
            segmentId: segmentId, representationId: representationId
        )
    }

    @Test("a polygon shape survives the mapping with its points intact")
    func aPolygonShapeSurvives() throws {
        let triangle: [[Double]] = [[0.1, 0.1], [0.4, 0.1], [0.25, 0.5]]
        let value = SourceAnchorValue(generated: anchor(
            rect: [0.1, 0.1, 0.3, 0.4],
            shapes: [.init(kind: .polygon, points: triangle)]
        ))

        #expect(value.shapes?.count == 1)
        #expect(value.shapes?.first?.kind == .polygon)
        #expect(value.shapes?.first?.points == triangle)
        // The engine's bound still rides along, so a rectangle-only surface is
        // unaffected by the type having become honest.
        #expect(value.rect == [0.1, 0.1, 0.3, 0.4])
    }

    @Test("a point survives and does NOT become a rect")
    func aPointStaysAPoint() throws {
        let value = SourceAnchorValue(generated: anchor(
            shapes: [.init(kind: .point, points: [[0.42, 0.67]])]
        ))

        #expect(value.shapes?.first?.kind == .point)
        #expect(value.shapes?.first?.points == [[0.42, 0.67]])
        // A point has no area, so the engine leaves `rect` unset and nothing
        // here may invent one: an invented zero-size rect is a thing a surface
        // would try to draw.
        #expect(value.rect == nil)
    }

    @Test("an open path keeps its two points and stays a path")
    func aPathStaysAPath() throws {
        let value = SourceAnchorValue(generated: anchor(
            shapes: [.init(kind: .path, points: [[0.1, 0.5], [0.9, 0.55]])]
        ))
        #expect(value.shapes?.first?.kind == .path)
        #expect(value.shapes?.first?.points?.count == 2)
    }

    @Test("a time span survives with its media reference and no points")
    func aTimeSpanSurvives() throws {
        let value = SourceAnchorValue(generated: anchor(
            shapes: [.init(kind: .time, tStart: 12.5, tEnd: 19.25)],
            mediaRef: "rec-7"
        ))

        #expect(value.shapes?.first?.kind == .time)
        #expect(value.shapes?.first?.tStart == 12.5)
        #expect(value.shapes?.first?.tEnd == 19.25)
        #expect(value.shapes?.first?.points == nil)
        #expect(value.mediaRef == "rec-7")
        #expect(value.rect == nil, "a time shape has no box at all")
    }

    @Test("several shapes at once all survive, in order")
    func severalShapesSurvive() throws {
        let value = SourceAnchorValue(generated: anchor(
            rect: [0.1, 0.1, 0.8, 0.6],
            shapes: [
                .init(kind: .polygon, points: [[0.1, 0.1], [0.4, 0.1], [0.25, 0.3]]),
                .init(kind: .polygon, points: [[0.5, 0.4], [0.9, 0.4], [0.7, 0.7]])
            ]
        ))
        #expect(value.shapes?.count == 2)
        #expect(value.shapes?[0].points?.first == [0.1, 0.1])
        #expect(value.shapes?[1].points?.first == [0.5, 0.4])
    }

    @Test("a degenerate bound does not silently acquire a drawable rectangle")
    func aDegenerateBoundStaysUndrawable() throws {
        // The engine drops a rect it cannot hold rather than inventing one
        // (`_build_anchor`), so the app's job is to carry the absence.
        let value = SourceAnchorValue(generated: anchor(
            shapes: [.init(kind: .point, points: [[0.0, 0.0]])]
        ))
        #expect(value.rect == nil)
        #expect(value.polygon == nil)
    }

    @Test("an anchor with no shapes maps exactly as it did before #5050")
    func anAnchorWithNoShapesIsUnchanged() throws {
        let value = SourceAnchorValue(generated: anchor(
            rect: [0.2, 0.3, 0.4, 0.1], polygon: [[0.2, 0.3], [0.6, 0.3], [0.4, 0.4]]
        ))

        #expect(value.shapes == nil)
        #expect(value.mediaRef == nil)
        #expect(value.segmentId == nil)
        #expect(value.representationId == nil)
        // The no-regression case: every field that worked before still does.
        #expect(value.rect == [0.2, 0.3, 0.4, 0.1])
        #expect(value.polygon == [[0.2, 0.3], [0.6, 0.3], [0.4, 0.4]])
        #expect(value.documentId == "doc-1")
    }

    /// #5058: what ACTUALLY happens to a kind the app has never heard of.
    ///
    /// `everyShapeKindSurvives` above cannot answer this — it enumerates the
    /// five known cases, so it passes whether `kind` is a string or an enum.
    /// This feeds an unknown kind through the REAL generated decoder, which is
    /// the layer that decides, and pins the answer.
    ///
    /// The answer is that the whole payload fails to decode, and that is worth
    /// knowing rather than discovering: a page carrying one unrecognised shape
    /// shows NOTHING, not "everything except that shape". `AnchorShapeKind` is
    /// `@frozen` with no unknown case because its contract calls it a closed
    /// set, so this is the contract's own chosen behaviour — but if a sixth
    /// kind is ever added, this test is where the cost of that decision is
    /// written down.
    @Test("the decoder refuses an unknown shape kind, and the whole payload fails")
    func theDecoderRefusesAnUnknownShapeKind() throws {
        let known = Data(#"{"kind":"polygon","points":[[0.1,0.1],[0.4,0.1],[0.2,0.5]]}"#.utf8)
        let unknown = Data(#"{"kind":"spiral","points":[[0.1,0.1]]}"#.utf8)

        // The known kind decodes, so this test is about the KIND and not about
        // the payload's shape.
        let shape = try JSONDecoder().decode(Components.Schemas.AnchorShape.self, from: known)
        #expect(shape.kind == .polygon)

        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(Components.Schemas.AnchorShape.self, from: unknown)
        }
    }

    @Test("a polygon and a DIFFERENT rect both survive; neither collapses into the other")
    func aPolygonIsNotReplacedByItsBoundingBox() throws {
        // THE SILENT LOSS THIS GUARDS: a polygon that comes back as its
        // bounding box looks perfectly fine on screen — a box is drawn, in
        // roughly the right place — and the shape a person actually drew is
        // gone. So the rect here is deliberately NOT the triangle's bound: if
        // either field were derived from the other, one of these two
        // expectations has to fail.
        let triangle: [[Double]] = [[0.10, 0.10], [0.40, 0.10], [0.25, 0.50]]
        let unrelatedRect: [Double] = [0.60, 0.70, 0.20, 0.10]
        let value = SourceAnchorValue(generated: anchor(
            rect: unrelatedRect,
            polygon: triangle,
            shapes: [.init(kind: .polygon, points: triangle)]
        ))

        #expect(value.polygon == triangle, "the polygon was replaced by a box")
        #expect(value.rect == unrelatedRect, "the rect was replaced by the polygon's bound")
        #expect(value.shapes?.first?.points == triangle)
        // And the three are genuinely distinct, so this test cannot pass by
        // everything happening to be equal.
        #expect(value.polygon?.count == 3)
        #expect(value.rect?.count == 4)
    }

    @Test("a rect-kind shape survives even though nothing special-cases it")
    func aRectKindShapeSurvives() throws {
        // `rect` is the one shape kind that duplicates information already in
        // `rect` itself. A mapping that "helpfully" skipped it would be a
        // catch-all by omission.
        let value = SourceAnchorValue(generated: anchor(
            rect: [0.1, 0.2, 0.3, 0.4],
            shapes: [.init(kind: .rect, points: [[0.1, 0.2], [0.4, 0.6]])]
        ))
        #expect(value.shapes?.count == 1)
        #expect(value.shapes?.first?.kind == .rect)
        #expect(value.shapes?.first?.points?.count == 2)
    }

    @Test("every shape kind the engine can send survives the mapping")
    func everyShapeKindSurvives() throws {
        // TOTALITY, asserted over the generated enum's OWN case list rather
        // than a list written here: `AnchorShapeKind` is `CaseIterable`, so if
        // the engine gains a sixth kind this test covers it the moment the
        // contract is regenerated — it cannot fall out of date. The app does
        // not render most of these; surviving the trip is the property.
        for kind in Components.Schemas.AnchorShapeKind.allCases {
            let value = SourceAnchorValue(generated: anchor(
                shapes: [.init(kind: kind, points: [[0.2, 0.3]], tStart: 1, tEnd: 2)]
            ))
            #expect(
                value.shapes?.first?.kind == kind,
                "shape kind \(kind.rawValue) did not survive the mapping"
            )
            #expect(value.shapes?.first?.points == [[0.2, 0.3]])
        }
    }

    @Test("the value type round-trips through Codable without losing the new fields")
    func theValueTypeRoundTripsThroughCodable() throws {
        // A one-way mapping test proves the wire decode; this proves the app's
        // OWN type does not lose the fields when it is encoded and decoded —
        // which is what happens wherever a `SourceAnchorValue` is cached or
        // persisted app-side. A field added to the struct but missing from a
        // hand-written `CodingKeys` would pass every test above and fail here.
        let triangle: [[Double]] = [[0.1, 0.1], [0.4, 0.1], [0.25, 0.5]]
        let original = SourceAnchorValue(generated: anchor(
            rect: [0.6, 0.7, 0.2, 0.1],
            polygon: triangle,
            shapes: [
                .init(kind: .polygon, points: triangle),
                .init(kind: .time, tStart: 3.5, tEnd: 9.25)
            ],
            mediaRef: "rec-3",
            segmentId: "seg-9",
            representationId: "rep-4"
        ))

        let decoded = try JSONDecoder().decode(
            SourceAnchorValue.self, from: JSONEncoder().encode(original)
        )

        #expect(decoded == original, "the app's own type lost something in a round trip")
        #expect(decoded.shapes?.count == 2)
        #expect(decoded.shapes?[0].points == triangle)
        #expect(decoded.shapes?[1].tStart == 3.5)
        #expect(decoded.mediaRef == "rec-3")
        #expect(decoded.segmentId == "seg-9")
        #expect(decoded.representationId == "rep-4")
        #expect(decoded.polygon == triangle)
    }

    @Test("the lasting references survive, by value")
    func theLastingReferencesSurvive() throws {
        let value = SourceAnchorValue(generated: anchor(
            segmentId: "seg-42", representationId: "rep-7"
        ))
        // Distinct values, so a transposed mapping fails by value rather than
        // passing because both happened to be non-nil.
        #expect(value.segmentId == "seg-42")
        #expect(value.representationId == "rep-7")
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
