@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The registry is the routing seam that lets the system-instantiated scheme
/// adapters (URLProtocol / WKURLSchemeHandler / AVAssetResourceLoaderDelegate)
/// map a `fichero-res://…?c=<token>` URL back to the `FicheroClient` that serves
/// it. These cover token stability, per-client isolation, and round-tripping a
/// built URL back to its loader + parts.
@MainActor
@Suite("StorageResourceRegistry")
struct StorageResourceRegistryTests {

    @Test("a client's token is stable across calls")
    func tokenIsStable() {
        let registry = StorageResourceRegistry.shared
        let client = FicheroClient()
        let first = registry.token(for: client)
        let second = registry.token(for: client)
        #expect(first == second)
    }

    @Test("distinct clients get distinct tokens")
    func distinctClientsDistinctTokens() {
        let registry = StorageResourceRegistry.shared
        let a = FicheroClient()
        let b = FicheroClient()
        #expect(registry.token(for: a) != registry.token(for: b))
    }

    @Test("built URL resolves back to the same client's loader and parts")
    func urlRoundTripsToLoader() {
        let registry = StorageResourceRegistry.shared
        let client = FicheroClient()
        let url = registry.url(for: client, kind: .display, documentId: "doc-42")

        let resolved = registry.resolve(url)
        #expect(resolved != nil)
        #expect(resolved?.parsed.kind == .display)
        #expect(resolved?.parsed.documentId == "doc-42")
        // Same client => same loader instance the registry minted for its token.
        let token = registry.token(for: client)
        #expect(resolved?.loader === registry.loader(forToken: token))
    }

    @Test("an unregistered token does not resolve (no silent substitute)")
    func unknownTokenDoesNotResolve() {
        let registry = StorageResourceRegistry.shared
        let foreign = StorageResourceURL.make(kind: .source, documentId: "x", token: "no-such-token")
        #expect(registry.resolve(foreign) == nil)
    }

    @Test("a foreign-scheme URL does not resolve")
    func foreignSchemeDoesNotResolve() {
        let registry = StorageResourceRegistry.shared
        let https = URL(string: "https://127.0.0.1:8765/api/storage/thumbnail/x")!
        #expect(registry.resolve(https) == nil)
    }
}
