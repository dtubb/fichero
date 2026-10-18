@testable import Fichero
import XCTest

/// #3290: an iOS device build can never reach the host's `.api-key`. The only
/// code that builds that path outside the app container is `hostHomeTokenFileURL`,
/// and it must stay inside the simulator-only branch. Source-shape guard.
@MainActor
final class IOSBootstrapTokenGuardTests: XCTestCase {
    func testHostHomeBootstrapPathIsSimulatorOnly() throws {
        let source = try AppSource.text(
            "../fichero-api-client/Sources/FicheroAPIClient/AuthTokenMiddleware.swift")
        let fn = try XCTUnwrap(source.range(of: "private static func hostHomeTokenFileURL"))
        let body = String(source[fn.upperBound...].prefix(900))
        let sim = try XCTUnwrap(body.range(of: "#if targetEnvironment(simulator) && !os(macOS)"))
        let host = try XCTUnwrap(body.range(of: "SIMULATOR_HOST_HOME"))
        let els = try XCTUnwrap(body.range(of: "#else"))
        XCTAssertTrue(sim.lowerBound < host.lowerBound && host.lowerBound < els.lowerBound,
                      "SIMULATOR_HOST_HOME must be read only inside the simulator branch")
        XCTAssertEqual(source.components(separatedBy: "SIMULATOR_HOST_HOME").count - 1, 1,
                       "a second SIMULATOR_HOST_HOME reader is a new bootstrap-token touchpoint")
    }
}
