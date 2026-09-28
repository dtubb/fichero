import FicheroAPIClient
import Foundation

/// Another Fichero engine already answering on the container socket (2026-09-28).
///
/// Every build that runs an engine on this Mac -- the installed app, Dev Embedded, a Dev Local engine
/// started from the shell -- uses ONE socket path in the app container and ONE `.api-key` beside it.
/// A second engine spawned over a live one rebinds the path and rewrites the key under it, and the
/// app then gets 401 on some requests and 200 on others (found when the installed /Applications
/// build started alongside a dev build). So before spawning, a live socket is a CONFLICT, surfaced in
/// the window like a held port -- Use it or Quit (Stop it when the holder's pid is known) -- never a
/// second engine. Pure: the rules live where a test can reach them.
enum EngineSocketConflict {
    enum Decision: Equatable {
        /// Nothing answers on the socket: spawn our engine.
        case spawnOurs
        /// The person chose Use it: adopt the engine that answers (still gated on the authenticated probe).
        case adoptExisting
        /// The person chose Stop it and the holder's pid is known: stop it, then spawn.
        case stopThenSpawn(pid: Int)
        /// No decision yet (or Stop it with no pid to stop): show the conflict in the window.
        case surface
    }

    static func decision(
        socketLive: Bool, holderPID: Int?, pendingChoice: EmbeddedBackendService.PortConflictResolution?
    ) -> Decision {
        guard socketLive else { return .spawnOurs }
        switch pendingChoice {
        case .useIt: return .adoptExisting
        case .stopIt: return holderPID.map { .stopThenSpawn(pid: $0) } ?? .surface
        case nil: return .surface
        }
    }

    /// Whether an engine ANSWERS on `socketPath`: a connect succeeds. A socket file with nothing
    /// listening behind it (an engine that died) is not live -- the spawn clears it as before.
    nonisolated static func isLive(socketPath: String) -> Bool {
        let descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else { return false }
        defer { close(descriptor) }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let pathBytes = Array(socketPath.utf8)
        guard pathBytes.count < MemoryLayout.size(ofValue: address.sun_path) else { return false }
        withUnsafeMutableBytes(of: &address.sun_path) { raw in
            raw.copyBytes(from: pathBytes)
            raw[pathBytes.count] = 0
        }
        let length = socklen_t(MemoryLayout<sockaddr_un>.size)
        return withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(descriptor, $0, length) == 0 }
        }
    }

    /// The live engine's version, from its unauthenticated `/api/health`, to name it in the window; nil
    /// when it does not say. ponytail: its pid and owning app join when the engine's health carries them
    /// (bugs2's half of this fix).
    static func liveEngineVersion(socketPath: String) async -> String? {
        let client = FicheroClient(transportMode: .uds(path: socketPath))
        guard let response = try? await client.api.healthCheckApiHealthGet(.init()),
              case .ok(let okResponse) = response, let health = try? okResponse.body.json else { return nil }
        return health.backendVersion
    }
}

/// What holds things up in `.portConflict`: port 8765, or another engine on the container socket.
/// Nonisolated: `BackendError.errorDescription` words it too.
nonisolated enum EngineConflict: Equatable, Sendable {
    case port8765
    case socket(pid: Int?, version: String?)

    /// One sentence naming the other engine as far as it is known -- never an invented version or pid.
    var sentence: String {
        switch self {
        case .port8765:
            return "Another process is already using port 8765."
        case .socket(let pid, let version):
            var named = "Another Fichero engine"
            if let version { named += " (version \(version))" }
            if let pid { named += ", PID \(pid)," }
            return named + " is already running on this Mac. Fichero will not start a second one over it: "
                + "use that one, or quit the other Fichero first."
        }
    }
}
