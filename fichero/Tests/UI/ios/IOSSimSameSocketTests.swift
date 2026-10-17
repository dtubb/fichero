#if os(iOS)
import Darwin
import XCTest

/// spec: ui-test-harness §`harness.ios-sim-same-socket` (#4782). A Simulator shares the Mac's
/// filesystem, so a runner on it must be able to `connect()` the AF_UNIX socket the Mac-side
/// `UITestEngineHarness` binds. The tester starts the harness engine on the Mac and passes the path
/// as `TEST_RUNNER_FICHERO_FORCE_UDS_PATH`; without it this skips (never green by default).
final class IOSSimSameSocketTests: XCTestCase {

    func testSimulatorCanConnectTheHostEngineSocket() throws {
        guard let path = ProcessInfo.processInfo.environment["FICHERO_FORCE_UDS_PATH"], !path.isEmpty else {
            throw XCTSkip("no host engine socket handed to the simulator run (TEST_RUNNER_FICHERO_FORCE_UDS_PATH)")
        }
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        XCTAssertGreaterThanOrEqual(fd, 0, "socket() failed: errno \(errno)")
        defer { close(fd) }
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let capacity = MemoryLayout.size(ofValue: addr.sun_path)
        XCTAssertLessThan(path.utf8.count, capacity, "socket path too long for sockaddr_un: \(path)")
        withUnsafeMutableBytes(of: &addr.sun_path) { buffer in
            _ = path.withCString { strncpy(buffer.baseAddress!.assumingMemoryBound(to: CChar.self), $0, capacity - 1) }
        }
        let result = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        XCTAssertEqual(result, 0, "connect() to \(path) failed: errno \(errno)")
    }
}
#endif
