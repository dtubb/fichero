@testable import Fichero
import Foundation
import Testing

/// Frame-classification, self-echo dedup, connect state and backoff coverage for
/// `LibraryChangeStream` (#1863), driven through the injected `ChangeStreamTransport`
/// seam so no live socket is needed. The stub replays canned SSE frames; the spy
/// consumer records exactly what the classify loop routed.
@MainActor
@Suite("LibraryChangeStream transport")
struct LibraryChangeStreamTransportTests {
    // MARK: - Test doubles

    /// Replays a fixed status + finite list of SSE text lines, then finishes.
    private struct StubTransport: ChangeStreamTransport {
        var status: Int = 200
        var frames: [String]

        func connect(_ request: URLRequest) async throws
            -> (status: Int, lines: AsyncThrowingStream<String, any Error>) {
            let frames = frames
            let lines = AsyncThrowingStream<String, any Error> { continuation in
                for frame in frames { continuation.yield(frame) }
                continuation.finish()
            }
            return (status, lines)
        }
    }

    private final class SpyConsumer: ChangeEventConsumer {
        nonisolated let changeDomains: Set<String>
        var applied: [ChangeEvent] = []
        var resyncCount = 0

        init(domains: Set<String>) { changeDomains = domains }
        func apply(_ event: ChangeEvent) { applied.append(event) }
        func resync() async { resyncCount += 1 }
    }

    private func makeStream(
        frames: [String],
        status: Int = 200,
        windowId: String = "self-window"
    ) -> LibraryChangeStream {
        LibraryChangeStream(
            baseURL: URL(string: "https://example.test:8765")!,
            libraryPath: "/lib",
            windowId: windowId,
            transport: StubTransport(status: status, frames: frames)
        )
    }

    private func dataFrame(type: String, originWindow: String? = nil) -> String {
        // Hand-built JSON — the values are plain identifiers needing no escaping,
        // so this avoids a throwing serializer in the frame factory.
        var fields = ["\"type\":\"\(type)\""]
        if let originWindow { fields.append("\"origin_window\":\"\(originWindow)\"") }
        return "data:{" + fields.joined(separator: ",") + "}"
    }

    // MARK: - Frame classification

    @Test("a data: frame decodes and routes to a matching-domain consumer")
    func dataFrameRoutes() async throws {
        let spy = SpyConsumer(domains: ["entity"])
        let stream = makeStream(frames: [dataFrame(type: "entity.updated")])
        stream.register(spy)

        try await stream.subscribeOnce(resyncOnConnect: false)

        #expect(spy.applied.map(\.type) == ["entity.updated"])
        #expect(stream.isConnected)
        #expect(stream.liveUpdatesUnavailable == false)
    }

    @Test("comment, blank and event: lines are skipped, not routed")
    func nonDataLinesSkipped() async throws {
        let spy = SpyConsumer(domains: ["entity"])
        let stream = makeStream(frames: [
            ": keepalive",
            "",
            "event: ping",
            dataFrame(type: "entity.created")
        ])
        stream.register(spy)

        try await stream.subscribeOnce(resyncOnConnect: false)

        #expect(spy.applied.map(\.type) == ["entity.created"])
    }

    @Test("an undecodable data: frame is dropped without crashing")
    func undecodableFrameDropped() async throws {
        let spy = SpyConsumer(domains: ["entity"])
        let stream = makeStream(frames: [
            "data:{not valid json",
            dataFrame(type: "entity.updated")
        ])
        stream.register(spy)

        try await stream.subscribeOnce(resyncOnConnect: false)

        #expect(spy.applied.map(\.type) == ["entity.updated"])
    }

    // MARK: - Domain filtering

    @Test("an event is only delivered to consumers whose domains include it")
    func domainFiltering() async throws {
        let entitySpy = SpyConsumer(domains: ["entity"])
        let claimSpy = SpyConsumer(domains: ["claim"])
        let stream = makeStream(frames: [dataFrame(type: "claim.updated")])
        stream.register(entitySpy)
        stream.register(claimSpy)

        try await stream.subscribeOnce(resyncOnConnect: false)

        #expect(entitySpy.applied.isEmpty)
        #expect(claimSpy.applied.map(\.type) == ["claim.updated"])
    }

    // MARK: - Self-echo dedup (spec §3.5)

