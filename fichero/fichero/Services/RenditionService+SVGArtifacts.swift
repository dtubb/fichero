import FicheroAPIClient
import Foundation
import OSLog

private let svgRenditionLogger = Logger(
    subsystem: "app.fichero.fichero", category: "RenditionSVGArtifacts"
)

/// An AI redraw of a page as SVG is another way that page LOOKS, which is the
/// definition of a rendition — so it belongs on the up/down flip the preview
/// already has (Daniel, 2026-09-04: "that'd be cool to demo"), exactly as the
/// original↔edited pair does (ce831ebd3). No new gesture, no new pane.
///
/// They are not rows in the `renditions` table: a redraw is an ARTIFACT, and
/// its bytes are text, not pixels. These entries carry an id that says which
/// artifact they are, and the preview renders them through `WebContentCanvas`
/// (WebKit, scripts disabled, #4329) instead of decoding an `NSImage`.
extension DocumentRendition {
    static let svgRole = "svg"
    /// Marks an id as an SVG ARTIFACT rather than a stored rendition row.
    static let svgArtifactPrefix = "svg:"

    static func svgArtifactRenditionId(artifactId: String) -> String {
        "\(svgArtifactPrefix)\(artifactId)"
    }

    /// The artifact id encoded in an SVG rendition id; nil for anything else.
    static func svgArtifactId(of id: String) -> String? {
        guard id.hasPrefix(svgArtifactPrefix) else { return nil }
        let rest = String(id.dropFirst(svgArtifactPrefix.count))
        return rest.isEmpty ? nil : rest
    }

    var isSVGArtifact: Bool { Self.svgArtifactId(of: id) != nil }

    /// One flip entry per SVG artifact this document carries, newest first.
    ///
    /// `hasOwnFrame` is TRUE for every one of them, and that is the load-bearing
    /// claim here: a redraw is a NEW drawing of the page, not the page's own
    /// pixels re-processed. Word boxes and region overlays normalised to the
    /// node's frame do not land on it, and `overlayFrameMatches` skips them
    /// rather than painting a plausible band over a picture that never had
    /// those coordinates.
    static func svgRenditions(
        documentId: String, artifacts: [Artifact]
    ) -> [DocumentRendition] {
        artifacts
            .filter { $0.documentId == documentId && looksLikeSVG($0) }
            .sorted { $0.createdAt > $1.createdAt }
            .map { artifact in
                DocumentRendition(
                    id: svgArtifactRenditionId(artifactId: artifact.id),
                    documentId: documentId,
                    role: svgRole,
                    path: "",
                    isPrimary: false,
                    pixelWidth: nil,
                    pixelHeight: nil,
                    isMaterialized: true,
                    hasOwnFrame: true,
                    note: renditionNote(for: artifact)
                )
            }
    }

    /// Whether an artifact is an SVG redraw.
    ///
    /// The TYPE alone is not enough: `convert` writes `conversion` for five
    /// target formats (markdown, html, svg, latex, csv — `convert.py:43`), so a
    /// markdown conversion would join the flip as a picture that will not
    /// draw. The content settles it, on the same `<svg` root check the engine
    /// validates with before persisting (`convert.py:97`). Content is
    /// truncated in list payloads, so only the head is examined — a real SVG
    /// declares its root in the first few hundred bytes or it is not one.
    static func looksLikeSVG(_ artifact: Artifact) -> Bool {
        guard let content = artifact.content else { return false }
        return content.prefix(500).lowercased().contains("<svg")
    }

    /// What the flip strip says about this entry beyond "SVG": who drew it.
    static func renditionNote(for artifact: Artifact) -> String {
        let producer = [artifact.model, artifact.provider]
            .compactMap { value -> String? in
                let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return trimmed.isEmpty ? nil : trimmed
            }
            .first
        guard let producer else { return "Redrawn as SVG" }
        return "Redrawn as SVG by \(producer)"
    }
}

extension RenditionService {
    /// `items` plus this document's SVG redraws.
    ///
    /// Ordered LAST, after the staged pipeline and the edit chain: the flip
    /// runs from the page as scanned toward the most interpreted view of it,
    /// and a model's redrawing is the most interpreted thing in the sequence.
    /// It is never the landing rendition for the same reason — nobody opening
    /// a page wants a redrawing of it before they have seen it.
    func appendingSVGRenditions(
        to items: [DocumentRendition],
        documentId: String,
        artifactService: ArtifactService?
    ) async -> [DocumentRendition] {
        guard let artifactService else { return items }
        guard let artifacts = try? await artifactService.getArtifacts(
            forDocumentId: documentId, includeDescendants: false
        ) else {
            // A failed artifact fetch means the flip is shorter, not wrong —
            // but it is still a fault worth naming rather than a silent
            // absence the user would read as "this page has no redraw".
            svgRenditionLogger.error(
                "Artifacts unavailable for \(documentId); SVG renditions are off for this page"
            )
            return items
        }
        let svgs = DocumentRendition.svgRenditions(documentId: documentId, artifacts: artifacts)
        return svgs.isEmpty ? items : items + svgs
    }

    /// One SVG rendition's MARKUP.
    ///
    /// Text, not `Data`: the caller hands it to `WebContentCanvas`, which takes
    /// a string. The full artifact is fetched because list payloads truncate
    /// content, and half an SVG is not a picture — it is a parse error that
    /// renders as blank.
    func svgArtifactMarkup(
        renditionId: String, artifactService: ArtifactService?
    ) async throws -> String {
        guard let artifactId = DocumentRendition.svgArtifactId(of: renditionId),
              let artifactService else {
            throw RenditionServiceError.contentUnavailable(renditionId: renditionId)
        }
        let artifact = try await artifactService.getArtifact(id: artifactId)
        guard let markup = artifact.content, markup.contains("<svg") else {
            throw RenditionServiceError.contentUnavailable(renditionId: renditionId)
        }
        return markup
    }
}
