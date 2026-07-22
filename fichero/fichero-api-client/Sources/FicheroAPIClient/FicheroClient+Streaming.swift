import Foundation
import HTTPTypes
import OpenAPIRuntime

/// Errors raised while opening a streaming request.
public enum FicheroStreamingError: Error, Sendable {
    /// The path / query could not be assembled into a valid request target.
    case invalidRequestTarget
}

extension FicheroClient {
    /// Open a streaming GET on `/api/<pathComponents>` through the SAME
    /// `ClientTransport` + middleware stack the generated client uses, and return
    /// the HTTP status plus the response body as a stream of newline-delimited
    /// text lines (SSE frames are `\n`-delimited).
    ///
    /// Because it dials through `ClientTransport` — URLSession for `.https`,
    /// AsyncHTTPClient for `.uds`, or any in-process transport — it works over a
    /// UDS-only or socket-less engine where a raw `URLSession` to
    /// `127.0.0.1:8765` would fail. Auth (`AuthTokenMiddleware`) and library
    /// scoping (`LibraryPathMiddleware`) are applied by the shared middleware
    /// stack, so no headers are hand-rolled here.
    ///
    /// - Parameters:
    ///   - pathComponents: Path segments under `/api`, e.g. `["changes",
    ///     "stream"]` → `/api/changes/stream`.
    ///   - queryItems: Optional query items appended to the request.
    /// - Returns: The response status code and the body as a line stream.
    public func streamLines(
        pathComponents: [String],
        queryItems: [URLQueryItem] = []
    ) async throws -> (status: Int, lines: AsyncThrowingStream<String, any Error>) {
        let (status, body) = try await streamingResponse(
            pathComponents: pathComponents,
            queryItems: queryItems
        )
        return (status, SSEByteLines.lines(from: body ?? HTTPBody()))
    }

    /// Issue the streaming request through the middleware stack + transport and
    /// return the raw status and streaming body.
    private func streamingResponse(
        pathComponents: [String],
        queryItems: [URLQueryItem]
    ) async throws -> (status: Int, body: HTTPBody?) {
        var components = URLComponents()
        components.path = "/api/" + pathComponents.joined(separator: "/")
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        guard let requestTarget = components.string else {
            throw FicheroStreamingError.invalidRequestTarget
        }

        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: requestTarget)
        request.headerFields[.accept] = "text/event-stream"

        let serverURL = Self.makeServerURL(baseURL: baseURL, transportMode: transportMode)
        let operationID = "ficheroStreamLines"

        // Fold the middleware stack around the transport exactly as the generated
        // `Client` does, so the streaming request gets identical auth + library
        // headers. Captured values are all Sendable.
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
            (response, responseBody) = try await next(request, nil, serverURL)
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
        return (response.status.code, responseBody)
    }
}

/// The one SSE-frame splitter shared by every stream consumer (change /
/// activity / workflow). Turns an `HTTPBody` byte stream into newline-delimited
/// text lines, matching the `URLSession.AsyncBytes.lines` semantics the services
/// relied on before they moved onto the transport.
enum SSEByteLines {
    private static let newline: UInt8 = 0x0A
    private static let carriageReturn: UInt8 = 0x0D

    /// Emit each line as its terminating `\n` arrives (a trailing `\r` is
    /// stripped), reassembling lines split across chunk boundaries, and flush any
    /// final unterminated line when the body closes.
    static func lines(from body: HTTPBody) -> AsyncThrowingStream<String, any Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                var buffer: [UInt8] = []
                do {
                    for try await chunk in body {
                        buffer.append(contentsOf: chunk)
                        while let newlineIndex = buffer.firstIndex(of: newline) {
                            var lineBytes = Array(buffer[buffer.startIndex..<newlineIndex])
                            if lineBytes.last == carriageReturn { lineBytes.removeLast() }
                            continuation.yield(String(decoding: lineBytes, as: UTF8.self))
                            buffer.removeSubrange(buffer.startIndex...newlineIndex)
                        }
                    }
                    if !buffer.isEmpty {
                        if buffer.last == carriageReturn { buffer.removeLast() }
                        continuation.yield(String(decoding: buffer, as: UTF8.self))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
