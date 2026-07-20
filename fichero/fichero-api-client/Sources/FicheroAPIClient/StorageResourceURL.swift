import Foundation

/// The three storage resource kinds the engine serves for a document. Mirrors
/// the `/api/storage/{thumbnail,display,source}/{doc_id}` endpoints.
public enum StorageResourceKind: String, Sendable, CaseIterable {
    case thumbnail
    case display
    case source
}

/// Pure builder/parser for the app's custom `fichero-res://` scheme.
///
/// Every in-app storage fetch — WebKit subresources, `AVURLAsset` media,
/// `URLSession`/`AsyncImage` — routes through URLs of the form
/// `fichero-res://<kind>/<documentId>?c=<token>` instead of a raw
/// `https://127.0.0.1:8765/api/storage/...` URL. A raw engine URL assumes an
/// HTTP host and breaks the instant the active `ClientTransport` is `.uds`
/// (AF_UNIX socket) or an in-memory transport; a `fichero-res://` URL carries
/// no host at all. The adapters (`URLProtocol` / `WKURLSchemeHandler` /
/// `AVAssetResourceLoaderDelegate`) resolve it by handing the `token` back to a
/// registry that owns the matching `FicheroClient`, so the bytes always travel
/// the generated OpenAPI client over whatever transport that client dials.
///
/// The `token` selects *which* client (i.e. which library / host) serves the
/// request — the system-instantiated adapters can't be dependency-injected, so
/// the URL itself carries the routing key.
///
/// This type is deliberately pure (no networking, no app types) so its URL
/// construction and parsing are unit-testable headlessly via `swift test`.
public enum StorageResourceURL {
    /// The custom URL scheme. Chosen to be unmistakably non-network so
    /// `URLProtocol`, `WKURLSchemeHandler`, and `AVAssetResourceLoader` all
    /// recognize and intercept it.
    public static let scheme = "fichero-res"

    /// Query-item name carrying the client-routing token.
    public static let tokenQueryName = "c"

    /// A parsed `fichero-res://` URL.
    public struct Parsed: Equatable, Sendable {
        public let kind: StorageResourceKind
        public let documentId: String
        public let token: String

        public init(kind: StorageResourceKind, documentId: String, token: String) {
            self.kind = kind
            self.documentId = documentId
            self.token = token
        }
    }

    /// Build `fichero-res://<kind>/<documentId>?c=<token>`.
    ///
    /// The document id is placed as a single path component (percent-encoded by
    /// `URLComponents`), so ids containing reserved characters round-trip
    /// cleanly through `parse`.
    public static func make(
        kind: StorageResourceKind,
        documentId: String,
        token: String
    ) -> URL {
        var components = URLComponents()
        components.scheme = scheme
        components.host = kind.rawValue
        // Leading slash makes `documentId` the first path component; assigning a
        // raw string here defers percent-encoding to `url`.
        components.path = "/" + documentId
        components.queryItems = [URLQueryItem(name: tokenQueryName, value: token)]
        guard let url = components.url else {
            // A percent-encodable string always yields a URL here; a failure is a
            // genuine programmer error, not a runtime condition to swallow.
            preconditionFailure("Un-buildable fichero-res URL for documentId: \(documentId)")
        }
        return url
    }

    /// Parse a `fichero-res://` URL back into its `(kind, documentId, token)`.
    /// Returns `nil` for any URL that isn't a well-formed resource URL of this
    /// scheme — callers treat `nil` as "not mine / malformed", never as a
    /// silent success.
    public static func parse(_ url: URL) -> Parsed? {
        guard url.scheme == scheme,
              let host = url.host,
              let kind = StorageResourceKind(rawValue: host)
        else { return nil }

        // Strip the single leading slash; the remainder is the (decoded)
        // document id. `url.path` is already percent-decoded by Foundation.
        let path = url.path
        let documentId = path.hasPrefix("/") ? String(path.dropFirst()) : path
        guard !documentId.isEmpty else { return nil }

        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let token = components.queryItems?
                  .first(where: { $0.name == tokenQueryName })?.value,
              !token.isEmpty
        else { return nil }

        return Parsed(kind: kind, documentId: documentId, token: token)
    }
}
