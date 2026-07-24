import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

#if os(macOS)
extension EmbeddedBackendService {
    /// The two places the nested engine can live, in the order we look (#3749).
    ///
    /// The channels genuinely diverge here and both must keep working from one
    /// binary's worth of source:
    ///   • Contents/Helpers  — the App Store build. TN2206 lists the designated
    ///     code locations (MacOS, Frameworks, Helpers, PlugIns, XPCServices,
    ///     Library); Resources is NOT one of them, and MAS ingestion validation
    ///     is stricter than notarization — an executable .app under Resources is
    ///     an invalid bundle structure. The sandbox spike (#3746) ran the engine
    ///     from Contents/Helpers, so this is demonstrated, not inferred.
    ///   • Contents/Resources — the Developer ID / DMG build, unchanged. It gets
    ///     away with Resources under notarization and is not worth the churn.
    ///
    /// Probing both (rather than an #if) keeps this one code path honest: the
    /// engine is wherever the build actually put it, and a mismatch surfaces as
    /// the existing backendAppNotFound error rather than a silent wrong guess.
    static let engineBundleSubpaths = [
        "Contents/Helpers/Fichero Engine.app",
        "Contents/Resources/Fichero Engine.app"
    ]

    // MARK: - Private Helpers

    // Promoted from `private` to internal: called by spawnAndAdoptEmbeddedEngine
    // in the Lifecycle extension file.
    func launchEmbeddedBackend() async throws {
        let bundlePath = Bundle.main.bundlePath
        let backendAppPath = try resolveBackendAppPath(bundlePath: bundlePath)
        let executablePath = "\(backendAppPath)/Contents/MacOS/Fichero Engine"
        logger.info("Embedded engine: \(backendAppPath)")

        // Port pre-flight (orphan sweep by the DMG build; a loopback probe under
        // the sandbox) already ran in resolvePortConflict() before we got here —
        // including in DEBUG (#2863). By this point the port is ours to bind.

        let (accessMaterial, publicBaseURL) = try await prepareAccessMaterial(executablePath: executablePath)

        // Persist the SPKI pin for every host the engine binds to. The
        // remote-access cert is also served on loopback, so pins match (#2611).
        try persistSPKIPins(accessMaterial, publicBaseURL: publicBaseURL)

        logger.info("Launching backend process: \(executablePath)")

        // Use Process for direct process control - much simpler than NSWorkspace
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        // Mirror start_backend.sh HTTPS args (#2603/#2604/#2611).
        process.arguments = [
            "--ssl-certfile", accessMaterial.certificatePath,
            "--ssl-keyfile", accessMaterial.keyPath
        ]
        // Mint the bootstrap token and a launch nonce HERE, in the app, and
        // pass both to the spawn (#2862). The app is authoritative: it writes
        // the token file itself (below) instead of racing to read whatever the
        // engine mints, and it can issue an authenticated readiness probe the
        // instant the engine binds. The nonce lets readiness prove the engine
        // answering /api/health is the child we launched.
        let bootstrapToken = Self.generateSecret()
        let launchNonce = Self.generateSecret()
        expectedLaunchNonce = launchNonce

        process.environment = buildChildEnvironment(
            bootstrapToken: bootstrapToken,
            launchNonce: launchNonce,
            accessMaterial: accessMaterial,
            publicBaseURL: publicBaseURL
        )

        // Diagnostic (#757): capture engine stdout/stderr to a tail-able file
        // in ~/Library/Logs/ so Release-build engine failures surface instead
        // of getting silently swallowed.
        let logHandle = try openEngineLogHandle()
        process.standardOutput = logHandle
        process.standardError = logHandle

        // Write the token file the app minted (#2862/#2863). We NEVER pre-delete
        // it: an empty/absent .api-key would make every request 401 until the
        // engine got around to writing one — the blank-window-with-401s bug.
        // Writing our own token (mode 0600) means the app and the engine agree
        // from the first request, with no window where the two disagree.
        if let tokenURL = AuthTokenMiddleware.bootstrapTokenFileURL() {
            Self.writeBootstrapTokenFile(bootstrapToken, at: tokenURL)
        }

        // If the engine dies on its own (crash, import error, port lost), flip
        // to .failed with the tail of engine.log instead of leaving the UI
        // stuck on a spinner or a blank window (#2863). Skipped when WE asked
        // it to stop. terminationHandler runs off the main actor, so hop back.
        intentionalStop = false
        process.terminationHandler = makeTerminationHandler()

        // Launch the process
        try process.run()

        let pid = process.processIdentifier
        // The gap between "engine spawn requested" and this marker is everything
        // the app does BEFORE the engine gets to start: the port pre-flight and
        // the TLS material prep (#3936/#3928). That cost was invisible.
        LaunchProfile.milestone("engine process launched", detail: "pid \(pid)")
        logger.info("Backend process launched successfully (PID: \(pid))")

        // Store PID and process reference
        backendPID = pid
        logger.info("Tracking embedded backend PID: \(pid)")
    }

