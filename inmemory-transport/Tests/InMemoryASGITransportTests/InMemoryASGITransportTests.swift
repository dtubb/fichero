import HTTPTypes
import OpenAPIRuntime
import PythonKit
import XCTest

@testable import InMemoryASGITransport

final class InMemoryASGITransportTests: XCTestCase {

    // MARK: - (a) Unary: drive the real Fichero FastAPI app /api/health in-process.

    func testUnaryRealAppHealth() async throws {
        let app = ASGIAppLoader.importApp(module: "fichero.api.main", attribute: "app")
        let transport = InMemoryASGIClientTransport(app: app)

        let request = HTTPRequest(
            method: .get,
            scheme: "http",
            authority: "127.0.0.1",
            path: "/api/health"
        )

        let start = Date()
        let (response, body) = try await transport.send(
            request, body: nil, baseURL: URL(string: "http://127.0.0.1")!, operationID: "health"
        )
        let elapsed = Date().timeIntervalSince(start)

        XCTAssertEqual(response.status.code, 200, "health should return 200")

        let collected = try await Data(collecting: body ?? .init(""), upTo: 1 << 20)
        let json = String(decoding: collected, as: UTF8.self)
        print("[unary] /api/health in \(String(format: "%.3f", elapsed))s -> \(json.prefix(120))")
        XCTAssertTrue(json.contains("\"status\":\"healthy\""), "unexpected health body: \(json)")
    }

    // MARK: - (b) Streaming: prove chunks arrive INCREMENTALLY, not buffered.

    func testStreamingIsIncremental() async throws {
        // Synthetic ASGI app: 3 body chunks, ~0.3s apart, more_body:true between them.
        let synthApp = ASGIAppLoader.execApp(
            #"""
            import asyncio

            INTERVAL = 0.3

            async def app(scope, receive, send):
                assert scope["type"] == "http"
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/event-stream")],
                })
                for i in range(3):
                    await asyncio.sleep(INTERVAL)
                    await send({
                        "type": "http.response.body",
                        "body": f"chunk{i}".encode(),
                        "more_body": i < 2,
                    })
            """#
        )

        let transport = InMemoryASGIClientTransport(app: synthApp)
        let request = HTTPRequest(
            method: .get, scheme: "http", authority: "127.0.0.1", path: "/stream"
        )

        let start = Date()
        let (response, body) = try await transport.send(
            request, body: nil, baseURL: URL(string: "http://127.0.0.1")!, operationID: "stream"
        )
        XCTAssertEqual(response.status.code, 200)

        var arrivals: [(text: String, at: TimeInterval)] = []
        let unwrapped = try XCTUnwrap(body)
        for try await chunk in unwrapped {
            let t = Date().timeIntervalSince(start)
            let text = String(decoding: chunk, as: UTF8.self)
            arrivals.append((text, t))
            print(String(format: "[stream] +%.2fs  %@", t, text))
        }

        // Content correctness.
        XCTAssertEqual(arrivals.map(\.text), ["chunk0", "chunk1", "chunk2"])

        // THE KEY ASSERTION: chunks are surfaced incrementally, not all at the end.
        // With a buffering transport, every arrival timestamp would be ~identical
        // (all at ~0.9s). With true streaming they are spaced ~0.3s apart.
        let interval = 0.3
        let firstArrival = arrivals[0].at
        let lastArrival = arrivals[2].at

        // First chunk must arrive well before the last — at least ~2 intervals earlier.
        let gap = lastArrival - firstArrival
        print(String(format: "[stream] first=%.2fs last=%.2fs gap=%.2fs", firstArrival, lastArrival, gap))
        XCTAssertGreaterThan(
            gap, interval * 1.5,
            "chunk 1 must arrive well before chunk 3 (gap \(gap)s) — proves non-buffering"
        )

        // First chunk should arrive around one interval, not after the whole app ran.
        XCTAssertLessThan(
            firstArrival, interval * 2.0,
            "first chunk arrived at \(firstArrival)s — too late, looks buffered"
        )

        // Successive gaps should each be ~one interval (loose bounds for CI jitter).
        let gap01 = arrivals[1].at - arrivals[0].at
        let gap12 = arrivals[2].at - arrivals[1].at
        XCTAssertGreaterThan(gap01, interval * 0.5, "gap0->1 too small: \(gap01)s")
        XCTAssertGreaterThan(gap12, interval * 0.5, "gap1->2 too small: \(gap12)s")
    }
}
