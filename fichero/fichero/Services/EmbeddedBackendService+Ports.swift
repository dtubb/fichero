import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

extension EmbeddedBackendService {
    /// Process-lifecycle ownership derived from one pure mapping (#4057).
    enum EngineOwnership: Equatable {
        /// The app spawned or otherwise owns the local engine process; app quit
        /// must terminate it.
        case ownedEmbedded
        /// The app adopted a user/developer-managed engine and must leave it
        /// running on quit.
        case adoptedExternal

        var isExternalBackend: Bool { self == .adoptedExternal }
    }

    /// Pure ownership table (#4057): strategy + transport + port outcome → whether
    /// the app owns the process lifecycle. Transport matters because a Debug dev
    /// engine reached via UDS/in-process is this app's local development engine and
    /// must die with the app; ordinary HTTPS Debug / remote / user-approved port
    /// adoption remains external and is left running.
    nonisolated static func engineOwnership(
        strategy: EngineConfig.EngineProvisioningStrategy,
        transportMode: TransportMode,
        portResolution: PortResolution?
    ) -> EngineOwnership {
        switch strategy {
        case .releaseEmbedded:
            return portResolution == .adoptExisting ? .adoptedExternal : .ownedEmbedded
        case .debugExternal:
            switch transportMode {
            case .uds:
                return .ownedEmbedded
            #if os(macOS)
            case .inMemory:
                return .ownedEmbedded
            #endif
            case .https:
                return .adoptedExternal
            }
        case .configuredRemote, .iosCompanion, .inert:
            return .adoptedExternal
        }
    }

    /// How the port pre-flight resolved (#2863).
    /// Promoted from `private` to internal: `resolvePortConflict` (this file)
    /// returns it and `spawnAndAdoptEmbeddedEngine` (Lifecycle extension) switches
    /// on it — a cross-file reference a private nested type can't satisfy.
    enum PortResolution: Equatable { case spawnOurs, adoptExisting }

    /// Is port 8765 ours? Only on the HTTPS transport (#4400). The pre-flight
    /// predates UDS: a `.releaseEmbedded` engine binds a socket in the app
    /// container — "no TCP port, no TLS" (`__main__.py`) — so in a shipping
    /// build 8765 is somebody else's, and adopting its holder strands the
    /// client on a socket nobody serves. `PortPreflightTransportTests` has the
    /// full dead end.
    nonisolated static func portPreflightApplies(transportMode: TransportMode) -> Bool {
        switch transportMode {
        case .https: return true
        case .uds: return false          // container socket; 8765 is not ours
        #if os(macOS)
        case .inMemory: return false     // no socket and no port to conflict on
        #endif
        }
    }

    /// The three port-conflict outcomes (#3111), separated from the lsof/kill
    /// syscalls so every branch is unit-testable.
    enum PortConflictAction: Equatable {
        /// Port is free, or the user chose Stop it (the caller SIGTERMs first).
        case spawn
        /// The user chose Use it — adopt the existing engine (still auth-gated).
        case adopt
        /// A foreign process holds the port and the user hasn't decided yet —
        /// surface the in-window `portConflict(pid)` phase.
        case surfacePhase(pid: Int)
    }

    /// Pure port-conflict decision (#3111): given the current holder PID (nil =
    /// free) and the pending user choice, decide spawn / adopt / surface-the-phase.
    /// The impure `resolvePortConflict` wraps this with the orphan sweep + kill.
    /// No silent adoption and no silent kill — a foreign holder always needs an
    /// explicit choice (#2863).
    static func portConflictAction(
        holderPID: Int?,
        pendingChoice: PortConflictResolution?
    ) -> PortConflictAction {
        guard let pid = holderPID else { return .spawn }
        guard let choice = pendingChoice else { return .surfacePhase(pid: pid) }
        switch choice {
        case .stopIt: return .spawn
        case .useIt: return .adopt
        }
    }

    // MARK: - Orphan-engine cleanup

