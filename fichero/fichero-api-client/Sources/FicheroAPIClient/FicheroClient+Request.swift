import Foundation
import HTTPTypes
import OpenAPIRuntime

extension FicheroClient {
    /// Issue a one-shot (non-streaming) request on `path` through the SAME
    /// `ClientTransport` + middleware stack the generated client uses, and return
    /// the HTTP status plus the fully-collected response body as `Data`.
    ///
    /// This is the buffered sibling of `streamLines`. Because it dials through
    /// `ClientTransport` — URLSession for `.https`, AsyncHTTPClient for `.uds`,
    /// or the in-process ASGI transport for `.inMemory` — it works over a
    /// UDS-only or socket-less engine where a raw `URLSession` to
    /// `127.0.0.1:8765` would silently fail (the "Loaded 0 entities" symptom).
    /// Auth (`AuthTokenMiddleware`) and library scoping (`LibraryPathMiddleware`)
    /// are applied by the shared middleware stack, so no `Authorization` /
    /// `X-Fichero-Library-Path` headers are hand-rolled here.
    ///
    /// - Parameters:
    ///   - path: The full request path, e.g. `/api/kg/graph/metrics`. Already
    ///     includes the `/api` prefix, matching the generated operation paths.
    ///   - method: HTTP method name (`GET`, `POST`, `DELETE`, `PATCH`, ...).
    ///     Unrecognised values fall back to `GET`.
    ///   - queryItems: Optional query items appended to the request target.
    ///   - jsonBody: Optional pre-serialized JSON request body. When present, a
    ///     `Content-Type: application/json` header is added.
    /// - Returns: The response status code and the buffered body bytes.
    public func requestData(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: Data? = nil
    ) async throws -> (status: Int, data: Data) {
        var components = URLComponents()
        components.path = path
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        guard let requestTarget = components.string else {
            throw FicheroStreamingError.invalidRequestTarget
        }

        let httpMethod = HTTPRequest.Method(method) ?? .get
        var request = HTTPRequest(method: httpMethod, scheme: nil, authority: nil, path: requestTarget)

        var httpBody: HTTPBody?
        if let jsonBody {
            request.headerFields[.contentType] = "application/json"
            httpBody = HTTPBody([UInt8](jsonBody))
        }

        let serverURL = Self.makeServerURL(baseURL: baseURL, transportMode: transportMode)
        let operationID = "ficheroRequestData"

        // Fold the middleware stack around the transport exactly as the generated
        // `Client` (and `streamLines`) does, so the request gets identical auth +
        // library headers. Captured values are all Sendable.
        let transport = self.transport
        var next: @Sendable (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?) = {
            request, body, url in
            try await transport.send(request, body: body, baseURL: url, operationID: operationID)
        }
        for middleware in middlewares.reversed() {
            let current = next
            next = { request, body, url in
                try await middleware.intercept(
                    request,
                    body: body,
                    baseURL: url,
                    operationID: operationID,
                    next: current
                )
            }
        }

        let (response, responseBody): (HTTPResponse, HTTPBody?)
        do {
            (response, responseBody) = try await next(request, httpBody, serverURL)
        } catch {
            // Observability seam (Daniel's mandate): classify + log the ACTUAL
            // cause of a transport failure instead of leaking a bare
            // `NSURLErrorDomain -1004`, then re-throw the ORIGINAL error so
            // callers' `catch`/control-flow are unchanged.
            FicheroClient.logConnectionFailure(
                error,
                transport: transportMode,
                operationID: operationID
            )
            throw error
        }
        let data: Data
        if let responseBody {
            data = try await Data(collecting: responseBody, upTo: .max)
        } else {
            data = Data()
        }
        return (response.status.code, data)
    }
}
