import Darwin
@testable import Fichero
import Foundation
import Testing

/// A socket file that exists with nothing behind it must be distinguishable
/// from a live one (#4400).
///
/// The app had no way to tell: no `unlink`, no `fileExists`, no connect probe
/// against any `.sock` path anywhere in `fichero/fichero/**`. So a dead
/// engine's leftover socket looked exactly like a working one, the client
/// dialled it, waited out the readiness budget, and then reported "no external
/// engine reachable — start it with start_backend.sh" — which is wrong twice
/// over: the engine HAD been started, and the socket is right there.
///
/// These bind real sockets in a temp directory rather than faking the kernel,
/// because the whole value of the probe is that `connect(2)` gives a
/// definitive answer and a stub could only restate what I assumed it does.
struct UDSSocketProbeTests {

    // MARK: - The three answers

    @Test("a served socket reads as listening")
    func aServedSocketIsListening() throws {
        let harness = try SocketHarness()
        defer { harness.tearDown() }

        #expect(UDSSocketProbe.liveness(atPath: harness.path) == .listening)
    }

    /// The case the app could not see. The file survives; the listener does
    /// not — exactly what an engine that died without unlinking leaves behind.
    @Test("a socket file whose listener has gone reads as stale, not as listening")
    func anAbandonedSocketIsStale() throws {
        let harness = try SocketHarness()
        defer { harness.tearDown() }

        harness.closeListener()

        #expect(FileManager.default.fileExists(atPath: harness.path))
        #expect(UDSSocketProbe.liveness(atPath: harness.path) == .stale)
    }

    @Test("a path no engine ever bound reads as absent")
    func anUnboundPathIsAbsent() {
        let path = NSTemporaryDirectory() + "fichero-never-bound-\(UUID().uuidString).sock"

        #expect(!FileManager.default.fileExists(atPath: path))
        #expect(UDSSocketProbe.liveness(atPath: path) == .absent)
    }

    /// "I could not look" is not "I looked and there was nothing" — only one of
    /// those means start an engine, and collapsing them is the silent-fallback
    /// shape this codebase rules out.
    @Test("an unprobeable path is unusable, never absent")
    func anUnprobeablePathIsNotAbsent() {
        let overlong = "/tmp/" + String(repeating: "x", count: 200) + ".sock"

        let liveness = UDSSocketProbe.liveness(atPath: overlong)

        #expect(liveness != .absent)
        #expect(liveness != .listening)
        if case .unusable = liveness {} else {
            Issue.record("expected .unusable, got \(liveness)")
        }
    }

    // MARK: - What the user is told

    /// Every failing answer names the socket. The bug class behind #4400 is a
    /// client and an engine disagreeing about which socket they mean, and a
    /// diagnosis that omits the path cannot show that.
    @Test("every failure diagnosis names the socket path")
    func failureDiagnosesNameThePath() throws {
        let path = "/tmp/fichero-diagnosis.sock"
        let failures: [UDSSocketProbe.Liveness] = [.stale, .absent, .unusable(errno: EACCES)]

        for liveness in failures {
            let message = try #require(UDSSocketProbe.diagnosis(for: liveness, path: path))
            #expect(message.contains(path), "\(liveness) omitted the socket path")
        }
    }

    /// A served socket produces no diagnosis at all — nil is what lets
    /// `requireServedSocket` return and hand over to the authenticated probe.
    @Test("a listening socket produces no diagnosis")
    func aListeningSocketHasNoDiagnosis() {
        #expect(UDSSocketProbe.diagnosis(for: .listening, path: "/tmp/x.sock") == nil)
    }

    /// Stale and absent must not read the same. They call for different actions
    /// — "your engine died, start it again" versus "nothing was ever here" —
    /// and the old single timeout message conflated them.
    @Test("a stale socket and an absent one say different things")
    func staleAndAbsentAreDistinguished() throws {
        let path = "/tmp/fichero-diagnosis.sock"

        let stale = try #require(UDSSocketProbe.diagnosis(for: .stale, path: path))
        let absent = try #require(UDSSocketProbe.diagnosis(for: .absent, path: path))

        #expect(stale != absent)
    }

    // MARK: - It narrows nothing

    /// The safety property, and the reason this is not a weakened fail-closed
    /// path: the probe can only REJECT. `.listening` yields no diagnosis, so
    /// `requireServedSocket` returns and the caller runs the same authenticated
    /// readiness probe it always did — the launch nonce and the token still
    /// decide whether the responder is ours. A successful `connect(2)` is
    /// evidence of nothing except that waiting would have been pointless in a
    /// different way.
    @Test("the probe can only reject; it never admits anything")
    func theProbeOnlyEverRejects() throws {
        // The one status that proceeds is the one that has been connected to.
        #expect(UDSSocketProbe.diagnosis(for: .listening, path: "/tmp/x.sock") == nil)

        let guardSource = try AppSource.text("Services/EmbeddedBackendService+SocketGuard.swift")
        // The guard may only ever fail the launch. Nothing in it marks the
        // service ready or short-circuits the authenticated readiness verdict.
        #expect(!guardSource.contains("status = .running"))
        #expect(!guardSource.contains("lastReadiness"))
        #expect(guardSource.contains("throw BackendError.backendAppNotFound"))
    }

    /// A non-UDS transport is not this probe's business, so it must pass
    /// through untouched — an HTTPS engine has no socket file to be stale.
    @Test("the guard is scoped to UDS and ignores every other transport")
    func nonUDSTransportsAreUntouched() throws {
        let guardSource = try AppSource.text("Services/EmbeddedBackendService+SocketGuard.swift")
        #expect(guardSource.contains("guard case let .uds(path) = transportMode else { return }"))
    }

    // MARK: - Support

    /// A real listening AF_UNIX socket, and the ability to abandon it.
    private struct SocketHarness {
        let path: String
        private let descriptor: Int32

        init() throws {
            path = NSTemporaryDirectory() + "fichero-probe-\(UUID().uuidString.prefix(8)).sock"
            descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
            guard descriptor >= 0 else { throw ProbeTestError.socketFailed(errno) }

            var addr = sockaddr_un()
            addr.sun_family = sa_family_t(AF_UNIX)
            let bytes = Array(path.utf8)
            let capacity = MemoryLayout.size(ofValue: addr.sun_path)
            withUnsafeMutablePointer(to: &addr.sun_path) { tuple in
                tuple.withMemoryRebound(to: CChar.self, capacity: capacity) { dst in
                    for (offset, byte) in bytes.enumerated() { dst[offset] = CChar(bitPattern: byte) }
                    dst[bytes.count] = 0
                }
            }

            let bound = withUnsafePointer(to: &addr) { pointer in
                pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
                    bind(descriptor, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_un>.size))
                }
            }
            guard bound == 0 else { throw ProbeTestError.bindFailed(errno) }
            guard listen(descriptor, 1) == 0 else { throw ProbeTestError.listenFailed(errno) }
        }

        /// Close the listener but LEAVE the file — the exact state an engine
        /// that died without unlinking leaves on disk.
        func closeListener() { close(descriptor) }

        func tearDown() {
            close(descriptor)
            try? FileManager.default.removeItem(atPath: path)
        }
    }

    private enum ProbeTestError: Error {
        case socketFailed(Int32)
        case bindFailed(Int32)
        case listenFailed(Int32)
    }
}