    #if os(macOS)
    // Compiled OUT of the App Store build (#3749). Everything from here to the
    // matching #endif enumerates or signals processes that are not our children
    // — pgrep, ps -E, kill() on a foreign PID. Under App Sandbox none of it
    // works, and shipping it dead would still put /usr/bin/pgrep and /bin/ps in
    // a binary the reviewer greps. The MAS build manages only the Process handle
    // it owns; see resolvePortConflict().
    #if !FICHERO_APP_STORE
    /// SIGTERM a "Fichero Server" subprocess left over from a previous run of
    /// **this** app that didn't get a chance to call .stop() (e.g. SIGKILL,
    /// crash, or force-quit). Called off the main actor before spawning a new engine
    /// so the new spawn can bind port 8765 cleanly.
    ///
    /// SAFETY (#2079): a host can BOTH serve a shared engine (for remote users)
    /// AND run the app. Killing local engines by name pattern would SIGTERM that
    /// shared engine out from under its users. We therefore never kill by name
    /// alone — only engines that provably belong to this app's lineage. The rule,
    /// in priority order, per candidate engine PID:
    ///   • configured to use a custom/remote host  → we own NO local engine;
    ///     skip the whole sweep (early return below).
    ///   • engine has no recorded `FICHERO_PARENT_PID`  → started independently
    ///     of any app (a shared/manually-run engine) — SPARE it.
    ///   • recorded parent is still alive and isn't us  → a DIFFERENT live owner
    ///     is using it — SPARE it.
    ///   • recorded parent is us, or is dead  → a genuine orphan of a Fichero
    ///     app run that no longer exists — KILL it.
    ///
    /// Correctness over aggressiveness: it is better to leave a real orphan
    /// running (the user can kill it) than to SIGTERM a shared engine others
    /// depend on. When in doubt we spare.
    nonisolated static func terminateOrphanEngines() {
        if EngineConfig.usesCustomHost {
            logger.info("Custom/remote engine host configured — skipping orphan sweep (no local engine is ours to kill)")
            return
        }

        let thisAppPID = ProcessInfo.processInfo.processIdentifier

        let pgrep = Process()
        pgrep.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        pgrep.arguments = ["-f", "Fichero Server.app/Contents/MacOS"]
        let pipe = Pipe()
        pgrep.standardOutput = pipe
        pgrep.standardError = FileHandle.nullDevice
        guard (try? pgrep.run()) != nil else { return }
        pgrep.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        guard let output = String(data: data, encoding: .utf8) else { return }
        for line in output.split(separator: "\n") {
            guard let pid = pid_t(line.trimmingCharacters(in: .whitespaces)) else { continue }

            guard let parent = engineParentPID(pid) else {
                logger.info("Engine PID \(pid) has no FICHERO_PARENT_PID — not app-spawned, sparing")
                continue
            }
            if parent != thisAppPID, isProcessAlive(parent) {
                logger.info("Engine PID \(pid) owned by live app PID \(parent) — sparing")
                continue
            }
            logger.info("Terminating orphan engine PID \(pid) (parent \(parent) is this app or dead)")
            kill(pid, SIGTERM)
        }
    }

    /// Read the `FICHERO_PARENT_PID` recorded in a candidate engine's
    /// environment (set by `launchEmbeddedBackend` on spawn). `ps -E` appends a
    /// process's environment to its command-line output, so we can recover the
    /// owner without a pidfile. Returns nil when the var is absent (engine
    /// started independently of any app) or the environment can't be read.
    nonisolated private static func engineParentPID(_ pid: pid_t) -> pid_t? {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/ps")
        task.arguments = ["-E", "-ww", "-o", "command=", "-p", String(pid)]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        guard (try? task.run()) != nil else { return nil }
        task.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        guard let output = String(data: data, encoding: .utf8),
              let range = output.range(of: "FICHERO_PARENT_PID=") else { return nil }
        let digits = output[range.upperBound...].prefix { $0.isNumber }
        return pid_t(digits)
    }

    /// True if `pid` names a live process — exists, even if owned by another
    /// user we lack permission to signal. `kill(_, 0)` returns 0 when the
    /// process exists and is signalable, or fails with EPERM when it exists but
    /// belongs to a different owner. Both mean "alive" for orphan-kill purposes.
    nonisolated private static func isProcessAlive(_ pid: pid_t) -> Bool {
        if pid <= 0 { return false }
        return kill(pid, 0) == 0 || errno == EPERM
    }
    #endif  // !FICHERO_APP_STORE — end of the non-child process machinery