    /// Locate the embedded engine bundle (#3749: Contents/Helpers for MAS,
    /// Contents/Resources for Developer ID/DMG). Throws `.backendAppNotFound`
    /// with the same diagnostic logging the inline check used to do.
    private func resolveBackendAppPath(bundlePath: String) throws -> String {
        // Bundle is named "Fichero Engine.app" (briefcase formal_name =
        // "Fichero Engine"), bundle ID app.fichero.fichero.engine.
        let candidates = Self.engineBundleSubpaths.map { "\(bundlePath)/\($0)" }
        guard let backendAppPath = candidates.first(where: {
            FileManager.default.fileExists(atPath: "\($0)/Contents/MacOS/Fichero Engine")
        }) else {
            let executablePath = candidates[0] + "/Contents/MacOS/Fichero Engine"
            logger.error("Backend executable not found at: \(executablePath)")
            // Debug builds skip the "Embed Fichero Engine" phase (it only runs in
            // Release), so in a Debug ⌘R the engine is expected to be running
            // externally on :8765. If it isn't, that's this path.
            let message = "Debug: start the engine first — fichero-engine/scripts/start_backend.sh. "
                + "Release: briefcase build macOS --app engine (in fichero-engine/), then rebuild."
            logger.error("\(message, privacy: .public)")
            throw BackendError.backendAppNotFound
        }
        return backendAppPath
    }

    /// Prepare the TLS material for either the loopback-only or hosted
    /// (remote-access) case, returning the material plus the public URL when
    /// hosting is enabled.
    private func prepareAccessMaterial(
        executablePath: String
    ) async throws -> (accessMaterial: RemoteAccessTLSMaterial, publicBaseURL: URL?) {
        if RemoteAccessConfig.hostingEnabled {
            guard let url = RemoteAccessConfig.publicBaseURL else {
                throw BackendError.launchFailed(
                    NSError(
                        domain: "EmbeddedBackendService",
                        code: 1,
                        userInfo: [NSLocalizedDescriptionKey: "Remote access needs a reachable HTTPS URL."]
                    )
                )
            }
            let accessMaterial = try await prepareRemoteAccessTLSMaterial(
                executablePath: executablePath,
                publicBaseURL: url
            )
            return (accessMaterial, url)
        } else {
            let accessMaterial = try await prepareLocalAccessTLSMaterial(executablePath: executablePath)
            return (accessMaterial, nil)
        }
    }

    private func persistSPKIPins(_ accessMaterial: RemoteAccessTLSMaterial, publicBaseURL: URL?) throws {
        try RemoteCertificatePinning.persistHostedBackendSPKIPin(
            accessMaterial.spkiPin,
            hostString: EngineConfig.defaultHostString
        )
        if let publicBaseURL {
            try RemoteCertificatePinning.persistHostedBackendSPKIPin(
                accessMaterial.spkiPin,
                hostString: publicBaseURL.absoluteString
            )
        }
    }

