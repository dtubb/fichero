import Darwin
import Foundation

/// Is anything actually serving this UNIX socket? (#4400)
///
/// The app had no answer to that question anywhere — no `unlink`, no
/// `fileExists`, no connect probe against any `.sock` path. A socket file that
/// exists with nothing behind it looked exactly like a live one, so the client
/// dialled it and waited out the readiness budget before reporting something
/// misleading ("no external engine reachable — start it with start_backend.sh",
/// when the engine had in fact been started and had died, leaving its file).
///
/// That is the same failure #4400 was about — the client dialling a socket
/// nobody serves — reached by a different route, so it deserved the same
/// treatment: name the socket and fail immediately rather than time out.
///
/// `connect(2)` on AF_UNIX answers definitively and without waiting: the kernel
/// either finds a listener queued on that inode or it does not. There is no
/// network round trip to time out on, which is what makes fail-fast honest here
/// rather than merely impatient.
enum UDSSocketProbe {

    /// What the kernel says about a socket path. Named `Liveness`, not
    /// `Status`: `Status` is a generated OpenAPI schema name, and shadowing one
    /// is how a hand-rolled type drifts from the contract (#4400).
    enum Liveness: Equatable {
        /// A listener accepted the connection. Says NOTHING about who is
        /// listening or whether it will honour our credentials — see the note
        /// on `requireServedSocket`.
        case listening
        /// The file is there and nothing is accepting on it: a previous engine
        /// died without unlinking. `ECONNREFUSED`.
        case stale
        /// No file at all — no engine has bound this path. `ENOENT`.
        case absent
        /// The path exists but cannot be probed (permissions, not a socket, a
        /// path over the `sun_path` limit). Never treated as absent, because
        /// "I could not look" and "I looked and there was nothing" are
        /// different answers and only one of them means start an engine.
        case unusable(errno: Int32)
    }

    /// Probe `path` without connecting to anything else and without blocking.
    static func liveness(atPath path: String) -> Liveness {
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)

        let capacity = MemoryLayout.size(ofValue: addr.sun_path)
        let bytes = Array(path.utf8)
        // A truncated path would probe a DIFFERENT socket, so refuse rather
        // than silently ask about the wrong one.
        guard bytes.count < capacity else { return .unusable(errno: ENAMETOOLONG) }

        withUnsafeMutablePointer(to: &addr.sun_path) { tuple in
            tuple.withMemoryRebound(to: CChar.self, capacity: capacity) { dst in
                for (offset, byte) in bytes.enumerated() { dst[offset] = CChar(bitPattern: byte) }
                dst[bytes.count] = 0
            }
        }

        let descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else { return .unusable(errno: errno) }
        defer { close(descriptor) }

        let result = withUnsafePointer(to: &addr) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
                Darwin.connect(descriptor, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        if result == 0 { return .listening }

        switch errno {
        case ECONNREFUSED: return .stale
        case ENOENT: return .absent
        default: return .unusable(errno: errno)
        }
    }

    /// The human sentence for a socket that cannot serve us.
    ///
    /// Names the path, because the whole class of bug behind #4400 is a client
    /// and an engine disagreeing about which socket they mean, and a diagnosis
    /// that omits the path cannot show that.
    static func diagnosis(for liveness: Liveness, path: String) -> String? {
        switch liveness {
        case .listening:
            return nil
        case .stale:
            return """
                The engine's socket file is there but nothing is serving it — \
                an engine bound \(path) and exited without cleaning up. \
                Start the engine again.
                """
        case .absent:
            return "No engine is listening on \(path). Start it with scripts/start_backend.sh."
        case .unusable(let code):
            return "Could not probe the engine socket at \(path) (errno \(code))."
        }
    }
}
