#if os(macOS)
import XCTest
import Foundation
import HTTPTypes
import OpenAPIRuntime
@testable import FicheroAPIClient

/// Makes `.inMemory` a first-class, fully-exercised test harness (#4052).
/// Proves the in-process ASGI bridge drives the real engine for unary +
/// streaming endpoints with auth/marker handling, and that the transport's
/// streaming/cancellation/concurrency guarantees hold (rebuilt against current
/// main — the unmerged `fix/inmemory-transport` branch sketched the intent;
/// this is the version that compiles + runs here).
///
/// All tests boot CPython via PythonKit and import the real engine `app`
/// in-process. The synthetic-app tests need no engine business logic; the
/// real-engine tests isolate HOME + `.api-key` so they never clobber a running
/// engine's `app.duckdb` or the developer's real `.api-key`.
@MainActor
final class InMemoryASGITransportHarnessTests: XCTestCase {

    override func setUp() async throws {
        try InMemoryTestEnv.configureOrSkip()
    }

    // MARK: - (a) Unary against the REAL engine app

    /// The real FastAPI app answers a plain unary GET in-process — the
    /// `AsgiBridge`/`PythonWorker`/GIL path is wired end-to-end.
    func testUnaryRealAppHealth() async throws {
        let transport = InMemoryASGIClientTransport(app: InMemoryEngineApp.shared())
        let request = HTTPRequest(
            method: .get, scheme: "http", authority: "127.0.0.1", path: "/api/health"
        )

        let (response, body) = try await transport.send(
            request, body: nil,
            baseURL: URL(string: "http://asgi.local")!,
            operationID: "harnessHealth"
        )
        XCTAssertEqual(response.status.code, 200, "real-engine /api/health must return 200")

        var bytes: [UInt8] = []
        if let body { for try await chunk in body { bytes.append(contentsOf: chunk) } }
        let json = String(decoding: bytes, as: UTF8.self)
        XCTAssertTrue(json.contains("\"status\":\"healthy\""),
                      "unexpected health body: \(json)")
    }

    // MARK: - (a2) AUTH against the REAL engine app

    /// An authenticated endpoint returns 401 without a token and 200 with the
    /// bootstrap token + the `inmemory` transport marker (which grants
    /// loopback-owner). Proves the marker → loopback-trust path works
    /// in-process — the same path the full `FicheroClient(transportMode:
    /// .inMemory)` relies on.
    func testAuthenticatedEndpointHonorsInMemoryMarker() async throws {
        // app.duckdb is frozen at storage-module import from FICHERO_BASE_PATH;
        // require it to be isolated before the process started. The .api-key
        // is isolated per-test via HOME.
        try InMemoryTestEnv.requireIsolatedBasePath()
        let (_, token, restoreHome) = try InMemoryTestEnv.isolatedHomeWithBootstrapToken()
        defer { restoreHome() }
        let transport = InMemoryASGIClientTransport(app: InMemoryEngineApp.shared())
        let path = "/api/settings/model-profiles"  // requires auth; no library
        let baseURL = URL(string: "http://asgi.local")!

        // (i) Without a token: must NOT be 200 (proves the endpoint is gated).
        let unauth = HTTPRequest(method: .get, scheme: "http", authority: "127.0.0.1", path: path)
        let (unauthResp, _) = try await transport.send(
            unauth, body: nil, baseURL: baseURL, operationID: "modelProfilesUnauth")
        XCTAssertNotEqual(
            unauthResp.status.code, 200,
            "endpoint must reject unauthenticated in-process calls (got \(unauthResp.status.code))")

        // (ii) With the bootstrap token + the in-memory transport marker: 200.
        var authed = HTTPRequest(method: .get, scheme: "http", authority: "127.0.0.1", path: path)
        authed.headerFields[.authorization] = "Bearer \(token)"
        let (resp, body) = try await transport.send(
            authed, body: nil, baseURL: baseURL, operationID: "modelProfilesAuth")
        var bytes: [UInt8] = []
        if let body { for try await chunk in body { bytes.append(contentsOf: chunk) } }
        let bodyText = String(decoding: bytes, as: UTF8.self)
        XCTAssertEqual(
            resp.status.code, 200,
            "authenticated endpoint should return 200 in-process via the inmemory marker, "
                + "got \(resp.status.code): \(bodyText)")
    }

    // MARK: - (b) Streaming is truly incremental (not buffered)

    /// A synthetic ASGI app emitting 3 chunks ~0.3s apart must surface each
    /// chunk to Swift as it arrives — not all at the end. Proves the bridge's
    /// `queue.Queue` handoff is genuinely incremental.
    func testStreamingIsIncremental() async throws {
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
        let request = HTTPRequest(method: .get, scheme: "http", authority: "127.0.0.1", path: "/stream")

        let start = Date()
        let (response, body) = try await transport.send(
            request, body: nil, baseURL: URL(string: "http://asgi.local")!, operationID: "stream")
        XCTAssertEqual(response.status.code, 200)

        var arrivals: [(text: String, at: TimeInterval)] = []
        let unwrapped = try XCTUnwrap(body)
        for try await chunk in unwrapped {
            let t = Date().timeIntervalSince(start)
            arrivals.append((String(decoding: chunk, as: UTF8.self), t))
        }

        XCTAssertEqual(arrivals.map(\.text), ["chunk0", "chunk1", "chunk2"])

        // THE KEY ASSERTION: chunks surface incrementally, not all at the end.
        // With a buffering transport, every timestamp would be ~identical (~0.9s).
        let interval = 0.3
        let gap = arrivals[2].at - arrivals[0].at
        XCTAssertGreaterThan(
            gap, interval * 1.5,
            "chunk 1 must arrive well before chunk 3 (gap \(gap)s) — proves non-buffering")
        XCTAssertLessThan(
            arrivals[0].at, interval * 2.0,
            "first chunk arrived at \(arrivals[0].at)s — too late, looks buffered")
    }

