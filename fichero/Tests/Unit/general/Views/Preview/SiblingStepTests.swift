@testable import Fichero
import CoreGraphics
import FicheroAPIClient
import ImageIO
import UniformTypeIdentifiers
import XCTest

/// #5462: a Preview swipe to the next item was slow.
///
/// These run the swipe's own step (`SiblingStep`, what `ContentView.commitSiblingStep` calls)
/// through the REAL `StorageService` and `RenditionService`, with only the HTTP transport replaced
/// by an engine that answers the routes the canvas reads after a fixed delay (`latency`), and
/// RECORDS every request. Timing is measured and printed, never asserted (a timing assertion on a
/// shared build machine is flaky); what is asserted is the WORK: how many engine round-trips stand
/// between a swipe and the image, and which writes happen in which order.
///
/// Each page has an original and a background-removed rendition, as the maintainer's pages do: the
/// canvas lands on background-removed, so it reads the rendition list, the edit chain and that
/// rendition's bytes before it can show anything.
@MainActor
final class SiblingStepTests: XCTestCase {
    private final class Engine: URLProtocol {
        nonisolated(unsafe) static var latency: TimeInterval = 0.025
        nonisolated(unsafe) static var png = Data()
        /// Each test's own host: a warm left running by an earlier test (it is never cancelled, by
        /// design) still reaches this engine, but is not counted against the next test.
        nonisolated(unsafe) static var host = ""
        private static let lock = NSLock()
        nonisolated(unsafe) private static var log: [String] = []

