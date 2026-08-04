@testable import Fichero
import XCTest

/// #4532 — the app told us the wrong thing about a 403 and cost half an hour
/// of diagnosis.
///
/// Both SSE consumers logged a hardcoded cause on any 403:
///
///     "change-stream denied (403) — no role on library; not retrying"
///     "activity stream denied (403) — no role on library; not retrying"
///
/// The engine was not saying that. With `FICHERO_MULTIUSER=0` the role check
/// is bypassed entirely and cannot produce a 403 at all; the denial that
/// actually fired was the library-path allowlist —
/// `{"detail": "Library path is not in an allowed location or not a .fichero
/// package."}` — for a library sitting in the home folder. The server sent a
/// body explaining exactly what was wrong and the client threw it away in
/// favour of a guess.
///
/// `streamLines` returns the body whatever the status, so the explanation was
/// always in hand. These tests pin that it is read and carried, and that the
/// invented sentence stays gone.
final class StreamDenialAttributionTests: XCTestCase {

    // MARK: - The decoder that replaced the guess

    private func lines(_ values: [String]) -> AsyncThrowingStream<String, any Error> {
        AsyncThrowingStream { continuation in
            for value in values { continuation.yield(value) }
            continuation.finish()
        }
    }

    /// The real denial body, verbatim from the live engine.
    func testExtractsTheEngineSentenceFromADetailBody() async {
        let body = #"{"detail": "Library path is not in an allowed location or not a .fichero package."}"#
        let message = await AccessError.denialMessage(fromBodyLines: lines([body]))

        XCTAssertEqual(message, "Library path is not in an allowed location or not a .fichero package.")
    }

    /// The other real shape: a structured denial carrying a machine code.
    func testFallsBackToReasonThenCodeWhenThereIsNoMessage() async {
        let body = #"{"code": "library_access_denied"}"#
        let message = await AccessError.denialMessage(fromBodyLines: lines([body]))

        XCTAssertEqual(message, "library_access_denied")
    }

    /// A body split across frames still decodes — the transport hands back
    /// lines, and JSON does not have to arrive on one of them.
    func testJoinsMultipleBodyLinesBeforeDecoding() async {
        let message = await AccessError.denialMessage(
            fromBodyLines: lines(["{", #""detail": "nope""#, "}"])
        )
        XCTAssertEqual(message, "nope")
    }

    /// Edge case: not JSON at all. Returning the raw text beats returning
    /// nothing — the engine said something and the user is better served by it.
    func testNonJSONBodyIsReturnedAsRawText() async {
        let message = await AccessError.denialMessage(fromBodyLines: lines(["upstream refused"]))
        XCTAssertEqual(message, "upstream refused")
    }

    /// Edge case: an empty body must produce nil, NOT an empty string — the
    /// caller renders "engine gave no reason", which is still the truth. This
    /// is the whole point: absence of an explanation must not be dressed up as
    /// one.
    func testEmptyBodyYieldsNilRatherThanAFabricatedCause() async {
        let empty = await AccessError.denialMessage(fromBodyLines: lines([]))
        XCTAssertNil(empty)

        let blank = await AccessError.denialMessage(fromBodyLines: lines(["", "   ", "\n"]))
        XCTAssertNil(blank)
    }

    /// Side effect that must not happen: an endless stream must not hang the
    /// reconnect loop. Only ever called on a non-200, but the cap is the thing
    /// standing between a mis-wired call and a wedged service.
    func testDrainIsCappedSoAMisdirectedCallCannotHang() async {
        let endless = AsyncThrowingStream<String, any Error> { continuation in
            for _ in 0..<10_000 { continuation.yield("x") }
            continuation.finish()
        }
        let message = await AccessError.denialMessage(fromBodyLines: endless, maxLines: 4)

        XCTAssertEqual(message, "x\nx\nx\nx", "the drain must stop at maxLines")
    }

    /// A body that errors part-way still yields what arrived. A truncated
    /// explanation beats no explanation.
    func testPartialBodyBeforeAnErrorIsStillUsed() async {
        let failing = AsyncThrowingStream<String, any Error> { continuation in
            continuation.yield("half a reason")
            continuation.finish(throwing: URLError(.networkConnectionLost))
        }
        let message = await AccessError.denialMessage(fromBodyLines: failing)

        XCTAssertEqual(message, "half a reason")
    }

    // MARK: - The invented sentence stays gone

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Services
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    func testNeitherStreamServiceAssertsACauseForA403() throws {
        for path in [
            "Services/LibraryChangeStream.swift",
            "Services/ActivityStreamService.swift"
        ] {
            let source = try Self.appSource(path)

            XCTAssertFalse(
                source.contains("no role on library"),
                """
                \(path) hardcodes a cause for a 403 again (#4532). With \
                multiuser off the role check cannot 403 at all, so this \
                sentence is wrong for the denial that actually fires.
                """
            )
            XCTAssertTrue(
                source.contains("AccessError.denialMessage(fromBodyLines: lines)"),
                "\(path) must read the engine's own explanation out of the response body"
            )
            XCTAssertTrue(
                source.contains("accessDeniedMessage = detail"),
                "\(path) must carry the reason outward so the UI can show it, not just log it"
            )
        }
    }
}
