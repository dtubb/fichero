import FicheroAPIClient
import Foundation

/// The transport the change-stream reads SSE frames from (#1863). Production
/// dials the engine through the shared `FicheroClient` transport (so the stream
/// works over `.https`, `.uds`, or an in-process engine — see
/// `FicheroClientChangeStreamTransport`); tests inject a stub that replays canned
/// frames, so frame-classification and self-echo dedup are unit-testable without
/// a live socket. The seam is deliberately narrow — it exposes only what the
/// classify loop consumes: the HTTP status plus the body as newline-delimited
/// SSE text lines.
@MainActor
protocol ChangeStreamTransport {
    /// Open `request` and return the HTTP status plus the response body as a
    /// stream of text lines (SSE frames are newline-delimited). Throws on a
    /// connect/transport failure.
    func connect(_ request: URLRequest) async throws -> (status: Int, lines: AsyncThrowingStream<String, any Error>)
}

/// Default transport: routes the change-stream SSE through the SAME
/// `FicheroClient` transport (URLSession for `.https`, AsyncHTTPClient for
/// `.uds`, or an in-process transport) and middleware stack the generated calls
/// use. This is what lets the reactive spine work over a UDS-only or socket-less
/// engine, where a raw `URLSession` to `127.0.0.1:8765` would fail.
///
/// The `URLRequest` (built by `engineEventStreamRequest`) carries only the
/// path/query here — auth and library-path headers are applied by the client's
/// middleware, so any headers already on the request are ignored.
struct FicheroClientChangeStreamTransport: ChangeStreamTransport {
    let client: FicheroClient

    func connect(_ request: URLRequest) async throws
        -> (status: Int, lines: AsyncThrowingStream<String, any Error>) {
        guard let url = request.url,
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw URLError(.badURL)
        }
        // The client's serverURL already carries the host; strip the leading
        // `/api` and split so `streamLines` rebuilds the request path through the
        // transport (it re-adds `/api`).
        var parts = components.path.split(separator: "/").map(String.init)
        if parts.first == "api" { parts.removeFirst() }
        return try await client.streamLines(
            pathComponents: parts,
            queryItems: components.queryItems ?? []
        )
    }
}
