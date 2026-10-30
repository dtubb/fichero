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
    // matching #endif enumerates or signals processes that are not our children.
    //
    // This is BINARY-CONTENT POLICY, not a disguised "am I sandboxed" check —
    // do NOT convert it to SandboxEnvironment.isSandboxed in a flag sweep: a
    // runtime guard would put the pgrep/ps strings back into the binary App
    // Review greps. check_mas_flag_containment.py allowlists exactly this file.
    // (Whether these branches still WORK inside the now-sandboxed dev app is a
    // separate, open runtime question — see the issue filed 2026-08-08.)
    // — pgrep, ps -E, kill() on a foreign PID. Under App Sandbox none of it
    // works, and shipping it dead would still put /usr/bin/pgrep and /bin/ps in
    // a binary the reviewer greps. The MAS build manages only the Process handle
    // it owns; see resolvePortConflict().
    #if !FICHERO_APP_STORE
    /// End the "Fichero Server" helpers an earlier run of this app left behind (spec
    /// `engine.stale-engines-ended-at-launch`; supersedes the #2079 rule that read `FICHERO_PARENT_PID` from each
    /// candidate's environment with `ps -E`). Called off the main actor before spawning, so the new engine can bind.
    ///
    /// SAFETY, the whole policy in `StaleEngineSweep.pidsToEnd` (pure, tested): only a process whose executable is a
    /// `Fichero Server.app` helper inside a `Fichero*.app`, by its real path (`proc_pidpath`), owned by this user, and an ORPHAN (its parent is launchd or gone). A helper whose
    /// parent is alive — this app's own engine, another running copy of the app, one started from a shell — is spared,
    /// and so is every uvicorn/python dev engine (not a bundle): the maintainer's external dev engine is never touched.
    /// When in doubt we spare. SIGTERM, then `TerminationDeadlinePolicy.quit` (2 s) and SIGKILL.
    nonisolated static func terminateOrphanEngines() {
        if EngineConfig.usesCustomHost {
            logger.info("Custom/remote engine host configured — skipping orphan sweep (no local engine is ours to kill)")
            return
        }
        let table = readProcessTable()
        guard !table.isEmpty else {
            logger.error("Stale-engine sweep skipped: could not read the process table")
            return
        }
        let ownPID = ProcessInfo.processInfo.processIdentifier
        let chosen = StaleEngineSweep.pidsToEnd(table: table, currentUID: getuid(), ownPID: ownPID)
            .compactMap { pid in table.first { $0.pid == pid } }
        guard !chosen.isEmpty else { return }
        // Identity is re-read right before EACH signal: a pid is reused once its process dies.
        func signalIfStillTheSame(_ fact: StaleEngineSweep.ProcessFact, _ signal: Int32) {
            guard fact.pid > 1,
                  StaleEngineSweep.isStillTheSame(fact, now: readProcessFact(pid: fact.pid)) else { return }
            kill(fact.pid, signal)
        }
        func isGone(_ fact: StaleEngineSweep.ProcessFact) -> Bool {
            !StaleEngineSweep.isStillTheSame(fact, now: readProcessFact(pid: fact.pid))
        }
        for fact in chosen { signalIfStillTheSame(fact, SIGTERM) }
        let started = Date()
        var escalated = false
        let policy = TerminationDeadlinePolicy.quit
        while true {
            let allGone = chosen.allSatisfy(isGone)
            switch policy.action(elapsed: Date().timeIntervalSince(started), childHasExited: allGone, hasEscalated: escalated) {
            case .replyNow:
                let ended = chosen.filter(isGone).map(\.pid)
                logger.info("Ended \(ended.count) stale Fichero Server process(es) from an earlier run: \(ended.map(String.init).joined(separator: ", "), privacy: .public)")
                StaleEngineSweep.record(ended: ended)
                return
            case .escalateToSIGKILL:
                escalated = true
                for fact in chosen { signalIfStillTheSame(fact, SIGKILL) }
            case .waitMore:
                Thread.sleep(forTimeInterval: policy.pollInterval)
            }
        }
    }

    /// Every process now running, by `libproc` (the kernel's own answer: the real executable path, not `ps`'s argv[0]).
    /// Empty when the table cannot be read (a sandbox that denies it): then nothing is ended.
    nonisolated private static func readProcessTable() -> [StaleEngineSweep.ProcessFact] {
        let capacity = Int(proc_listallpids(nil, 0))
        guard capacity > 0 else { return [] }
        var pids = [pid_t](repeating: 0, count: capacity + 64)
        let count = Int(proc_listallpids(&pids, Int32(pids.count * MemoryLayout<pid_t>.size)))
        guard count > 0 else { return [] }
        return pids.prefix(count).compactMap { $0 > 0 ? readProcessFact(pid: $0) : nil }
    }

    /// pid -> (parent, owner, real executable path), or nil when the process is gone or cannot be read.
    nonisolated private static func readProcessFact(pid: pid_t) -> StaleEngineSweep.ProcessFact? {
        var info = proc_bsdinfo()
        let infoSize = Int32(MemoryLayout<proc_bsdinfo>.size)
        guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, infoSize) == infoSize else { return nil }
        var path = [CChar](repeating: 0, count: 4096)
        guard proc_pidpath(pid, &path, UInt32(path.count)) > 0 else { return nil }
        let executablePath = String(cString: path)
        return StaleEngineSweep.ProcessFact(
            pid: pid, parentPID: Int32(info.pbi_ppid), uid: info.pbi_uid, executablePath: executablePath,
            recordedParentPID: StaleEngineSweep.isFicheroServerHelper(executablePath: executablePath)
                ? recordedParentPID(pid: pid) : nil
        )
    }

    /// `FICHERO_PARENT_PID` from the process's environment (`KERN_PROCARGS2`, same-user processes only); nil when it
    /// cannot be read, which spares the process.
    nonisolated private static func recordedParentPID(pid: pid_t) -> Int32? {
        var mib: [Int32] = [CTL_KERN, KERN_PROCARGS2, pid]
        var size = 0
        guard sysctl(&mib, 3, nil, &size, nil, 0) == 0, size > 0 else { return nil }
        var buffer = [UInt8](repeating: 0, count: size)
        guard sysctl(&mib, 3, &buffer, &size, nil, 0) == 0 else { return nil }
        return StaleEngineSweep.recordedParentPID(procArgs: Array(buffer.prefix(size)))
    }

    /// The orphan sweep as ITS OWN named, awaited seam (#4896, spec:
    /// `engine.orphan-sweep-precedes-spawn-decision`). f9a737d5f's regression
    /// (ed436c69a) was not "the call site forgot to await" in the abstract —
    /// it was this exact `.value` dropped from this exact detached-task await.
    /// Naming the seam means a future edit has to touch a function whose only
    /// job is "await the kill enumeration", not an inline expression buried in
    /// `resolvePortConflict`'s default argument. `terminate` is injectable so a
    /// test can prove the AWAIT itself — not just that some sweep was called —
    /// without a real pgrep/ps/kill enumeration.
    nonisolated static func awaitedOrphanSweep(
        terminate: @escaping @Sendable () -> Void = { EmbeddedBackendService.terminateOrphanEngines() }
    ) async {
        await Task.detached(priority: .userInitiated) {
            LaunchProfile.milestone("orphan engine sweep starts (off-main)")
            terminate()
            LaunchProfile.milestone("orphan engine sweep finished (off-main)")
        }.value
    }

    #else
    /// App Sandbox: no orphan sweep (see `resolvePortConflict`). Kept only so
    /// that function's default argument compiles in the App Store build.
    nonisolated static func awaitedOrphanSweep() async {}
    #endif  // !FICHERO_APP_STORE — end of the non-child process machinery

    /// Whether this build starts its engine ahead of the first window (#5228). Not the App Store
    /// build: it may not sweep or signal other processes (#3749), so its ordinary pre-flight decides.
    /// The flag lives here, the one file allowed to read it (check_mas_flag_containment).
    nonisolated static var launchesAheadOfTheWindow: Bool {
        #if FICHERO_APP_STORE
        false
        #else
        true
        #endif
    }

    /// The orphan sweep, callable from either build: a no-op in the App Store build, which has none.
    nonisolated static func sweepOrphanEnginesIfAllowed() {
        #if !FICHERO_APP_STORE
        terminateOrphanEngines()
        #endif
    }

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
    /// - Parameters:
    ///   - sweep: The orphan-engine sweep, injectable so a test can prove the
    ///     ORDER (sweep completes before a spawn decision is returned) without
    ///     a real pgrep/ps/kill enumeration. Defaults to the production sweep,
    ///     unchanged for every real caller (#4896, spec:
    ///     `engine.orphan-sweep-precedes-spawn-decision`).
    ///   - transportMode: The transport the port pre-flight checks against.
    ///     Defaults to the real ambient `EngineConfig.transportMode`; injectable
    ///     so a test can pick a mode where the pre-flight doesn't apply (`.uds`,
    ///     `.inMemory`) and so exercise the sweep-ordering guarantee with no
    ///     port/pid syscalls at all.
    func resolvePortConflict(
        sweep: () async -> Void = {
            // The sweep machinery is compiled out of the App Store binary (#3749).
            #if !FICHERO_APP_STORE
            await EmbeddedBackendService.awaitedOrphanSweep()
            #endif
        },
        transportMode: TransportMode = EngineConfig.transportMode
    ) async throws -> PortResolution {
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
        // Not the port (UDS, in-memory): a live engine on the container socket -- the installed app's, a dev
        // build's -- is a conflict, never a second engine (`liveSocketResolution`). The sandbox cannot learn or
        // stop the holder's pid, so no Stop it here.
        guard Self.portPreflightApplies(transportMode: transportMode) else {
            return try await liveSocketResolution(for: transportMode) ?? .spawnOurs
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
        //
        // AWAITED on purpose (#4690 review, 2026-09-18): the sweep kills any
        // engine whose FICHERO_PARENT_PID is THIS app — which is only safe
        // while none of ours exists yet. Briefly made fire-and-forget, it
        // could land after our own spawn and SIGTERM the engine we just
        // started. The pgrep+ps round trip is not in the measured launch cost.
        await sweep()
        LaunchProfile.milestone("orphan engine sweep done")
        // Below here is all about 8765, which a UDS engine never binds. A UDS engine instead checks its socket,
        // AFTER the sweep (which frees a socket an orphan of OURS held): a live engine still answering there is
        // somebody else's -- the installed app's, a dev build's -- and is never given a second.
        guard Self.portPreflightApplies(transportMode: transportMode) else {
            let resolution = try await liveSocketResolution(for: transportMode) ?? .spawnOurs
            LaunchProfile.milestone("engine socket checked")
            return resolution
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

extension EmbeddedBackendService {
    /// `resolveLiveSocket` for a UDS transport; nil for any other (nothing to check). The live engine's
    /// pid is used (for Stop it) only where the app may signal another process: never in the App Store build.
    func liveSocketResolution(for transportMode: TransportMode) async throws -> PortResolution? {
        guard case .uds(let path) = transportMode else { return nil }
        #if FICHERO_APP_STORE
        return try await resolveLiveSocket(path, mayStop: false)
        #else
        return try await resolveLiveSocket(path, mayStop: true)
        #endif
    }

    /// The socket half of the pre-flight (`EngineSocketConflict`): nil when nothing answers (go on and
    /// spawn), the resolution when the person chose, or a `socketInUse` throw so the window asks -- naming
    /// the other engine's version and, where it may be stopped, its pid.
    func resolveLiveSocket(_ path: String, mayStop: Bool) async throws -> PortResolution? {
        guard await Task.detached(priority: .userInitiated, operation: { EngineSocketConflict.isLive(socketPath: path) }).value
        else { return nil }
        let other = await EngineSocketConflict.liveEngine(socketPath: path)
        let holderPID = mayStop ? other.pid : nil
        switch EngineSocketConflict.decision(
            socketLive: true, holderPID: holderPID, pendingChoice: pendingPortConflictResolution,
            contractDiffers: other.contractDiffers
        ) {
        case .spawnOurs:
            return nil
        case .adoptExisting:
            pendingPortConflictResolution = nil
            return .adoptExisting
        case .stopThenSpawn(let pid):
            pendingPortConflictResolution = nil
            #if !FICHERO_APP_STORE
            // Stop it, and wait for the socket to fall silent: an engine spawned over a live one refuses to
            // start (7c00a47ed), so spawning early would only fail the other way.
            kill(pid_t(pid), SIGTERM)
            for _ in 0..<50 where EngineSocketConflict.isLive(socketPath: path) {
                try? await Task.sleep(nanoseconds: 100_000_000)
            }
            if EngineSocketConflict.isLive(socketPath: path) { kill(pid_t(pid), SIGKILL) }
            #endif
            return nil
        case .surface:
            pendingPortConflictResolution = nil
            throw BackendError.socketInUse(
                path: path, pid: holderPID, version: other.version, owner: other.owner,
                contractDiffers: other.contractDiffers)
        }
    }
}
