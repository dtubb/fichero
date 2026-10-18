@testable import Fichero
import XCTest

/// #3290: pins are keyed per host string, so editing a paired host in Settings
/// leaves the new host with no pin. A non-loopback host that must be pinned then
/// has to be refused, never trusted by default. Source-shape guard.
@MainActor
final class PinFailsClosedAfterHostEditShapeTests: XCTestCase {
    func testUnpinnedEnforcedHostIsCancelled() throws {
        let source = try AppSource.code(
            "../fichero-api-client/Sources/FicheroAPIClient/RemoteCertificatePinning.swift")
        let guardAt = try XCTUnwrap(source.range(of: "guard let expectedSPKIPin = persistedSPKIPin(hostString: hostString) else {"))
        let branch = String(source[guardAt.upperBound...].prefix(700))
        let enforce = try XCTUnwrap(branch.range(of: "guard shouldEnforcePinning(forHost: host) else {"))
        let tail = String(branch[enforce.upperBound...])
        let defaultAt = try XCTUnwrap(tail.range(of: ".performDefaultHandling"))
        let cancelAt = try XCTUnwrap(tail.range(of: ".cancelAuthenticationChallenge"))
        XCTAssertTrue(defaultAt.lowerBound < cancelAt.lowerBound,
                      "only a host that need not be pinned may fall to default handling; an enforced one must cancel")
    }
}
