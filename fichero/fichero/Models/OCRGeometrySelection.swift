import FicheroAPIClient
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
    /// `regions` (the bboxes-first Apple Vision pre-pass, 2026-08-11) ranks
    /// last: it is boxes without aligned text, so it shows a page's geometry
    /// BEFORE any transcription exists and yields to both richer types after.
    /// `aligned_transcript` (2026-09-06): Kraken baselines with a KNOWN
    /// transcript forced onto them line-by-line (no recognition). It carries
    /// text like `transcription` and shares its tier — newest measured pass
    /// wins — so a fresh alignment shows on its own and never permanently masks
    /// a later Detect Regions run.
    static let geometryBearingTypes = [
        "text_geometry", "transcription", "aligned_transcript", "regions"
    ]

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
        rankCandidates(candidates.filter { !isKnownEmpty($0) }.map {
            RankCandidate(type: $0.artifactType, isHandCurated: isHandCurated($0), createdAt: $0.createdAt, value: $0)
        })
    }

    /// The seam's ranking of a page's passes (source-model App slice A, #4954): what the Mac canvas
    /// draws, through `SegmentDisplay.selected(for:store:)` in `loadOCRGeometry`. Its LEGACY tier
    /// keeps `ranked(_:)`'s artifact-type rule (2026-08-25) and the curation override (2026-09-03)
    /// applies to every tier; the tiers above it rank passes that have no artifact at all (#5146).
    ///
    /// **Curation** takes BOTH signals `isHandCurated(_:Artifact)` takes,
    /// just addressed per pass instead of per artifact (review fix #2, the
    /// 2026-09-03 rule): a pass is hand-curated when its own
    /// `provenanceKind == .human` (mirrors `provider == "user"`) OR any of
    /// ITS segments is (`Segment.isHandCurated`, engine-set from the box's
    /// own `provider`/`source`) — the common case, a person's marquee
    /// written into an otherwise-machine pass. Ranking on `provenanceKind`
    /// alone would let the next machine run of that SAME pass type cover the
    /// person's region again.
    ///
    /// **`createdAt == nil`** (now possible — `PassRead.createdAt` is
    /// optional) sorts as the OLDEST candidate within its tier, never
    /// invented and never crashing the comparison: an unknown time is not
    /// evidence of recency.
    ///
    /// **No `isKnownEmpty` equivalent**: that existed purely to skip a
    /// FETCH for a candidate the lean list payload already proved was
    /// empty. This function's caller already holds every segment (one
    /// engine call, `source.one-store`), so "does this pass have any
    /// segments" is answered directly from that list, not carried as a
    /// field here.
    ///
    /// **Which passes rank, and in what order (#5146, applied 2026-09-27 from the programme's rules;
    /// `segment-editor.md`):** the engine's working pass → hand-curated → every other pass → legacy
    /// artifact geometry, newest first inside each tier. **An import has no tier of its own** (ruled
    /// 2026-10-04, #5443): it is ranked by date with the machine passes. The first rung is the
    /// ENGINE's answer (`PassRead.working`, `resolve_working_pass`), chosen or by the rule, so the
    /// image and the text cannot pick different passes by two copies of one ladder; the rungs below
    /// it only decide what is drawn when the working pass has no shapes. Only a LEGACY pass
    /// (provisional: read from an artifact's `ocr_geometry` blob) is ranked by its artifact type, with
    /// the old type tiers inside its tier and a non-geometry type left out. A real pass has no
    /// artifact behind it -- a PAGE or ALTO import, a folder import -- so `artifactType` is nil, and
    /// dropping it for that is what left every imported page with no boxes on the image while its
    /// text showed.
    ///
    /// **A pass without shapes goes last** (`ui.preview.draws-a-pass-with-shapes`): when every one
    /// of its segments in `segments` has no place to draw (`hasShape`), it may still be the page's
    /// text, but the boxes come from the best-ranked pass that has shapes. It is moved behind them,
    /// not dropped, so a text-only page (its only pass unstated) still selects its lines as before.
    /// A pass none of whose segments are in hand is not judged -- absence of the segments is not
    /// evidence of absence of shapes.
    nonisolated static func rankedPasses(_ passes: [SegmentPassValue], segments: [Segment]) -> [SegmentPassValue] {
        let curatedPassIds = Set(segments.filter(\.isHandCurated).map(\.passId))
        let heldPassIds = Set(segments.map(\.passId))
        let shapedPassIds = Set(segments.filter(hasShape).map(\.passId))
        var ranked: [RankedPass] = []
        // A georeferencing pass holds control points and a mask, not the page's text (#5122): it is
        // never drawn as the page's boxes, whatever its tier. Ranked with them, an imported
        // georeference outranked a machine transcription and the page went blank (bugs2, a35449e3b).
        for pass in passes where !pass.isGeoreferencing {
            let shapeless = heldPassIds.contains(pass.id) && !shapedPassIds.contains(pass.id)
            let tier: Int
            var typeRank = 0
            if pass.working {
                // The engine's working pass (#5156, #5443): a person's choice, or the ladder's answer.
                tier = -1
            } else if pass.provenanceKind == .human || curatedPassIds.contains(pass.id) {
                tier = 0
            } else if !pass.provisional {
                tier = 2
            } else {
                guard let type = pass.artifactType, let rank = geometryBearingTypes.firstIndex(of: type) else { continue }
                tier = 3
                typeRank = rank == 0 ? 0 : 1
            }
            ranked.append(RankedPass(
                shapeless: shapeless, tier: tier, typeRank: typeRank, createdAt: pass.createdAt ?? .distantPast, pass: pass
            ))
        }
        ranked.sort { lhs, rhs in
            if lhs.shapeless != rhs.shapeless { return !lhs.shapeless }
            if lhs.tier != rhs.tier { return lhs.tier < rhs.tier }
            if lhs.typeRank != rhs.typeRank { return lhs.typeRank < rhs.typeRank }
            return lhs.createdAt > rhs.createdAt
        }
        return ranked.map(\.pass)
    }

    /// Whether a segment has a place on the image to draw: not one whose file stated no place (the
    /// engine's `shape: unstated`, stored on a whole-page rect only because a segment must be
    /// somewhere), and not one with neither a box nor a drawn shape.
    nonisolated static func hasShape(_ segment: Segment) -> Bool {
        guard !segment.shapeIsUnstated else { return false }
        return segment.anchor.rect != nil || !SegmentShapes.drawn(for: segment).isEmpty
    }

    /// One pass with its place in the ladder -- a struct, not a tuple (SwiftLint `large_tuple`).
    private struct RankedPass {
        let shapeless: Bool
        let tier: Int
        let typeRank: Int
        let createdAt: Date
        let pass: SegmentPassValue
    }

    /// One candidate for `rankCandidates` — a plain struct rather than a
    /// four-member tuple (SwiftLint `large_tuple`, caught on build 2).
    private struct RankCandidate<T> {
        let type: String
        let isHandCurated: Bool
        let createdAt: Date
        let value: T
    }

    /// The one ranking algorithm (review fix #3): two tiers over
    /// `geometryBearingTypes` — `text_geometry` alone at rank 0, every other
    /// geometry-bearing type tied at rank 1 — plus a `-1` override for
    /// hand-curated candidates, newest first as the tie-break within a rank.
    /// Both `ranked(_:)` (artifacts) and `rankedPasses(_:segments:)`
    /// (passes) build their candidate list and call this, so the
    /// 2026-08-25 (type tiers) and 2026-09-03 (curation persists) rules live
    /// in exactly one place.
    nonisolated private static func rankCandidates<T>(_ candidates: [RankCandidate<T>]) -> [T] {
        var ranked: [(rank: Int, candidate: RankCandidate<T>)] = []
        for candidate in candidates {
            guard let typeRank = geometryBearingTypes.firstIndex(of: candidate.type) else { continue }
            let rank = candidate.isHandCurated ? -1 : (typeRank == 0 ? 0 : 1)
            ranked.append((rank: rank, candidate: candidate))
        }
        ranked.sort { lhs, rhs in
            if lhs.rank != rhs.rank { return lhs.rank < rhs.rank }
            return lhs.candidate.createdAt > rhs.candidate.createdAt
        }
        return ranked.map { $0.candidate.value }
    }

    /// Whether a person drew this geometry rather than a pass measuring it.
    ///
    /// TWO signals, because a drawn region can land two ways (verified
    /// against the real library, 2026-09-03: 955 geometry artifacts, none of
    /// them `provider: "user"`, yet the audit trail records `regions_edit`
    /// calls — so in practice the boxes went into machine artifacts):
    ///
    ///   * the ARTIFACT is `provider: "user"` — the one the region verbs
    ///     bootstrap when a page has no geometry at all. This is the only
    ///     curation signal in the LEAN list payload, so it is all the
    ///     ranking can see before fetching.
    ///   * the GEOMETRY carries hand-drawn boxes — true whenever a region
    ///     was added to an artifact a machine pass had already written,
    ///     which is the common case. Only visible once the geometry is in
    ///     hand, so it is checked where the candidate is fetched anyway.
    ///
    /// Neither alone is enough, and the second cannot be lifted into the
    /// ranking without fetching every candidate. See the review doc.
    static func isHandCurated(_ artifact: Artifact) -> Bool {
        if artifact.provider?.lowercased() == "user" { return true }
        return carriesCuration(artifact.ocrGeometry)
    }

    /// Whether this geometry holds boxes a person drew. Nil geometry — a
    /// list payload, which omits it — is not evidence either way.
    static func carriesCuration(_ geometry: OCRGeometry?) -> Bool {
        geometry?.boxes.contains(where: \.isHandDrawn) ?? false
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
    /// The winning geometry TOGETHER WITH the artifact it came from
    /// (2026-08-29, regions as first-class): curation verbs — move / delete /
    /// add / combine — must address the artifact that owns the boxes on
    /// screen, so a surface that can edit needs the id, not just the boxes.
    struct SelectedGeometry {
        let artifactId: String
        let geometry: OCRGeometry
    }

    @MainActor
    static func load(
        documentId: String,
        using artifactService: ArtifactService
    ) async throws -> OCRGeometry? {
        try await loadSelected(documentId: documentId, using: artifactService)?.geometry
    }

    @MainActor
    static func loadSelected(
        documentId: String,
        using artifactService: ArtifactService
    ) async throws -> SelectedGeometry? {
        // The inspector's selection outranks the ladder (Daniel, 2026-08-27:
        // "when I click on different regions in artifacts, should bounding
        // boxes update?"). Selecting a geometry-bearing artifact for THIS
        // document shows that artifact's boxes; anything else — no selection,
        // another document's artifact, a boxless artifact — falls back to the
        // authority ladder below. The check lives here so the image and PDF
        // surfaces cannot choose differently (#4418).
        let focus = FocusedArtifact.shared
        if let focusedId = focus.id,
           focus.documentId == documentId,
           let focused = focus.artifact,
           geometryBearingTypes.contains(focused.artifactType),
           !isKnownEmpty(focused),
           let full = try? await artifactService.getArtifact(id: focusedId),
           let geometry = full.ocrGeometry,
           carriesGeometry(geometry) {
            return SelectedGeometry(artifactId: focusedId, geometry: geometry)
        }
        var candidates: [Artifact] = []
        for type in geometryBearingTypes {
            candidates += try await artifactService.getArtifacts(
                forDocumentId: documentId,
                type: type,
                includeDescendants: false
            )
        }
        // Probe best-first and stop at the first candidate that carries
        // boxes — one fetch in the common case.
        //
        // Deliberately NOT "keep probing for a curated candidate"
        // (2026-09-03): the lean list omits geometry, so hand-drawn boxes
        // inside a machine artifact are invisible until it is fetched, and
        // hunting for them would cost a round-trip per candidate on every
        // page load. It buys almost nothing either — `promoteMarquees`
        // writes into the artifact the ladder already picked, so curated
        // boxes are normally in the winner. The artifact-level signal in
        // `ranked` covers the bootstrap case; the rest is in the review doc.
        for candidate in ranked(candidates) {
            let full = try await artifactService.getArtifact(id: candidate.id)
            if let geometry = full.ocrGeometry, carriesGeometry(geometry) {
                return SelectedGeometry(artifactId: candidate.id, geometry: geometry)
            }
        }
        return nil
    }
}
