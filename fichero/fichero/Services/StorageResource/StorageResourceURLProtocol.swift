import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "StorageResourceURLProtocol")

/// `URLProtocol` that intercepts `fichero-res://` URLs on any `URLSession` it is
/// registered with (including `URLSession.shared`, which backs `AsyncImage`),
/// and serves them through the transport-agnostic `StorageResourceLoader`.
///
/// This is the adapter for URLSession/AsyncImage/Spatial consumers. It reads the
/// routing token from the URL, resolves the matching loader in
/// `StorageResourceRegistry`, fetches the bytes over the active
/// `ClientTransport`, and hands them back as a synthetic `HTTPURLResponse`.
///
/// `@unchecked Sendable`: Foundation drives `URLProtocol` instances across
/// threads and the async fetch runs off the calling thread. The only mutable
/// state is `loadTask`, guarded by `lock`; every `URLProtocolClient` callback is
/// made from the single load `Task`, so there is no concurrent client-callback
/// race.
final class StorageResourceURLProtocol: URLProtocol, @unchecked Sendable {
    /// Registered exactly once (idempotent) the first time a client is added to
    /// the registry, so `URLSession.shared`/`AsyncImage` resolve `fichero-res://`
    /// before any such URL exists.
    private static let registerOnceToken: Void = {
        URLProtocol.registerClass(StorageResourceURLProtocol.self)
        return ()
    }()

    static func registerOnce() {
        _ = registerOnceToken
    }

    private let lock = NSLock()
    private var loadTask: Task<Void, Never>?

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.scheme == StorageResourceURL.scheme
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        let task = Task { [weak self] in
            await self?.performLoad()
        }
        lock.lock()
        loadTask = task
        lock.unlock()
    }

    override func stopLoading() {
        lock.lock()
        loadTask?.cancel()
        loadTask = nil
        lock.unlock()
    }

    private func performLoad() async {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: StorageResourceError.malformedURL(URL(string: "about:blank")!))
            return
        }
        do {
            let resource = try await Self.load(url: url)
            try Task.checkCancellation()
            let response = HTTPURLResponse(
                url: url,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: [
                    "Content-Type": resource.contentType,
                    "Content-Length": String(resource.data.count)
                ]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: resource.data)
            client?.urlProtocolDidFinishLoading(self)
        } catch is CancellationError {
            // stopLoading already tore the request down; nothing to report.
        } catch {
            logger.error("fichero-res load failed for \(url.absoluteString, privacy: .public): \(error.localizedDescription, privacy: .public)")
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    /// Resolve + fetch on the main actor (where the registry / client live).
    @MainActor
    private static func load(url: URL) async throws -> StorageResourceLoader.Resource {
        guard let (loader, parsed) = StorageResourceRegistry.shared.resolve(url) else {
            if let parsed = StorageResourceURL.parse(url) {
                throw StorageResourceError.unknownClient(token: parsed.token)
            }
            throw StorageResourceError.malformedURL(url)
        }
        return try await loader.fetch(kind: parsed.kind, documentId: parsed.documentId)
    }
}
