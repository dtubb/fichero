import Foundation

/// Which artifact supplies the page-geometry overlay (#4418).
///
/// Two defects meet here.
///
/// **The identifier.** The overlay asked for `type: "transcription"`; the
/// import path writes `artifact_type = "text_geometry"`. Two green commits and
/// a dead feature, because `artifact_type` is a bare `str` in the OpenAPI
/// schema — from the contract's point of view every string is valid, so nothing
/// in the toolchain could object. The durable fix is a declared enum in the
/// schema (backend lane); until then the vocabulary lives HERE, in one list, so
/// adopting the generated enum is a rename of two literals rather than a
/// rework. Deliberately NOT added to `Artifact.ArtifactType`: that enum is a
/// hand-rolled shadow of the server's vocabulary, already 8 cases against the
/// 20+ actually written, and #4426 is auditing it. Widening a shadow to fix a
/// mismatch caused by shadowing would be the wrong direction.
///
/// **The selection.** The overlay took `max(by: createdAt)`, so any later run
/// displaced the ingest-time geometry. Recency answers "what happened last",
/// not "what carries page boxes".
///
/// Choosing by payload is not merely tidier here — the producer *requires* it.
/// `_save_pdf_text_layer_geometry` writes a `text_geometry` artifact **even for
/// a page with no text layer**, carrying zero boxes, so that a scan stays
/// distinguishable from an unprocessed page. A scanned page therefore always
/// has an empty `text_geometry` artifact, and its real boxes arrive later under
/// `transcription` from OCR. Preferring `text_geometry` and stopping would fix
/// born-digital PDFs by blinding every scan.
///
/// So: prefer the geometry-native type, fall back to transcription, and skip
/// anything that carries no boxes — whichever type it came from.
enum OCRGeometrySelection {

    /// Artifact types that can carry page geometry, most authoritative first.
    ///
    /// `text_geometry` outranks `transcription` because it is the PDF's own
    /// text layer: exact coordinates from the file, not a model's estimate.
    static let geometryBearingTypes = ["text_geometry", "transcription"]

    /// Key the producer writes alongside a geometry artifact, letting an empty
    /// one be skipped from the LIST payload without spending a fetch on it.
    /// Geometry itself is omitted from list responses to keep them lean.
    static let boxCountKey = "box_count"

    /// Candidates to probe, best first.
    ///
    /// Ordered by type authority, then newest-first *within* a type. Recency
    /// survives only as a tie-break among artifacts of equal authority — it can
    /// no longer let a transcription displace the page's own text layer.
    ///
    /// Artifacts known to carry zero boxes are dropped: they are the producer's
    /// deliberate "this page is a scan" marker, not a geometry source. An
    /// artifact whose box count is unknown is kept, because absence of the hint
    /// is not evidence of absence of boxes.
    /// Written as explicit statements rather than a `filter.compactMap.sorted`
    /// chain: that form asks Swift to infer a tuple element type through four
    /// generic calls, and the type-checker times out on it (the
    /// `LibraryWindow.body` failure mode).
    static func ranked(_ candidates: [Artifact]) -> [Artifact] {
        var ranked: [(rank: Int, artifact: Artifact)] = []
        for artifact in candidates {
            if isKnownEmpty(artifact) { continue }
            guard let rank: Int = geometryBearingTypes.firstIndex(of: artifact.artifactType) else {
                continue
            }
            ranked.append((rank: rank, artifact: artifact))
        }
        ranked.sort { lhs, rhs in
            if lhs.rank != rhs.rank { return lhs.rank < rhs.rank }
            return lhs.artifact.createdAt > rhs.artifact.createdAt
        }
        return ranked.map { $0.artifact }
    }

    /// Whether the list payload already proves this artifact has no boxes.
    ///
    /// Only an explicit zero counts. A missing key means the producer did not
    /// say, which is the normal case for transcription artifacts.
    static func isKnownEmpty(_ artifact: Artifact) -> Bool {
        guard let raw = artifact.data?[boxCountKey]?.value else { return false }
        if let count = raw as? Int { return count == 0 }
        if let count = raw as? Double { return count == 0 }
        return false
    }

    /// Whether a fetched artifact actually carries drawable geometry.
    ///
    /// The last word, and the only one that matters: an artifact may be of the
    /// right type, recent, and still carry nothing.
    static func carriesGeometry(_ geometry: OCRGeometry?) -> Bool {
        guard let geometry else { return false }
        return !geometry.boxes.isEmpty
    }

    /// Fetch the best available geometry for a page, or `nil` if none applies.
    ///
    /// List first (lean payload), then the single GET that actually carries the
    /// geometry. Probes candidates best-first and stops at the first that
    /// carries boxes, because an artifact of the right type can still be empty:
    /// the importer writes a zero-box `text_geometry` artifact for every scanned
    /// page on purpose.
    ///
    /// Lives here rather than on either preview so the two rendering surfaces —
    /// a SwiftUI overlay for rasterised images, PDF annotations for PDFKit —
    /// share ONE decision about which artifact wins (#4418). They must draw
    /// differently because AppKit's `PDFView` has no coordinate space a SwiftUI
    /// sibling can be laid out in; they must not *choose* differently.
    @MainActor
    static func load(
        documentId: String,
        using artifactService: ArtifactService
    ) async throws -> OCRGeometry? {
        var candidates: [Artifact] = []
        for type in geometryBearingTypes {
            candidates += try await artifactService.getArtifacts(
                forDocumentId: documentId,
                type: type,
                includeDescendants: false
            )
        }
        for candidate in ranked(candidates) {
            let full = try await artifactService.getArtifact(id: candidate.id)
            if carriesGeometry(full.ocrGeometry) {
                return full.ocrGeometry
            }
        }
        return nil
    }
}
