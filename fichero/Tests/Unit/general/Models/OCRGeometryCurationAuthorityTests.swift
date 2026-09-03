@testable import Fichero
import Foundation
import Testing

/// Daniel, 2026-09-03: "I draw a region, switch view, come back and it's
/// gone."
///
/// Drawn regions ARE saved — they land as boxes on a `provider: "user"`
/// artifact the region verbs bootstrap. What loses them is the authority
/// ladder. It ranked hand-drawn regions in the same tier as machine passes
/// and broke ties by recency, so the next transcription or Detect Regions run
/// — newer by definition — permanently masked the boxes their author had just
/// curated. The preview kept the selection alive through `FocusedArtifact`,
/// which is in-memory only: switch away, come back, and the ladder decides
/// again.
///
/// Curation persists and constrains the machine, never the other way round.
struct OCRGeometryCurationAuthorityTests {

    private func artifact(
        id: String,
        type: String,
        ageInHours: Double,
        provider: String? = nil,
        boxCount: Int? = nil
    ) -> Artifact {
        Artifact(
            id: id,
            documentId: "page-1",
            artifactType: type,
            data: boxCount.map { ["box_count": AnyCodable($0)] },
            provider: provider,
            createdAt: Date(timeIntervalSince1970: 1_000_000 - ageInHours * 3600)
        )
    }

    // MARK: - The regression, stated directly

    @Test("a later machine pass cannot mask the regions a person drew")
    func curationOutranksALaterMachinePass() {
        let drawn = artifact(id: "user-regions", type: "regions", ageInHours: 5, provider: "user")
        let rerun = artifact(id: "fresh-ocr", type: "transcription", ageInHours: 0, provider: "vision")
        #expect(OCRGeometrySelection.ranked([rerun, drawn]).first?.id == "user-regions")
    }

    /// `text_geometry` is the file's own text layer and outranks every
    /// ESTIMATE — but it is still a machine pass, and a person who drew on the
    /// page after it meant to.
    @Test("curation outranks even the PDF's own text layer")
    func curationOutranksTheFilesTextLayer() {
        let drawn = artifact(id: "user-regions", type: "regions", ageInHours: 1, provider: "user")
        let layer = artifact(id: "pdf-layer", type: "text_geometry", ageInHours: 9, provider: "pdf")
        #expect(OCRGeometrySelection.ranked([layer, drawn]).first?.id == "user-regions")
    }

    /// Two curated artifacts still break the tie the way every tier does.
    @Test("between two curated artifacts the newest still wins")
    func newestCurationWins() {
        let older = artifact(id: "older", type: "regions", ageInHours: 9, provider: "user")
        let newer = artifact(id: "newer", type: "regions", ageInHours: 1, provider: "user")
        #expect(OCRGeometrySelection.ranked([older, newer]).first?.id == "newer")
    }

    // MARK: - The rules it must not break

    /// A curated artifact the producer already marked empty is still empty:
    /// authority is not a reason to draw nothing.
    @Test("an empty curated artifact is still skipped")
    func emptyCurationIsStillSkipped() {
        let empty = artifact(
            id: "empty-user", type: "regions", ageInHours: 1, provider: "user", boxCount: 0
        )
        let real = artifact(id: "ocr", type: "transcription", ageInHours: 5, provider: "vision")
        let ranked = OCRGeometrySelection.ranked([empty, real])
        #expect(ranked.map(\.id) == ["ocr"])
    }

    /// The machine tiers are untouched: the file's own text layer still beats
    /// an estimate, and among estimates the newest still wins (2026-08-25).
    @Test("the machine ladder is unchanged when nothing was curated")
    func machineLadderIsUnchanged() {
        let layer = artifact(id: "layer", type: "text_geometry", ageInHours: 9, provider: "pdf")
        let stale = artifact(id: "stale", type: "transcription", ageInHours: 9, provider: "vision")
        let fresh = artifact(id: "fresh", type: "regions", ageInHours: 1, provider: "vision")
        #expect(OCRGeometrySelection.ranked([stale, fresh, layer]).map(\.id)
            == ["layer", "fresh", "stale"])
    }

    /// An artifact with no provider at all is a machine artifact, not a
    /// curated one — absence is not evidence of authorship.
    @Test("a provider-less artifact does not claim curation authority")
    func missingProviderIsNotCuration() {
        #expect(!OCRGeometrySelection.isHandCurated(
            artifact(id: "a", type: "regions", ageInHours: 1)
        ))
    }

    @Test("the user provider is recognised regardless of case")
    func userProviderIsCaseInsensitive() {
        #expect(OCRGeometrySelection.isHandCurated(
            artifact(id: "a", type: "regions", ageInHours: 1, provider: "User")
        ))
    }
}
