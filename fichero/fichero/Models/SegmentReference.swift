import FicheroAPIClient
import Foundation

/// A citable segment reference opened from outside the app (#5164; `source.segment.citable`):
/// `fichero:segment/<library>/<document>/<segment>`, as Copy Reference writes it. The app resolves it
/// through the engine's ONE resolver (`POST /api/locations/resolve`, which follows merges and splits and
/// refuses another library's reference), then opens the page with the segment selected.
struct SegmentReference: Equatable {
    let libraryId: String
    let documentId: String
    let segmentId: String

    /// The string form, exactly as the engine's reference route writes it.
    var string: String { "fichero:segment/\(libraryId)/\(documentId)/\(segmentId)" }

    /// A reference from a URL: `fichero:segment/…` or, as some apps rewrite it, `fichero://segment/…`.
    /// Nil for anything else -- a pairing link, a library path -- so those keep their own handling.
    static func parse(_ url: URL) -> SegmentReference? {
        guard url.scheme?.lowercased() == "fichero" else { return nil }
        let rest = url.absoluteString.dropFirst("fichero:".count).drop { $0 == "/" }
        let parts = rest.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 4, parts[0] == "segment", !parts[1...].contains(where: \.isEmpty) else { return nil }
        return SegmentReference(libraryId: parts[1], documentId: parts[2], segmentId: parts[3])
    }

    /// The same, from a string (a pasted link).
    static func parse(string: String) -> SegmentReference? {
        URL(string: string).flatMap(parse)
    }

    /// What the resolver is asked: the whole string, so the engine checks its library and page parts.
    var location: Components.Schemas.Location {
        Components.Schemas.Location(segmentId: string)
    }

    /// Where the resolved reference lands: the live segment's page, and the live segment (a merged or
    /// split one is followed, never the stale id). Nil when the segment was deleted with no successor.
    static func landing(_ resolved: Components.Schemas.ResolvedLocation) -> ReadingOrderChoice.Landing? {
        guard let segmentId = resolved.resolvedSegmentId, resolved.segmentDeleted != true else { return nil }
        return ReadingOrderChoice.Landing(documentId: resolved.resolvedDocumentId, segmentId: segmentId)
    }

    /// Resolve and say where to go -- the one path the URL handler and its test both take.
    @MainActor
    func resolve(with locations: LocationService) async throws -> ReadingOrderChoice.Landing? {
        Self.landing(try await locations.resolve(location))
    }
}
