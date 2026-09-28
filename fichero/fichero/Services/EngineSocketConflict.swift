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

    /// What the live engine says of itself on its unauthenticated `/api/health`, to name it in the window.
    struct LiveEngine: Equatable {
        var version: String?
        var pid: Int?
        /// The app the engine runs from (`engine_owner`): a bundle path such as "/Applications/Fichero.app",
        /// or "dev external" for a script-started engine (7c00a47ed).
        var owner: String?
    }

    /// The live engine's version, pid and owning app (`engine_pid`, `engine_owner`); each nil when unsaid.
    @MainActor static func liveEngine(socketPath: String) async -> LiveEngine {
        let client = FicheroClient(transportMode: .uds(path: socketPath))
        guard let response = try? await client.api.healthCheckApiHealthGet(.init()),
              case .ok(let okResponse) = response, let health = try? okResponse.body.json else { return LiveEngine() }
        return LiveEngine(version: health.backendVersion, pid: health.enginePid, owner: health.engineOwner)
    }
}

/// What holds things up in `.portConflict`: port 8765, or another engine on the container socket.
/// Nonisolated: `BackendError.errorDescription` words it too.
nonisolated enum EngineConflict: Equatable, Sendable {
    case port8765
    case socket(pid: Int?, version: String?, owner: String? = nil)

    /// One sentence naming the other engine as far as it is known -- never an invented version or pid.
    var sentence: String {
        switch self {
        case .port8765:
            return "Another process is already using port 8765."
        case .socket(let pid, let version, let owner):
            var named = "Another Fichero engine"
            if let version { named += " (version \(version))" }
            if let pid { named += ", PID \(pid)," }
            if let from = Self.ownerPhrase(owner) { named += " " + from }
            return named + " is already running on this Mac. Fichero will not start a second one over it: "
                + "use that one, or quit the other Fichero first."
        }
    }

    /// Where the other engine runs from, in words: the app bundle's name ("from Fichero.app in
    /// /Applications"), or "started from a script" for "dev external". Nil when it did not say.
    static func ownerPhrase(_ owner: String?) -> String? {
        guard let owner, !owner.isEmpty else { return nil }
        if owner == "dev external" { return "started from a script" }
        let url = URL(fileURLWithPath: owner)
        return "from \(url.lastPathComponent) in \(url.deletingLastPathComponent().path)"
    }
}
