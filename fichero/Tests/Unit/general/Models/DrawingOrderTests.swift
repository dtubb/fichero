@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `SegmentDisplay.drawingOrder`: the ONE order the Preview tries a page's passes in (#5467). The engine's
/// working pass comes first; below it -- until the segments route serves a rank of its own -- a person's
/// pass, then every other real pass newest first, then a legacy result's geometry by its type, and a
/// shapeless pass behind every pass with shapes. Moved here with its cases from `OCRGeometrySelectionTests`
/// when the app's other ladders (the artifact path's `ranked`, the inspector-focus override) were deleted.
/// Behaviour: `source.app.curated-pass-stays-on-top`, `source.app.overlays-draw-from-the-seam`.
struct DrawingOrderTests {

    /// The type the importer writes for a PDF's own text layer is one a legacy pass is drawn from, ahead of
    /// a transcription (#4418: the overlay once asked only for "transcription" and drew nothing).
    @Test("the PDF's own text layer and transcription are drawable legacy types, the layer first")
    func theTextLayerAndTranscriptionAreDrawable() {
        let types = SegmentDisplay.geometryBearingTypes
        #expect(types.contains("transcription"))
        #expect(types.firstIndex(of: "text_geometry")! < types.firstIndex(of: "transcription")!)
    }

    // MARK: - The order over passes (`SegmentPassValue`)

    private func pass(
        id: String,
        type: String,
        ageInHours: Double?,
        humanCurated: Bool = false
    ) -> SegmentPassValue {
        SegmentPassValue(
            id: id, provisional: true, documentId: "page-1", name: type,
            provenanceKind: humanCurated ? .human : .workflow,
            provider: nil, model: nil, runId: nil,
            createdAt: ageInHours.map { Date(timeIntervalSince1970: 1_000_000 - $0 * 3600) },
            text: nil, sourceArtifactId: id, artifactType: type
        )
    }

