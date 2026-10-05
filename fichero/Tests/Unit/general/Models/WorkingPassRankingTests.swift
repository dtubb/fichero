@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// An import has no rank of its own, and Preview draws a pass with shapes (#5443, #5425;
/// `source.pass.working`, `ui.preview.draws-a-pass-with-shapes`).
///
/// The Mosquera page (SM_NPQ_C01_005): a TEI import of a Qwen-VL draft, every line `shape: unstated` on a
/// whole-page rect, and a newer Gemini-on-Kraken pass whose lines carry polygons. The app's old ladder put
/// the import in a tier of its own and did not look for shapes, so Preview drew the import -- nothing -- on
/// 358 of 374 pages.
///
/// Rewritten for #5467: the ranking is the engine's alone (`test_an_import_has_no_rank_of_its_own.py`,
/// `test_the_engine_serves_the_drawn_pass.py`), served as `working`, `drawn` and `rank` on each pass. These
/// cases give the app the engine's answer for each state of that page and pin that the app draws exactly
/// what the engine marks, with no ranking of its own laid over it. If these fail, the app re-ranks again.
struct WorkingPassRankingTests {

    /// A real pass as the engine serves it: its kind and age, and the engine's marks.
    private func served(
        _ id: String, kind: Components.Schemas.ProvenanceKind, ageInHours: Double,
        rank: Int?, drawn: Bool = false, basis: String? = nil
    ) -> SegmentPassValue {
        var pass = SegmentPassValue(
            id: id, provisional: false, documentId: "page-1", name: id, provenanceKind: kind,
            createdAt: Date(timeIntervalSince1970: 1_000_000 - ageInHours * 3600),
            sourceArtifactId: nil, artifactType: nil
        )
        pass.rank = rank
        pass.drawn = drawn
        pass.working = rank == 0
        pass.workingBasis = rank == 0 ? (basis ?? "newest-machine-unchosen") : nil
        return pass
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

    private var mosqueraLines: [Segment] {
        [
            line("d0", pass: "docx-draft", index: 0, unstated: true),
            line("d1", pass: "docx-draft", index: 1, unstated: true),
            line("k0", pass: "gemini-on-kraken", index: 0),
            line("k1", pass: "gemini-on-kraken", index: 1)
        ]
    }

    /// `source.pass.working` (#5443/#5425): with nobody's choice, the run that landed after the import is
    /// the working pass and is drawn -- no manual promote.
    @Test("source.pass.working: an import beside a newer machine pass -- the newer is drawn")
    func anImportBesideANewerMachinePass() {
        let imported = served("docx-draft", kind: .externalImport, ageInHours: 48, rank: 1)
        let kraken = served("gemini-on-kraken", kind: .workflow, ageInHours: 1, rank: 0, drawn: true)
        #expect(SegmentDisplay.drawn(passes: [imported, kraken], segments: mosqueraLines)?.passId == "gemini-on-kraken")
    }

    /// `ui.preview.draws-a-pass-with-shapes`: a person chose the shapeless import, so it is the working pass
    /// and the page's TEXT; the engine marks the Kraken pass `drawn`, and Preview draws its boxes.
    @Test("ui.preview.draws-a-pass-with-shapes: a chosen geometry-free pass is the text; the drawn pass is the boxes")
    func aChosenShapelessPassLeavesTheBoxesToTheDrawnPass() throws {
        let imported = served("docx-draft", kind: .externalImport, ageInHours: 48, rank: 0, basis: "chosen")
        let kraken = served("gemini-on-kraken", kind: .workflow, ageInHours: 1, rank: 1, drawn: true)
        let drawn = try #require(SegmentDisplay.drawn(passes: [imported, kraken], segments: mosqueraLines))
        #expect(drawn.passId == "gemini-on-kraken")
        #expect(drawn.geometry.boxes.count == 2)
    }

    /// A text-only page (a TEI edition with no facsimile, its only pass) has no drawn pass; its working pass
    /// is still the one selected, so the Reader and the Order list select its lines.
    @Test("ui.preview.draws-a-pass-with-shapes: a text-only page's only pass is still the one selected")
    func aTextOnlyPagesOnlyPassIsStillSelected() {
        let imported = served("papyrus-tei", kind: .externalImport, ageInHours: 48, rank: 0)
        let segments = [line("p0", pass: "papyrus-tei", index: 0, unstated: true)]
        #expect(SegmentDisplay.drawn(passes: [imported], segments: segments)?.passId == "papyrus-tei")
    }

    /// The exception ruled 2026-10-04: an outside edit through a synced folder is the NEWEST pass and still
    /// never working until a person chooses it. The app cannot tell it from any other import (`PassRead`
    /// carries no actor), which is why it draws the engine's marks and ranks nothing itself.
    @Test("source.pass.working: a synced-folder outside edit does not win")
    func aSyncedFolderOutsideEditDoesNotWin() {
        let kraken = served("gemini-on-kraken", kind: .workflow, ageInHours: 1, rank: 0, drawn: true)
        let outside = served("edited-outside", kind: .externalImport, ageInHours: 0, rank: 1)
        let segments = [line("k0", pass: "gemini-on-kraken", index: 0), line("o0", pass: "edited-outside", index: 0)]
        #expect(SegmentDisplay.drawn(passes: [outside, kraken], segments: segments)?.passId == "gemini-on-kraken")
    }
}