    nonisolated static func waitForPortToClear(_ port: UInt16, timeout: TimeInterval) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let inUse = await Task.detached(priority: .userInitiated) {
                Self.portInUse(port)
            }.value
            if !inUse { return }
            try? await Task.sleep(for: .milliseconds(100))
        }
    }

    nonisolated private static func portInUse(_ port: UInt16) -> Bool {
        #if FICHERO_APP_STORE
        return portIsAcceptingConnections(port)
        #else
        return pidOnPort(port) != nil
        #endif
    }

    /// Is something LISTENing on `port`? A plain loopback TCP connect — the only
    /// port probe available under App Sandbox (#3749).
    ///
    /// `lsof` enumerates other processes' file descriptors, which the sandbox
    /// does not permit; it would fail and report the port "free", the engine
    /// would spawn, and the bind would fail with a confusing error. A connect to
    /// 127.0.0.1 is covered by `com.apple.security.network.client`, tells us the
    /// one thing we actually need ("is the port taken?"), and tells us nothing
    /// about WHO holds it — which is correct, because a sandboxed app has no
    /// business knowing, and cannot signal them anyway.
    nonisolated static func portIsAcceptingConnections(_ port: UInt16) -> Bool {
        let sock = socket(AF_INET, SOCK_STREAM, 0)
        guard sock >= 0 else { return false }
        defer { close(sock) }

        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")

        return withUnsafePointer(to: &addr) { raw in
            raw.withMemoryRebound(to: sockaddr.self, capacity: 1) { addrPtr in
                connect(sock, addrPtr, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0
            }
        }
    }

    /// PID of the owned Debug-local engine, if ownership says this app must tear
    /// it down. UDS dev engines are started by the Xcode pre-action, not
    /// `launchEmbeddedBackend()`, so this bridges that adopted-but-owned path.
    static func ownedDebugEnginePID(transportMode: TransportMode) async -> pid_t? {
        #if FICHERO_APP_STORE
        return nil
        #else
        switch transportMode {
        case .uds(let path):
            return await pidOnUnixSocket(path)
        #if os(macOS)
        case .inMemory:
            return nil
        #endif
        case .https:
            return nil
        }
        #endif
    }

    #if !FICHERO_APP_STORE
    private static func pidOnUnixSocket(_ path: String) async -> pid_t? {
        await Task.detached(priority: .userInitiated) {
            pidOnUnixSocketSync(path)
        }.value
    }

    nonisolated private static func pidOnUnixSocketSync(_ path: String) -> pid_t? {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        task.arguments = ["-t", path]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        guard (try? task.run()) != nil else { return nil }
        task.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        let first = String(data: data, encoding: .utf8)?
            .split(separator: "\n").first
            .map(String.init)?
            .trimmingCharacters(in: .whitespaces)
        return first.flatMap { pid_t($0) }
    }

    /// PID of the process LISTENing on `port`, or nil if the port is free.
    ///
    /// Shells out to lsof, so it is compiled out of the App Store build (#3749);
    /// the sandbox permits no view of other processes' descriptors. MAS uses
    /// portIsAcceptingConnections() above, which answers "is it taken?" without
    /// asking "by whom?".
    nonisolated private static func pidOnPort(_ port: UInt16) -> pid_t? {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        task.arguments = ["-i", ":\(port)", "-sTCP:LISTEN", "-t"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        guard (try? task.run()) != nil else { return nil }
        task.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        let first = String(data: data, encoding: .utf8)?
            .split(separator: "\n").first
            .map(String.init)?
            .trimmingCharacters(in: .whitespaces)
        return first.flatMap { pid_t($0) }
    }
    #endif

    // Port pre-flight (#2863/#3111). Sweep our own orphans; if the port is
    // then STILL held by a process we can't claim, the user must choose — but
    // the decision now happens IN-WINDOW (`portConflict` phase), not in a
    // pre-window `NSAlert`. When no choice has been made yet, throw
    // `.portConflict(pid)` so the connection view can render Stop it / Use it /
    // Quit; the button sets `pendingPortConflictResolution` and retries, and
    // this consumes it exactly once. Never silently adopts or silently kills.
    // Promoted from `private` to internal: called by spawnAndAdoptEmbeddedEngine
    // in the Lifecycle extension file.
    func resolvePortConflict() async throws -> PortResolution {
        #if FICHERO_APP_STORE
        // App Sandbox (#3749): we manage ONLY our own child. There is no orphan
        // sweep, no holder PID and no kill, for two independent reasons:
        //   • Unavailable — pgrep / ps -E / lsof enumerate other processes, and
        //     kill() signals them. The sandbox permits none of that; the calls
        //     fail or return nothing, so a sweep would be theatre.
        //   • Unacceptable — an app that pokes at processes it does not own reads
        //     badly against guideline 2.4.5 even where it happens to work.
        // So: probe the port the one way the sandbox allows, and if it is taken,
        // let the USER decide (Use it / Quit) instead of silently adopting or
        // silently killing. 2.4.5(iii) stays satisfied by the existing design —
        // stop() SIGTERMs our own child on quit, and the engine self-terminates
        // when FICHERO_PARENT_PID dies.
        // #4400, and MAS is where the dead end was worst: no holder PID means
        // no "Stop it", so Quit was the only way out of the adopt-then-time-out
        // loop. No sweep to preserve here, so this guard is the whole pre-flight.
        guard Self.portPreflightApplies(transportMode: EngineConfig.transportMode) else {
            return .spawnOurs
        }
        guard Self.portIsAcceptingConnections(8765) else { return .spawnOurs }

        if pendingPortConflictResolution == .useIt {
            // Adoption is still gated on the authenticated readiness probe
            // downstream — an auth-rejecting squatter lands in authRejected,
            // never ready (#2864/#3111).
            pendingPortConflictResolution = nil
            return .adoptExisting
        }
        // pid is genuinely unknowable here, so it is reported as nil rather than
        // guessed. The in-window phase drops "Stop it" and offers Use it / Quit.
        pendingPortConflictResolution = nil
        throw BackendError.portConflict(pid: nil)
        #else
        // The sweep runs on EVERY transport, deliberately: an engine this app
        // spawned in a previous session is ours to reap whichever way it was
        // reached, and reaping it is what frees a stale socket (#4400).
        await Task.detached(priority: .userInitiated) {
            Self.terminateOrphanEngines()
        }.value
        // Below here is all about 8765, which a UDS engine never binds.
        guard Self.portPreflightApplies(transportMode: EngineConfig.transportMode) else {
            return .spawnOurs
        }
        await Self.waitForPortToClear(8765, timeout: 3.0)
        let holder = await Task.detached(priority: .userInitiated) {
            Self.pidOnPort(8765).map(Int.init)
        }.value

        switch Self.portConflictAction(holderPID: holder, pendingChoice: pendingPortConflictResolution) {
        case .surfacePhase(let pid):
            // No decision yet → surface the in-window portConflict phase (#3111);
            // pendingPortConflictResolution stays nil for the user to set.
            throw BackendError.portConflict(pid: pid)
        case .adopt:
            // Adoption stays gated on the authenticated readiness probe
            // downstream — an auth-rejecting squatter lands in authRejected,
            // never ready (#2864/#3111).
            pendingPortConflictResolution = nil
            return .adoptExisting
        case .spawn:
            // Stop it: SIGTERM (then SIGKILL) the foreign holder before binding.
            // Skipped when the port was already free (no pending choice).
            if pendingPortConflictResolution == .stopIt, let pid = holder.map({ pid_t($0) }) {
                kill(pid, SIGTERM)
                await Self.waitForPortToClear(8765, timeout: 5.0)
                if await Task.detached(priority: .userInitiated, operation: { Self.portInUse(8765) }).value {
                    kill(pid, SIGKILL)
                    await Self.waitForPortToClear(8765, timeout: 2.0)
                }
            }
            pendingPortConflictResolution = nil
            return .spawnOurs
        }
        #endif
    }
    #endif
}
