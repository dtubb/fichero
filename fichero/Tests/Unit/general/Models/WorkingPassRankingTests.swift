@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// An import has no rank of its own, and Preview draws a pass with shapes (#5443, #5425;
/// `source.pass.working`, `ui.preview.draws-a-pass-with-shapes`).
///
/// The SAME cases as the engine's `tests/unit/api/test_an_import_has_no_rank_of_its_own.py`, so the
/// two halves of the one rule are pinned alike. The Mosquera page (SM_NPQ_C01_005): a TEI import of
/// a Qwen-VL draft, every line `shape: unstated` on a whole-page rect, and a newer Gemini-on-Kraken
/// pass whose lines carry polygons. `rankedPasses` put the import in a tier of its own above every
/// machine pass and did not look for shapes, so Preview drew the import -- nothing -- on 358 of 374
/// pages. If these fail, a file imported once outranks every later run, or the image goes blank.
struct WorkingPassRankingTests {

    private func realPass(id: String, kind: Components.Schemas.ProvenanceKind, ageInHours: Double) -> SegmentPassValue {
        SegmentPassValue(
            id: id, provisional: false, documentId: "page-1", name: id, provenanceKind: kind,
            createdAt: Date(timeIntervalSince1970: 1_000_000 - ageInHours * 3600),
            sourceArtifactId: nil, artifactType: nil
        )
    }

    /// A line of a pass: drawn (a rect and a polygon), or with no place its file stated (`unstated`).
    private func line(_ id: String, pass passId: String, index: Int, unstated: Bool = false) -> Segment {
        var anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1"))
        let top = 0.1 + Double(index) * 0.05
        anchor.rect = unstated ? [0, 0, 1, 1] : [0.1, top, 0.6, 0.04]
        anchor.polygon = unstated ? nil : [[0.1, top], [0.7, top], [0.7, top + 0.04], [0.1, top + 0.04]]
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: passId,
            kind: "line", kindRaw: nil, provenanceKind: unstated ? .externalImport : .workflow,
            anchor: anchor, baseline: nil, text: "line \(index)", confidence: nil, sourceArtifactId: nil,
            boxIndex: index, pageIndex: nil, metadata: unstated ? ["shape": AnyCodable("unstated")] : nil
        )
    }

    /// `source.pass.working` (#5443/#5425): with nobody's choice, the run that landed after the import
    /// is what shows -- no manual promote. Before, the import's own tier put it first for ever.
    @Test("source.pass.working: an import beside a newer machine pass -- the newer is drawn first")
    func anImportBesideANewerMachinePass() {
        let imported = realPass(id: "docx-draft", kind: .externalImport, ageInHours: 48)
        let kraken = realPass(id: "gemini-on-kraken", kind: .workflow, ageInHours: 1)
        let ranked = OCRGeometrySelection.rankedPasses([imported, kraken], segments: [])
        #expect(ranked.map(\.id) == ["gemini-on-kraken", "docx-draft"])
    }

    /// `source.pass.working`: a person's live choice always wins, over a newer run and an import.
    @Test("source.pass.working: a person's choice beats both the import and the newer run")
    func aPersonsChoiceBeatsBoth() {
        var imported = realPass(id: "docx-draft", kind: .externalImport, ageInHours: 48)
        imported.working = true
        imported.workingBasis = "chosen"
        let kraken = realPass(id: "gemini-on-kraken", kind: .workflow, ageInHours: 1)
        let older = realPass(id: "apple-vision", kind: .workflow, ageInHours: 72)
        let ranked = OCRGeometrySelection.rankedPasses([kraken, older, imported], segments: [])
        #expect(ranked.map(\.id) == ["docx-draft", "gemini-on-kraken", "apple-vision"])
    }

    /// `ui.preview.draws-a-pass-with-shapes`: the import a person chose is the TEXT, but it has no
    /// shapes, so the boxes come from the best-ranked pass that has them. Before, the chosen import
    /// won the drawing too and the image was blank.
    @Test("ui.preview.draws-a-pass-with-shapes: a geometry-free winner yields boxes from the best pass with shapes")
    func aGeometryFreeWinnerYieldsBoxesFromTheBestPassWithShapes() throws {
        var imported = realPass(id: "docx-draft", kind: .externalImport, ageInHours: 48)
        imported.working = true
        imported.workingBasis = "chosen"
        let kraken = realPass(id: "gemini-on-kraken", kind: .workflow, ageInHours: 1)
        let segments = [
            line("d0", pass: "docx-draft", index: 0, unstated: true),
            line("d1", pass: "docx-draft", index: 1, unstated: true),
            line("k0", pass: "gemini-on-kraken", index: 0),
            line("k1", pass: "gemini-on-kraken", index: 1)
        ]
        let ranked = OCRGeometrySelection.rankedPasses([imported, kraken], segments: segments)
        #expect(ranked.map(\.id) == ["gemini-on-kraken", "docx-draft"])
        let drawn = try #require(SegmentDisplay.winningPass(passes: [imported, kraken], segments: segments))
        #expect(drawn.pass.id == "gemini-on-kraken")
        #expect(drawn.geometry.boxes.count == 2)
    }

    /// A shapeless pass is moved behind the passes with shapes, never dropped: on a text-only page
    /// (a TEI edition with no facsimile, its only pass) it is still the pass whose lines the Reader
    /// and the Order list select, as before this change.
    @Test("ui.preview.draws-a-pass-with-shapes: a text-only page's only pass is still the one selected")
    func aTextOnlyPagesOnlyPassIsStillSelected() {
        var imported = realPass(id: "papyrus-tei", kind: .externalImport, ageInHours: 48)
        imported.working = true
        imported.workingBasis = "newest-machine-unchosen"
        let segments = [line("p0", pass: "papyrus-tei", index: 0, unstated: true)]
        #expect(SegmentDisplay.winningPass(passes: [imported], segments: segments)?.pass.id == "papyrus-tei")
    }

    /// A pass whose segments the caller does not hold is not judged shapeless: absence of the
    /// segments is not evidence of absence of shapes (the same rule as `isKnownEmpty`).
    @Test("ui.preview.draws-a-pass-with-shapes: a pass with no segments in hand is still ranked")
    func aPassWithNoSegmentsInHandIsStillRanked() {
        let kraken = realPass(id: "gemini-on-kraken", kind: .workflow, ageInHours: 1)
        #expect(OCRGeometrySelection.rankedPasses([kraken], segments: []).map(\.id) == ["gemini-on-kraken"])
    }

    /// The exception ruled 2026-10-04: an outside edit arriving through a synced folder is the
    /// NEWEST pass, and still never becomes working until a person chooses it. The app cannot tell an
    /// outside edit from any other import (`PassRead` carries no actor), which is why it takes the
    /// engine's working pass first rather than re-deriving the ladder.
    @Test("source.pass.working: a synced-folder outside edit does not win")
    func aSyncedFolderOutsideEditDoesNotWin() {
        var kraken = realPass(id: "gemini-on-kraken", kind: .workflow, ageInHours: 1)
        kraken.working = true
        kraken.workingBasis = "newest-machine-unchosen"
        let outside = realPass(id: "edited-outside", kind: .externalImport, ageInHours: 0)
        let ranked = OCRGeometrySelection.rankedPasses([outside, kraken], segments: [])
        #expect(ranked.first?.id == "gemini-on-kraken")
    }
}