    @Test("a frame originating from this window is dropped (self-echo dedup)")
    func selfEchoDropped() async throws {
        let spy = SpyConsumer(domains: ["entity"])
        let stream = makeStream(
            frames: [dataFrame(type: "entity.updated", originWindow: "self-window")],
            windowId: "self-window"
        )
        stream.register(spy)

        try await stream.subscribeOnce(resyncOnConnect: false)

        #expect(spy.applied.isEmpty)
    }

    @Test("a frame from a different window is still delivered")
    func otherWindowDelivered() async throws {
        let spy = SpyConsumer(domains: ["entity"])
        let stream = makeStream(
            frames: [dataFrame(type: "entity.updated", originWindow: "other-window")],
            windowId: "self-window"
        )
        stream.register(spy)

        try await stream.subscribeOnce(resyncOnConnect: false)

        #expect(spy.applied.map(\.type) == ["entity.updated"])
    }

    // MARK: - Connect state

    @Test("a non-200 status throws and never marks the stream connected")
    func nonOKStatusThrows() async {
        let spy = SpyConsumer(domains: ["entity"])
        let stream = makeStream(frames: [dataFrame(type: "entity.updated")], status: 403)
        stream.register(spy)

        await #expect(throws: (any Error).self) {
            try await stream.subscribeOnce(resyncOnConnect: false)
        }
        #expect(stream.isConnected == false)
        #expect(spy.applied.isEmpty)
    }

    @Test("resyncOnConnect re-fetches every consumer before streaming frames")
    func resyncOnReconnect() async throws {
        let spy = SpyConsumer(domains: ["entity"])
        let stream = makeStream(frames: [dataFrame(type: "entity.updated")])
        stream.register(spy)

        try await stream.subscribeOnce(resyncOnConnect: true)

        #expect(spy.resyncCount == 1)
        #expect(spy.applied.map(\.type) == ["entity.updated"])
    }

    // MARK: - Backoff (pure)

    @Test("backoff doubles from the initial delay and caps at 30s")
    func backoffDoublesAndCaps() {
        let initial = LibraryChangeStream.initialBackoffNanos
        #expect(initial == 1_000_000_000)

        var backoff = initial
        backoff = LibraryChangeStream.nextBackoffNanos(after: backoff)
        #expect(backoff == 2_000_000_000)
        backoff = LibraryChangeStream.nextBackoffNanos(after: backoff)
        #expect(backoff == 4_000_000_000)

        // Well past the ceiling → clamps, never exceeds 30s.
        #expect(LibraryChangeStream.nextBackoffNanos(after: 20_000_000_000) == 30_000_000_000)
        #expect(LibraryChangeStream.nextBackoffNanos(after: 30_000_000_000) == 30_000_000_000)
    }

    @Test("paused pill stays hidden until the second consecutive missed cycle")
    func pausedPillThreshold() {
        #expect(LibraryChangeStream.shouldSurfaceUnavailable(failureCount: 0) == false)
        #expect(LibraryChangeStream.shouldSurfaceUnavailable(failureCount: 1) == false)
        #expect(LibraryChangeStream.shouldSurfaceUnavailable(failureCount: 2) == true)
    }

    // MARK: - No spurious reconnect prompt (#3351)

    @Test("engine reachable: a healthy stream leaves the reconnect pill hidden")
    func reachableEngineHidesPausedPill() async throws {
        // A reachable engine returns 200 and streams a frame, then the stub's
        // finite frame list ends the connection cleanly (a server-side rotation).
        // The reconnect pill must NOT be shown — that clean end is not a failure.
        let stream = makeStream(frames: [dataFrame(type: "entity.updated")])
        #expect(stream.liveUpdatesUnavailable == false, "starts hidden")

        try await stream.subscribeOnce(resyncOnConnect: false)

        #expect(stream.isConnected, "reachable → connected during the stream")
        #expect(stream.liveUpdatesUnavailable == false,
                "reachable engine must never surface a Reconnect prompt (#3351)")
    }

    @Test("a single dropped cycle does not surface the pill (transient settles)")
    func singleTransientDoesNotSurface() {
        // The two-strike debounce: one miss self-heals on the next backoff tick
        // and stays invisible. Before #3351 a clean end pre-incremented the count,
        // so a lone transient could hit the threshold; now only genuine errors do.
        #expect(LibraryChangeStream.shouldSurfaceUnavailable(failureCount: 1) == false)
    }
}