    // MARK: - (c) Concurrency: a unary call completes while a stream drains

    /// A slow SSE-like stream (3 chunks 0.4s apart, ~1.2s total) must NOT
    /// serialize the shared Python worker: a fast unary call fired mid-stream
    /// completes promptly. The body-drain thread releases the GIL while parked
    /// in `queue.Queue.get()`, so the worker can service the unary request.
    func testConcurrentUnaryDuringStreamDrain() async throws {
        let slowApp = ASGIAppLoader.execApp(
            #"""
            import asyncio
            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                for i in range(3):
                    await asyncio.sleep(0.4)
                    await send({"type": "http.response.body",
                                "body": f"s{i}".encode(), "more_body": i < 2})
            """#)
        let fastApp = ASGIAppLoader.execApp(
            #"""
            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"fast", "more_body": False})
            """#)

        let slow = InMemoryASGIClientTransport(app: slowApp)
        let fast = InMemoryASGIClientTransport(app: fastApp)
        let baseURL = URL(string: "http://asgi.local")!
        let mk = { (p: String) in HTTPRequest(method: .get, scheme: "http", authority: "127.0.0.1", path: p) }

        let slowStart = Date()
        let slowTask = Task<[Double], Error> {
            let (_, body) = try await slow.send(mk("/slow"), body: nil, baseURL: baseURL, operationID: "slow")
            var stamps: [Double] = []
            for try await chunk in body ?? HTTPBody() { _ = chunk; stamps.append(Date().timeIntervalSince(slowStart)) }
            return stamps
        }

        // Let the slow stream get mid-drain (past its first 0.4s chunk, parked
        // in a blocking get() with the GIL released).
        try await Task.sleep(nanoseconds: 600_000_000)  // 0.6s

        let unaryStart = Date()
        let (uResp, uBody) = try await fast.send(mk("/fast"), body: nil, baseURL: baseURL, operationID: "fast")
        var uData: [UInt8] = []
        if let uBody { for try await chunk in uBody { uData.append(contentsOf: chunk) } }
        let unaryElapsed = Date().timeIntervalSince(unaryStart)
        let sinceSlowStart = Date().timeIntervalSince(slowStart)

        XCTAssertEqual(uResp.status.code, 200)
        XCTAssertEqual(String(decoding: uData, as: UTF8.self), "fast")
        XCTAssertLessThan(
            unaryElapsed, 0.30,
            "unary took \(unaryElapsed)s — the stream drain serialized the worker")
        XCTAssertLessThan(
            sinceSlowStart, 1.0,
            "unary finished at +\(sinceSlowStart)s — slow stream should still be draining")

        let slowStamps = try await slowTask.value
        XCTAssertEqual(slowStamps.count, 3, "slow stream should emit 3 chunks")
        XCTAssertGreaterThan(slowStamps.last ?? 0, 1.0, "slow stream should really take ~1.2s")
    }

    // MARK: - (d) Cancellation: dropping the stream stops the drain thread

    /// When the consumer drops the response body mid-stream, `onTermination`
    /// fires → `DrainControl.cancel()` wakes the drain thread out of its
    /// blocking `get()` and it exits promptly — far sooner than the app's
    /// 10s sleep. Without this, a cancelled SSE would leak the drain thread for
    /// the lifetime of the stream (WARN-3).
    func testStreamCancellationStopsDrain() async throws {
        let app = ASGIAppLoader.execApp(
            #"""
            import asyncio
            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"first", "more_body": True})
                await asyncio.sleep(10.0)
                await send({"type": "http.response.body", "body": b"never", "more_body": False})
            """#)
        let drainEnded = expectation(description: "drain thread exited after cancellation")
        let transport = InMemoryASGIClientTransport(app: app, onDrainEnd: { drainEnded.fulfill() })

        // Read the first chunk, then let the response body go out of scope.
        func consumeFirstChunkThenDrop() async throws {
            let (resp, body) = try await transport.send(
                HTTPRequest(method: .get, scheme: "http", authority: "127.0.0.1", path: "/sse"),
                body: nil, baseURL: URL(string: "http://asgi.local")!, operationID: "sse")
            XCTAssertEqual(resp.status.code, 200)
            let unwrapped = try XCTUnwrap(body)
            for try await chunk in unwrapped {
                XCTAssertEqual(String(decoding: chunk, as: UTF8.self), "first")
                break
            }
            // resp/body/unwrapped released at return -> stream termination.
        }
        try await consumeFirstChunkThenDrop()

        await fulfillment(of: [drainEnded], timeout: 5.0)
    }
}
#endif