import FicheroAPIClient
import Foundation
import OSLog
import WebKit

private let logger = Logger(subsystem: "app.fichero.fichero", category: "StorageResourceSchemeHandler")

/// `WKURLSchemeHandler` that lets WebKit content load `fichero-res://` storage
/// resources (e.g. `<img src="fichero-res://display/…">`) through the
/// transport-agnostic `StorageResourceLoader` instead of a raw engine URL.
///
/// Register it on a `WKWebViewConfiguration`:
/// ```swift
/// config.setURLSchemeHandler(StorageResourceSchemeHandler(), forURLScheme: StorageResourceURL.scheme)
/// ```
///
/// WebKit forbids registering a handler for a scheme it treats as built-in
/// (http/https), which is exactly why storage images embedded in web content
/// must use the custom `fichero-res://` scheme to be interceptable over
/// UDS/in-memory transports.
///
/// `@MainActor`: `WKURLSchemeHandler` is `WK_SWIFT_UI_ACTOR` (main-actor
/// isolated) in the SDK, and WebKit makes every `start`/`stop` callback on the
/// main thread — so the in-flight `tasks` map is main-actor confined with no
/// locking.
@MainActor
final class StorageResourceSchemeHandler: NSObject, WKURLSchemeHandler {
    /// Tasks in flight keyed by object identity so `stop` cancels the right one.
    private var tasks: [ObjectIdentifier: Task<Void, Never>] = [:]

    func webView(_ webView: WKWebView, start urlSchemeTask: any WKURLSchemeTask) {
        let key = ObjectIdentifier(urlSchemeTask)
        guard let url = urlSchemeTask.request.url else {
            urlSchemeTask.didFailWithError(StorageResourceError.malformedURL(URL(string: "about:blank")!))
            return
        }
        tasks[key] = Task { @MainActor [weak self] in
            do {
                let resource = try await Self.load(url: url)
                try Task.checkCancellation()
                guard let self, self.tasks[key] != nil else { return }
                let response = HTTPURLResponse(
                    url: url,
                    statusCode: 200,
                    httpVersion: "HTTP/1.1",
                    headerFields: [
                        "Content-Type": resource.contentType,
                        "Content-Length": String(resource.data.count)
                    ]
                )!
                urlSchemeTask.didReceive(response)
                urlSchemeTask.didReceive(resource.data)
                urlSchemeTask.didFinish()
                self.tasks[key] = nil
            } catch {
                if error.isCancellationError {
                    // `stop` already removed the task; WebKit rejects callbacks on a
                    // stopped task.
                    return
                }
                let reason = error.localizedDescription
                logger.error(
                    "fichero-res web load failed for \(url.absoluteString, privacy: .public): \(reason, privacy: .public)"
                )
                guard let self, self.tasks[key] != nil else { return }
                urlSchemeTask.didFailWithError(error)
                self.tasks[key] = nil
            }
        }
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: any WKURLSchemeTask) {
        let key = ObjectIdentifier(urlSchemeTask)
        tasks[key]?.cancel()
        tasks[key] = nil
    }

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
