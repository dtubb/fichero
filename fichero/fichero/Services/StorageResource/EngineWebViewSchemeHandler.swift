import FicheroAPIClient
import Foundation
import OSLog
import WebKit

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EngineWebViewSchemeHandler")

/// `WKURLSchemeHandler` that funnels a KG reader-pane page load through the
/// transport-agnostic `FicheroClient` instead of a raw `https://…:8765` URL.
///
/// The KG pane renders a whole engine page (`fichero-server://engine/view/…`)
/// plus its relative subresources (`/api/…` data, `/view/…` static assets).
/// WKWebView can only dial an HTTP host, so over a `.uds` (AF_UNIX socket) or
/// in-memory transport the main-frame load fails with `-1004`. This handler
/// intercepts every `fichero-server://` navigation and subresource, maps it to
/// an engine path, and fetches it with `FicheroClient.requestData(...)` —
/// buffered — so the bytes travel whatever `ClientTransport` the client dials.
/// Auth (`AuthTokenMiddleware`) and library scoping (`LibraryPathMiddleware`)
/// are applied by the client's shared middleware stack, so the page needs no
/// hand-injected token and no headers are copied off the WebKit request.
///
/// This mirrors `StorageResourceSchemeHandler` (which does the same for
/// `fichero-res://` storage images); the difference is that this handler serves
/// arbitrary engine paths for a directly-injected `client` rather than a
/// registry-routed storage loader, because the KG pane owns its configuration
/// and can hand the correct library's client in.
///
/// `@MainActor`: `WKURLSchemeHandler` is main-actor isolated in the SDK and
/// WebKit makes every `start`/`stop` callback on the main thread, so the
/// in-flight `tasks` map needs no locking. `FicheroClient` is likewise
/// main-actor isolated.
@MainActor
final class EngineWebViewSchemeHandler: NSObject, WKURLSchemeHandler {
    /// Maximum response delivered to WebKit. `requestData` is already buffered;
    /// transport-level allocation bounds require a future streaming client API.
    private static let maxResponseBytes = 100 * 1024 * 1024

    static func validateResponseSize(byteCount: Int) throws {
        guard byteCount <= maxResponseBytes else {
            throw EngineWebViewError.responseTooLarge(
                actualBytes: byteCount,
                limitBytes: maxResponseBytes
            )
        }
    }

    private let client: FicheroClient
    /// Tasks in flight keyed by object identity so `stop` cancels the right one.
    private var tasks: [ObjectIdentifier: Task<Void, Never>] = [:]

    init(client: FicheroClient) {
        self.client = client
    }

    func webView(_ webView: WKWebView, start urlSchemeTask: any WKURLSchemeTask) {
        let key = ObjectIdentifier(urlSchemeTask)
        guard let url = urlSchemeTask.request.url,
              let enginePath = EngineWebViewURL.enginePath(from: url) else {
            urlSchemeTask.didFailWithError(EngineWebViewError.malformedURL(urlSchemeTask.request.url))
            return
        }
        let method = urlSchemeTask.request.httpMethod ?? "GET"
        let queryItems = EngineWebViewURL.queryItems(from: url)
        let body = Self.requestBody(from: urlSchemeTask.request)

        tasks[key] = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let (status, data) = try await self.client.requestData(
                    path: enginePath,
                    method: method,
                    queryItems: queryItems,
                    jsonBody: body
                )
                try Task.checkCancellation()
                guard self.tasks[key] != nil else { return }
                guard (200...299).contains(status) else {
                    // Fail the task loudly on a non-2xx so WebKit surfaces the
                    // error rather than rendering error-page bytes as content.
                    throw EngineWebViewError.httpStatus(status, path: enginePath)
                }
                try Self.validateResponseSize(byteCount: data.count)
                let response = HTTPURLResponse(
                    url: url,
                    statusCode: status,
                    httpVersion: "HTTP/1.1",
                    headerFields: [
                        "Content-Type": EngineWebViewURL.mimeType(forPath: enginePath),
                        "Content-Length": String(data.count)
                    ]
                )!
                urlSchemeTask.didReceive(response)
                urlSchemeTask.didReceive(data)
                urlSchemeTask.didFinish()
                self.tasks[key] = nil
            } catch {
                if error.isCancellationError {
                    // `stop` already removed the task; WebKit rejects callbacks on
                    // a stopped task.
                    return
                }
                // One OSLogMessage literal: `Logger` takes a literal, so `+`-joining
                // two interpolated fragments does not type-check.
                logger.error(
                    "fichero-server load failed for \(url.absoluteString, privacy: .public): \(error.localizedDescription, privacy: .public)"
                )
                guard self.tasks[key] != nil else { return }
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

    /// Extract a request body for `POST`/`PUT`/`PATCH`. WKWebView usually exposes
    /// `httpBody`; some `fetch`/XHR bodies arrive as an `httpBodyStream`, which we
    /// drain fully. `GET` requests have no body.
    private static func requestBody(from request: URLRequest) -> Data? {
        if let body = request.httpBody, !body.isEmpty { return body }
        guard let stream = request.httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 64 * 1024
        var buffer = [UInt8](repeating: 0, count: bufferSize)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: bufferSize)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data.isEmpty ? nil : data
    }
}

enum EngineWebViewError: Error, LocalizedError {
    case malformedURL(URL?)
    case httpStatus(Int, path: String)
    case responseTooLarge(actualBytes: Int, limitBytes: Int)

    var errorDescription: String? {
        switch self {
        case .malformedURL(let url):
            return "Malformed fichero-server URL: \(url?.absoluteString ?? "nil")"
        case .httpStatus(let status, let path):
            return "Engine returned HTTP \(status) for \(path)"
        case .responseTooLarge(let actualBytes, let limitBytes):
            return "Engine response of \(actualBytes) bytes exceeds the \(limitBytes)-byte limit"
        }
    }
}