    /// Build the child env from the app's environment with every inherited
    /// FICHERO_* stripped (#3933). The engine's security posture — auth on/off
    /// (FICHERO_DISABLE_AUTH), bind surface (FICHERO_LAN_HOST/FICHERO_BIND_HOST)
    /// — is decided ENTIRELY by the FICHERO_* keys set below, never by a stray
    /// one in the launching shell. `FICHERO_DISABLE_AUTH=1 open Fichero.app`
    /// must not spawn an auth-less engine. Non-FICHERO vars (PATH, HOME,
    /// locale, dyld/xpc, …) are inherited unchanged — the bundled interpreter
    /// needs them and none influence engine auth or bind. This fails closed
    /// for any FICHERO_* added later: unknown ones are dropped until
    /// explicitly set here.
    private func buildChildEnvironment(
        bootstrapToken: String,
        launchNonce: String,
        accessMaterial: RemoteAccessTLSMaterial,
        publicBaseURL: URL?
    ) -> [String: String] {
        var environment = Self.childEnvironmentBase(inheriting: ProcessInfo.processInfo.environment)
        // Engine watches this PID and self-terminates if we die without a
        // chance to call .stop() (e.g., SIGKILL). Belt-and-braces with the
        // applicationWillTerminate path.
        environment["FICHERO_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        environment["FICHERO_BOOTSTRAP_TOKEN"] = bootstrapToken
        environment["FICHERO_LAUNCH_NONCE"] = launchNonce
        environment["FICHERO_TLS_CERTFILE"] = accessMaterial.certificatePath
        environment["FICHERO_TLS_KEYFILE"] = accessMaterial.keyPath
        environment["FICHERO_TLS_SPKI_HASH"] = accessMaterial.spkiPin
        environment["FICHERO_BIND_HOST"] = accessMaterial.bindHost
        // Bind the embedded engine on the same AF_UNIX socket the app client
        // dials over UDS (EngineConfig.transportMode → .uds). Only this spawn
        // path (releaseEmbedded) sets it; Debug/remote/inert never spawn and
        // keep TCP+TLS. The engine's Lane E honors FICHERO_UDS_PATH and binds
        // UDS-only (no TCP port, no TLS) when it is present.
        environment["FICHERO_UDS_PATH"] = EngineConfig.udsSocketPath
        if let publicBaseURL {
            // Reuse the same env contract as RemoteAccessConfig so the
            // remote-access launch path cannot drift from the helper (#2611).
            environment.merge(
                RemoteAccessConfig.launchEnvironment(
                    for: publicBaseURL,
                    material: accessMaterial,
                    bonjourEnabled: RemoteAccessConfig.bonjourEnabled
                ),
                uniquingKeysWith: { $1 }
            )
        }
        environment["FICHERO_FEATURE_TIER"] =
            FeatureManager.shared.activeBuildTier.environmentValue
        environment["FICHERO_MULTIUSER"] = EngineConfig.multiuserEnabled ? "1" : "0"
        #if os(macOS)
        // Sandboxed (Mac App Store) engine: hand it the security-scoped bookmarks for
        // the user's libraries (#3747). A dynamic Powerbox grant does NOT inherit into
        // a child process, so without these the engine cannot open a library in
        // ~/Documents at all — a plain open() is denied and DuckDB fails with it.
        // Nil (so the var is absent) when there is nothing to send: every
        // non-sandboxed DMG run, where the engine already has filesystem access.
        if let bookmarks = FolderAccessManager.shared.engineBookmarkPayload() {
            environment["FICHERO_LIBRARY_BOOKMARKS"] = bookmarks
        }
        #endif
        return environment
    }

    private func openEngineLogHandle() throws -> FileHandle {
        let logURL = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero/engine.log")
        try? FileManager.default.createDirectory(
            at: logURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        return try FileHandle(forWritingTo: logURL)
    }

    private func makeTerminationHandler() -> @Sendable (Process) -> Void {
        { [weak self] proc in
            // Decode BOTH fields: for `.uncaughtSignal`, `terminationStatus` is
            // the SIGNAL NUMBER, not an exit code — reading only the status
            // reports a SIGPIPE (signal 13) as the false "exit code 13" (#dev).
            let status = proc.terminationStatus
            let reason = proc.terminationReason
            let description = Self.describeTermination(status: status, reason: reason)
            let wasSignal = reason == .uncaughtSignal
            let wasSigpipe = wasSignal && status == SIGPIPE
            Task { @MainActor [weak self] in
                guard let self, !self.intentionalStop else { return }

                // A SIGPIPE is the engine being told a client hung up mid-write
                // (a cancelled probe, a connection dropped after a 401) — NOT a
                // crash. The engine now ignores SIGPIPE (see engine __main__),
                // so this should not fire; if an older engine build still dies
                // this way, log it honestly and do NOT feed it to the crash
                // restart loop, whose "start already in flight" churn (#3108)
                // is the stuck-on-launch symptom. The readiness/heartbeat loop
                // re-drives the connection on its own.
                if wasSigpipe {
                    logger.notice(
                        "Engine received SIGPIPE (client closed mid-write); not a crash, not restarting"
                    )
                    return
                }

                logger.error("Engine terminated unexpectedly (\(description, privacy: .public))")

                let tail = Self.tailEngineLog(lines: 20)
                if Self.shouldSurfaceUnexpectedExitImmediately(status: self.status, isStarting: self.isStarting) {
                    self.status = .failed
                    self.errorMessage = Self.unexpectedExitDiagnosis(description: description, tail: tail)
                    return
                }

                // #18: auto-restart a crashed embedded engine so a transient
                // crash self-heals with no manual Retry — but stop if it keeps
                // dying, to avoid a hot restart loop.
                guard self.shouldAutoRestartAfterCrash() else {
                    self.status = .failed
                    self.errorMessage = "The engine keeps crashing (\(description)) — "
                        + "stopped auto-restarting after \(Self.crashLoopMaxRestarts) attempts "
                        + "in \(Int(Self.crashLoopWindow))s."
                        + (tail.isEmpty ? "" : "\n\n\(tail)")
                    return
                }

                logger.info("Auto-restarting engine after unexpected termination (\(description, privacy: .public))")
                self.status = .starting
                do {
                    try await self.start()
                } catch {
                    let tail = Self.tailEngineLog(lines: 20)
                    self.status = .failed
                    self.errorMessage = "The engine terminated (\(description)) and could not be "
                        + "restarted: \(error.localizedDescription)"
                        + (tail.isEmpty ? "" : "\n\n\(tail)")
                }
            }
        }
    }

    static func shouldSurfaceUnexpectedExitImmediately(status: BackendStatus, isStarting: Bool) -> Bool {
        if isStarting { return true }
        if case .starting = status { return true }
        return false
    }

    static func unexpectedExitDiagnosis(description: String, tail: String) -> String {
        "The engine exited unexpectedly (\(description))."
            + (tail.isEmpty ? "" : "\n\n\(tail)")
    }

    /// Human-readable termination cause. For `.uncaughtSignal`, `status` is the
    /// signal number (e.g. 13 = SIGPIPE), NOT an exit code — decode it as a
    /// signal so logs and the failure banner never mislabel a signal as an exit
    /// code. For `.exit`, `status` is the real process exit code.
    nonisolated static func describeTermination(status: Int32, reason: Process.TerminationReason) -> String {
        switch reason {
        case .uncaughtSignal:
            let name = signalName(status)
            return name.map { "signal \(status) \($0)" } ?? "signal \(status)"
        case .exit:
            return "exit code \(status)"
        @unknown default:
            return "status \(status)"
        }
    }

    /// Best-effort symbolic name for a termination signal (e.g. 13 → "SIGPIPE").
    nonisolated private static func signalName(_ signalNumber: Int32) -> String? {
        guard let cName = strsignal(signalNumber) else { return nil }
        let text = String(cString: cName)
        // strsignal returns a human phrase ("Broken pipe"); prefer the SIGxxx
        // mnemonic for the ones we actually reason about, fall back to the phrase.
        switch signalNumber {
        case SIGPIPE: return "SIGPIPE"
        case SIGKILL: return "SIGKILL"
        case SIGTERM: return "SIGTERM"
        case SIGSEGV: return "SIGSEGV"
        case SIGABRT: return "SIGABRT"
        case SIGBUS: return "SIGBUS"
        case SIGILL: return "SIGILL"
        default: return text.isEmpty ? nil : text
        }
    }
}
#endif