        static var requests: [String] { lock.withLock { log } }
        static func reset() { lock.withLock { log = [] } }

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.host?.hasSuffix("swipe.test") == true
        }
        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let path = request.url?.path ?? ""
            if request.url?.host == Self.host { Self.lock.withLock { Self.log.append(path) } }
            let parts = path.split(separator: "/").map(String.init)
            let (body, type) = Self.answer(parts)
            DispatchQueue.global().asyncAfter(deadline: .now() + Self.latency) { [self] in
                let response = HTTPURLResponse(
                    url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": type]
                )!
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: body)
                client?.urlProtocolDidFinishLoading(self)
            }
        }

        override func stopLoading() {}

        /// `/api/documents/{id}/renditions`, `…/renditions/{rid}/content`, `/api/images/{id}/edits`,
        /// `/api/storage/display/{id}`.
        private static func answer(_ parts: [String]) -> (Data, String) {
            if parts.count == 4, parts[1] == "documents", parts[3] == "renditions" {
                let id = parts[2]
                let json = """
                {"count":2,"items":[
                 {"id":"\(id)-o","document_id":"\(id)","role":"original","path":"o.png","is_primary":true},
                 {"id":"\(id)-bg","document_id":"\(id)","role":"background_removed","path":"bg.png"}]}
                """
                return (Data(json.utf8), "application/json")
            }
            if parts.count == 4, parts[1] == "images", parts[3] == "edits" {
                let json = #"{"document_id":"\#(parts[2])","operations":[],"updated_at":"2026-10-05T00:00:00Z"}"#
                return (Data(json.utf8), "application/json")
            }
            if parts.last == "content" { return (png, "image/png") }
            return (png, "image/jpeg")
        }
    }

    private var storage: StorageService!
    private var renditions: RenditionService!
    private let pages = (0 ..< 6).map { Document(id: "p\($0)", docType: .file, fileType: .image, name: "\($0).jpg") }

    override func setUp() {
        super.setUp()
        EngineConfig.defaults.removeObject(forKey: ZoomableImagePreview.stickyRenditionRoleKey)
        Engine.latency = 0.025
        Engine.png = Self.png()
        Engine.host = "t\(UUID().uuidString.prefix(8).lowercased()).swipe.test"
        Engine.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Engine.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://\(Engine.host)")!,
            libraryPath: "/tmp/swipe.fichero",
            session: URLSession(configuration: configuration)
        )
        storage = StorageService(ficheroClient: client)
        renditions = RenditionService(ficheroClient: client)
    }

    private static func png() -> Data {
        let context = CGContext(
            data: nil, width: 8, height: 8, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )!
        let out = NSMutableData()
        let dest = CGImageDestinationCreateWithData(out, UTType.png.identifier as CFString, 1, nil)!
        CGImageDestinationAddImage(dest, context.makeImage()!, nil)
        CGImageDestinationFinalize(dest)
        return out as Data
    }

    private func ms(since start: ContinuousClock.Instant) -> Double {
        let elapsed = ContinuousClock.now - start
        return Double(elapsed.components.attoseconds) / 1e15 + Double(elapsed.components.seconds) * 1000
    }

    /// Polls for up to 30 s: the test host's main actor is busy with the app's own launch for
    /// seconds at a time, so a short wait measures the host, not the step.
    private func waitUntil(_ condition: () -> Bool) async {
        for _ in 0 ..< 3000 where !condition() { try? await Task.sleep(for: .milliseconds(10)) }
    }

    /// The measurement behind #5462. The swipe used to warm its neighbours with the BASE display
    /// image, but the canvas shows the preferred rendition: so the "warmed" neighbour was still cold
    /// and EVERY swipe paid three engine round-trips in a row (list, edit chain, bytes) before its
    /// image could show, each one also waiting its turn on the main actor. Warming what the canvas
    /// shows leaves nothing to fetch.
    func testWarmingTheBaseDisplayLeftTheNeighbourColdWarmingWhatTheCanvasShowsLeavesNoFetch() async {
        // The old warm (still the iOS and reader page-turn warm): the base display image.
        await storage.prefetchDisplayImages(["p1"])
        XCTAssertFalse(SiblingStep.isWarm("p1", storage: storage, renditions: renditions),
                       "the base display is not what the canvas shows for a page with a background-removed rendition")
        Engine.reset()
        await SiblingStep.warm("p1", storage: storage, renditions: renditions)
        XCTAssertEqual(Engine.requests, ["/api/documents/p1/renditions", "/api/images/p1/edits",
                                         "/api/documents/p1/renditions/p1-bg/content"],
                       "a base-warmed neighbour still costs the list, the edit chain and the bytes, in a row")

        // The new warm: what the canvas shows.
        await SiblingStep.warm(["p2"], storage: storage, renditions: renditions)
        XCTAssertTrue(SiblingStep.isWarm("p2", storage: storage, renditions: renditions))
        Engine.reset()
        await SiblingStep.warm("p2", storage: storage, renditions: renditions)
        XCTAssertEqual(Engine.requests, [], "a neighbour warmed with what the canvas shows needs no fetch")
    }

    /// A swipe to a warmed neighbour shows it in the SAME turn, before any engine request: the
    /// Preview's item changes before the Inspector's work (all of it engine round-trips) can
    /// complete. The canvas then reads the list and the bytes again and finds both in memory — no
    /// store whose input did not change is reloaded.
    func testASwipeToAWarmNeighbourShowsItAtOnceAndTheCanvasFetchesNothing() async {
        let step = SiblingStep()
        var shown: [String] = []
        step.commit(to: pages[1], neighbours: ["p2", "p0", "p3"], storage: storage, renditions: renditions) {
            shown.append($0.id)
        }
        await waitUntil { shown == ["p1"] }
        await waitUntil { SiblingStep.isWarm("p2", storage: storage, renditions: renditions) }
        XCTAssertTrue(SiblingStep.isWarm("p2", storage: storage, renditions: renditions),
                      "landing on p1 warms the next page with the image the canvas will show")

        Engine.reset()
        let start = ContinuousClock.now
        step.commit(to: pages[2], neighbours: ["p3", "p1", "p4", "p0"], storage: storage, renditions: renditions) {
            shown.append($0.id)
        }
        // No await between the swipe and this line: the item changed in the swipe's own turn.
        XCTAssertEqual(shown, ["p1", "p2"], "a warm neighbour shows in the swipe's own turn")
        XCTAssertNil(step.pending)
        XCTAssertEqual(Engine.requests, [], "nothing was asked of the engine before the item changed")
        print("#5462 swipe to a warm neighbour: shown after \(ms(since: start)) ms")

        // What the canvas does on the new item (StorageDisplayImageCanvas.loadImageOnce).
        Engine.reset()
        await renditions.load(documentId: "p2")
        _ = try? await renditions.contentData(documentId: "p2", renditionId: "p2-bg")
        XCTAssertFalse(Engine.requests.contains { $0.hasPrefix("/api/documents/p2") || $0.hasPrefix("/api/images/p2") },
                       "the canvas reloads nothing the step already holds: \(Engine.requests)")
    }

    /// Two quick swipes are two steps. A swipe during a cold page's hold used to step from the item
    /// still on screen, so it landed on the same page as the first. Now the new swipe shows the held
    /// step at once (`flush`) and cancels its hold: the held page is shown exactly once.
    ///
    /// And the hold is a CAP: a cold page lands when it runs out, long before its warm is done. The
    /// old hold raced the two in a task group, which waits for every child, so it waited for the
    /// whole warm (here 3 × 5 s) however short the cap.
    func testASwipeDuringAHoldShowsTheHeldStepAndCancelsItsHold() async {
        Engine.latency = 5  // the warm needs 15 s: only the 140 ms cap can land the step
        let step = SiblingStep()
        var shown: [String] = []
        let show: (Document) -> Void = { shown.append($0.id) }
        step.commit(to: pages[1], neighbours: [], storage: storage, renditions: renditions, show: show)
        XCTAssertEqual(step.pending?.id, "p1", "a cold page holds")
        XCTAssertEqual(shown, [])

        step.flush(show: show)  // the second swipe arrives
        XCTAssertEqual(shown, ["p1"], "the held step shows at once")
        step.commit(to: pages[2], neighbours: [], storage: storage, renditions: renditions, show: show)
        await waitUntil { shown.count == 2 }
        XCTAssertEqual(shown, ["p1", "p2"], "the cold page landed at the cap")
        XCTAssertFalse(Engine.requests.contains("/api/documents/p2/renditions/p2-bg/content"),
                       "it landed before its warm got past the list: the cap did not wait for the warm")
        try? await Task.sleep(for: .milliseconds(300))
        XCTAssertEqual(shown, ["p1", "p2"], "p1's cancelled hold never shows it a second time")
    }
}
