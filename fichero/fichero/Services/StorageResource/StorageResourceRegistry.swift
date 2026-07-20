import FicheroAPIClient
import Foundation

/// Shared, main-actor registry that maps a `fichero-res://` routing token back
/// to the `StorageResourceLoader` (and thus the `FicheroClient`) that serves it.
///
/// ## Why a registry
/// The three scheme adapters — `StorageResourceURLProtocol`,
/// `StorageResourceSchemeHandler` (WebKit), `StorageResourceAVAssetDelegate`
/// (AVFoundation) — are instantiated by the system, not by the app's
/// dependency graph, so they cannot be handed a `FicheroClient` directly. The
/// `fichero-res://…?c=<token>` URL instead carries a routing token; the adapter
/// looks the token up here to reach the right client. This is the deliberate,
/// documented `static` seam the design calls for.
///
/// ## Lifecycle
/// A token is minted per distinct `FicheroClient` instance and is stable for
/// that instance's lifetime (`APIClient.reconfigure` reuses the same
/// `FicheroClient`, so a host change keeps the token — the loader follows the
/// client to the new host automatically). New libraries create new clients and
/// get fresh tokens. The registry is an app-lifetime singleton and holds its
/// loaders (and thus clients) strongly; the number of libraries opened in a
/// session is small, so entries are not evicted. If that ever grows unbounded,
/// add explicit `unregister` on library close — intentionally omitted now to
/// avoid dangling tokens on in-flight web/media requests.
@MainActor
final class StorageResourceRegistry {
    static let shared = StorageResourceRegistry()

    private var loadersByToken: [String: StorageResourceLoader] = [:]
    private var tokensByClient: [ObjectIdentifier: String] = [:]
    private var counter = 0

    private init() {}

    /// The stable routing token for `client`, minting one (and its loader) on
    /// first use. Registering the first client also installs the global
    /// `URLProtocol` so plain `URLSession` / `AsyncImage` consumers resolve
    /// `fichero-res://` before any such URL is produced.
    func token(for client: FicheroClient) -> String {
        let identity = ObjectIdentifier(client)
        if let existing = tokensByClient[identity] { return existing }
        counter += 1
        let token = "c\(counter)"
        tokensByClient[identity] = token
        loadersByToken[token] = StorageResourceLoader(client: client)
        StorageResourceURLProtocol.registerOnce()
        return token
    }

    /// Build a `fichero-res://` URL for a resource served by `client`.
    func url(
        for client: FicheroClient,
        kind: StorageResourceKind,
        documentId: String
    ) -> URL {
        StorageResourceURL.make(kind: kind, documentId: documentId, token: token(for: client))
    }

    /// The loader for a routing token, or `nil` if the token is unknown.
    func loader(forToken token: String) -> StorageResourceLoader? {
        loadersByToken[token]
    }

    /// Resolve a `fichero-res://` URL to its loader + parsed parts in one step.
    /// Returns `nil` (never a substitute) when the URL is foreign/malformed or
    /// its token is unregistered — the adapter fails the request loudly.
    func resolve(_ url: URL) -> (loader: StorageResourceLoader, parsed: StorageResourceURL.Parsed)? {
        guard let parsed = StorageResourceURL.parse(url),
              let loader = loadersByToken[parsed.token] else { return nil }
        return (loader, parsed)
    }
}