    /// A segment whose only job is to prove per-segment curation — see
    /// `SegmentMappingTests` for the field-mapping coverage this fixture
    /// deliberately does not repeat.
    private func segment(passId: String, humanCurated: Bool) -> Segment {
        Segment(
            id: "\(passId)-seg", provisional: true, documentId: "page-1", passId: passId,
            kind: "word", kindRaw: nil, provenanceKind: humanCurated ? .human : .workflow,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1")),
            baseline: nil, text: nil, confidence: nil, sourceArtifactId: nil,
            boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("drawingOrder: authority beats recency, over the legacy types")
    func drawingOrderAuthorityBeatsRecency() {
        let ranked = SegmentDisplay.drawingOrder([
            pass(id: "ocr", type: "transcription", ageInHours: 0),
            pass(id: "geo", type: "text_geometry", ageInHours: 100)
        ], segments: [])
        #expect(ranked.first?.id == "geo")
    }

    @Test("drawingOrder: recency breaks ties inside one type")
    func drawingOrderRecencyBreaksTies() {
        let ranked = SegmentDisplay.drawingOrder([
            pass(id: "old", type: "transcription", ageInHours: 10),
            pass(id: "new", type: "transcription", ageInHours: 1)
        ], segments: [])
        #expect(ranked.map(\.id) == ["new", "old"])
    }

    @Test("drawingOrder: a fresh regions pass displaces a stale transcription pass")
    func drawingOrderFreshRegionsDisplacesStaleTranscription() {
        let ranked = SegmentDisplay.drawingOrder([
            pass(id: "ocr-old", type: "transcription", ageInHours: 48),
            pass(id: "regions-new", type: "regions", ageInHours: 0)
        ], segments: [])
        #expect(ranked.map(\.id) == ["regions-new", "ocr-old"])
    }

    @Test("drawingOrder: a hand-curated pass outranks every machine pass, any age")
    func drawingOrderHandCuratedOutranksEverything() {
        let ranked = SegmentDisplay.drawingOrder([
            pass(id: "geo", type: "text_geometry", ageInHours: 0),
            pass(id: "curated", type: "regions", ageInHours: 1000, humanCurated: true)
        ], segments: [])
        #expect(ranked.first?.id == "curated")
    }

    /// The 2026-09-03 defect, restated for the seam (review fix #2): a
    /// person's marquee written INTO an otherwise-machine pass — the common
    /// case — must still outrank a newer pure-machine pass of the same
    /// type, even though the pass's own `provenanceKind` is `.workflow`.
    @Test("drawingOrder: a machine pass carrying one human segment outranks a newer pure machine pass")
    func drawingOrderSegmentCurationOutranksNewerMachinePass() {
        let curatedByBox = pass(id: "machine-with-marquee", type: "regions", ageInHours: 100)
        let newerPureMachine = pass(id: "newer-machine", type: "regions", ageInHours: 1)
        let ranked = SegmentDisplay.drawingOrder(
            [newerPureMachine, curatedByBox],
            segments: [
                segment(passId: "machine-with-marquee", humanCurated: true),
                segment(passId: "newer-machine", humanCurated: false)
            ]
        )
        #expect(ranked.first?.id == "machine-with-marquee")
    }

    @Test("drawingOrder: a pass with no createdAt sorts as the OLDEST in its tier, never crashes")
    func drawingOrderNilCreatedAtSortsOldest() {
        let ranked = SegmentDisplay.drawingOrder([
            pass(id: "known-recent", type: "transcription", ageInHours: 1),
            pass(id: "unknown-time", type: "transcription", ageInHours: nil)
        ], segments: [])
        #expect(ranked.map(\.id) == ["known-recent", "unknown-time"])
    }

    /// NOT a guarantee that a `nil` `artifactType` never reaches the app
    /// (test audit, B2/F-none-numbered, 2026-09-20): today's engine handlers
    /// only ever build a `SegmentPassValue` from a LEGACY artifact, which always
    /// has a type. But `pass_read_from_row` (`models/segments.py:1099`)
    /// returns `artifact_type=None` for a REAL converted-page record, and
    /// #4924 (first-edit conversion) is what starts writing those. This test
    /// pins today's EXCLUSION rule, not the CLAIM that it is harmless — the
    /// day #4924 lands, a real pass with `artifactType == nil` is silently
    /// dropped from the ranking by this same code path, and the first
    /// converted page draws nothing while every test here stays green. The
    /// engine lane is deciding what a real pass should report; this pin must
    /// not be read as proof that case cannot occur.
    ///
    /// **That day came (#5146):** a PAGE or ALTO import writes a real pass with no artifact, and the
    /// maintainer's imported Syriac page drew no boxes. The rule now: only a LEGACY (provisional)
    /// pass is judged by its artifact type, which is what this test still pins; a real pass with no
    /// type is kept -- `drawingOrderKeepsARealPassWithNoArtifactType` below.
    @Test("drawingOrder: a LEGACY pass whose artifactType is nil or unrecognised is excluded, not crashed on")
    func drawingOrderUnrecognisedTypeExcluded() {
        let unknownType = pass(id: "weird", type: "some_future_type", ageInHours: 0)
        let noType = SegmentPassValue(
            id: "no-type", provisional: true, documentId: "page-1", name: "?",
            provenanceKind: .unknown, provider: nil, model: nil, runId: nil,
            createdAt: nil, text: nil, sourceArtifactId: nil, artifactType: nil
        )
        let known = pass(id: "geo", type: "text_geometry", ageInHours: 0)
        let ranked = SegmentDisplay.drawingOrder([unknownType, noType, known], segments: [])
        #expect(ranked.map(\.id) == ["geo"])
    }

    private func realPass(id: String, kind: Components.Schemas.ProvenanceKind, ageInHours: Double) -> SegmentPassValue {
        SegmentPassValue(
            id: id, provisional: false, documentId: "page-1", name: id, provenanceKind: kind,
            createdAt: Date(timeIntervalSince1970: 1_000_000 - ageInHours * 3600),
            sourceArtifactId: nil, artifactType: nil
        )
    }

    /// #5146: the maintainer's imported Syriac page showed its text and no boxes, because the one
    /// pass it had -- written by `format.import`, with no artifact behind it -- was dropped here.
    @Test("drawingOrder: a real pass with no artifactType is KEPT (an imported page draws its boxes)")
    func drawingOrderKeepsARealPassWithNoArtifactType() {
        let imported = realPass(id: "page-xml", kind: .externalImport, ageInHours: 5)
        #expect(SegmentDisplay.drawingOrder([imported], segments: []).map(\.id) == ["page-xml"])
    }

    /// #5122: an imported georeference and an imported transcription were one tier, so the newer
    /// georeference was ranked first and drawn. A georeferencing pass is not ranked at all.
    @Test("drawingOrder: a georeferencing pass is left out, even imported, newer and chosen")
    func drawingOrderLeavesOutGeoreferencing() {
        var georef = realPass(id: "georef", kind: .externalImport, ageInHours: 0)
        georef.transformation = "polynomial-1"
        georef.working = true
        georef.workingBasis = "chosen"
        let transcription = realPass(id: "page-xml", kind: .externalImport, ageInHours: 50)
        #expect(SegmentDisplay.drawingOrder([georef, transcription], segments: []).map(\.id) == ["page-xml"])
    }

    /// Ruled 2026-10-04 (#5443): an import has no rank of its own, so it sits among the passes no
    /// person touched, by date -- here behind the newer machine pass.
    @Test("drawingOrder: hand-curated, then every other pass newest first (an import among them), then legacy")
    func drawingOrderLadder() {
        let ranked = SegmentDisplay.drawingOrder([
            pass(id: "legacy-geo", type: "text_geometry", ageInHours: 0),
            realPass(id: "machine", kind: .workflow, ageInHours: 0),
            realPass(id: "imported", kind: .externalImport, ageInHours: 50),
            realPass(id: "curated", kind: .human, ageInHours: 500)
        ], segments: [])
        #expect(ranked.map(\.id) == ["curated", "machine", "imported", "legacy-geo"])
    }

    /// #5156: a person's explicit choice of working pass outranks the ladder, as the inspector's
    /// focused artifact does. Since #5443 the app takes the ENGINE's working pass first whatever its
    /// basis: the engine works it out by the same ladder (`resolve_working_pass`) plus the one
    /// exception the app cannot see -- an outside edit never wins by itself -- so a pass the engine
    /// marks working by the rule is drawn first too. Two copies of the ladder are how Preview, the
    /// text and the Order tab came to show three different passes of one page.
    @Test("drawingOrder: the engine's working pass comes first, chosen or by the rule")
    func drawingOrderChosenWorkingFirst() {
        var chosen = realPass(id: "machine-chosen", kind: .workflow, ageInHours: 100)
        chosen.working = true
        chosen.workingBasis = "chosen"
        var byRule = realPass(id: "machine-by-rule", kind: .workflow, ageInHours: 0)
        byRule.working = true
        byRule.workingBasis = "newest-machine-unchosen"
        let curated = realPass(id: "curated", kind: .human, ageInHours: 1)
        #expect(SegmentDisplay.drawingOrder([curated, chosen], segments: []).map(\.id) == ["machine-chosen", "curated"])
        #expect(SegmentDisplay.drawingOrder([byRule, curated], segments: []).map(\.id) == ["machine-by-rule", "curated"])
    }
}
