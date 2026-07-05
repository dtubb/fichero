import Foundation

/// The transport the change-stream reads SSE frames from (#1863). Production
/// reads the certificate-pinned `URLSession.bytes` loop; tests inject a stub that
/// replays canned frames, so frame-classification and self-echo dedup are
/// unit-testable without a live socket. The seam is deliberately narrow — it
/// exposes only what the classify loop consumes: the HTTP status plus the body
/// as newline-delimited SSE text lines.
@MainActor
protocol ChangeStreamTransport {
    /// Open `request` and return the HTTP status plus the response body as a
    /// stream of text lines (SSE frames are newline-delimited). Throws on a
    /// connect/transport failure.
    func connect(_ request: URLRequest) async throws -> (status: Int, lines: AsyncThrowingStream<String, any Error>)
}

/// Default transport: the certificate-pinned `URLSession.bytes` SSE loop. Owns
/// the session so it is retained for the lifetime of the stream — the delegate
/// challenge handler only fires when the session outlives the `bytes(for:)` call.
struct URLSessionChangeStreamTransport: ChangeStreamTransport {
    let session: URLSession

    func connect(_ request: URLRequest) async throws -> (status: Int, lines: AsyncThrowingStream<String, any Error>) {
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        let stream = AsyncThrowingStream<String, any Error> { continuation in
            let pump = Task {
                do {
                    for try await line in bytes.lines {
                        continuation.yield(line)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in pump.cancel() }
        }
        return (http.statusCode, stream)
    }
}
