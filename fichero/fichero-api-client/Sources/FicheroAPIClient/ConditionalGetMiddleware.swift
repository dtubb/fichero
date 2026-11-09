import Foundation
import HTTPTypes
import OpenAPIRuntime

/// Sends `If-None-Match` on the pollers whose engine answers carry an ETag (#6446: `GET /api/stats`, the recipes Start plan), and turns the
/// engine's `304` back into the last `200` it held, so a caller never sees a 304: an unchanged library costs an empty answer, not the
/// whole body. The held answer is keyed by the full request path and the library header, so two libraries never share one.
public final class ConditionalGetMiddleware: ClientMiddleware, @unchecked Sendable {
    private struct Held {
        let etag: String
        let body: Data
        let fields: HTTPFields
    }

    private let lock = NSLock()
    private var held: [String: Held] = [:]

    public init() {}

    /// The paths whose answers the engine tags (#6446).
    static func isTagged(_ path: String) -> Bool {
        let bare = path.split(separator: "?").first.map(String.init) ?? path
        return bare == "/api/stats" || bare == "/api/recipes/project/start"
    }

    private func key(_ request: HTTPRequest) -> String {
        "\(request.path ?? "")|\(request.headerFields[HTTPField.Name("X-Fichero-Library-Path")!] ?? "")"
    }

    public func intercept(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String,
        next: (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)
    ) async throws -> (HTTPResponse, HTTPBody?) {
        guard request.method == .get, Self.isTagged(request.path ?? "") else {
            return try await next(request, body, baseURL)
        }
        let key = key(request)
        var request = request
        let before = lock.withLock { held[key] }
        if let before { request.headerFields[.ifNoneMatch] = before.etag }
        let (response, responseBody) = try await next(request, body, baseURL)
        if response.status.code == 304, let before {
            return (HTTPResponse(status: .ok, headerFields: before.fields), HTTPBody(before.body))
        }
        guard response.status.code == 200, let etag = response.headerFields[.eTag], let responseBody else {
            return (response, responseBody)
        }
        let data = try await Data(collecting: responseBody, upTo: 64 * 1024 * 1024)
        lock.withLock { held[key] = Held(etag: etag, body: data, fields: response.headerFields) }
        return (response, HTTPBody(data))
    }
}
