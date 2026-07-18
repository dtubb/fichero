import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

// swiftlint:disable file_length type_body_length

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

/// True when this process is hosting an XCTest bundle. Detected via the XCTest
/// runtime class, which is loaded into the host the moment the test bundle is
/// injected (before `main`), so it's reliable regardless of how the host was
/// launched — unlike the `XCTest*` env vars, which don't always propagate.
///
/// Used to neutralize app-boot side effects during tests: the host must not
/// launch a backend (it would race / fatally terminate via showBackendError)
/// or open the user's real libraries. The integration harness (EngineHarness)
/// owns engine lifecycle and seeds its own disposable library.
func isRunningXCTests() -> Bool {
    if NSClassFromString("XCTestCase") != nil { return true }
    let env = ProcessInfo.processInfo.environment
    return env["XCTestConfigurationFilePath"] != nil || env["XCTestBundlePath"] != nil
}

// `isUITesting()` / `uiTestSupportDirectory()` live in UITestSupport.swift (#1230).

/// Manages the embedded Python backend lifecycle
@MainActor
@Observable
final class EmbeddedBackendService {
    var status: BackendStatus = .stopped
    var errorMessage: String?

    // Plumbing, not observed UI state — exclude from @Observable tracking, and
    // `nonisolated(unsafe)` so the nonisolated Swift-6 `deinit` can read it
    // (only mutated on the main actor; set only on the embedded-spawn path).
    @ObservationIgnored nonisolated(unsafe) private var backendPID: pid_t?
    private var isExternalBackend = false  // Track if using external vs embedded backend
    var isUsingExternalBackend: Bool { isExternalBackend }
    /// The FICHERO_LAUNCH_NONCE we passed to the engine we spawned (#2862).
    /// Readiness verifies /api/health echoes this exact value, proving the
    /// responder is the child we launched — not a stale process on the port.
    /// nil when we adopted an external engine (we didn't spawn it, so there's
    /// no nonce to match).
    private(set) var expectedLaunchNonce: String?
    private var backendURL: URL {
        // Own-engine traffic stays on loopback, never the advertised public URL (#2604).
        EngineConfig.host
    }

    enum BackendStatus {
        case stopped
        case starting
        case running
        case failed
    }

    /// Whether a `connectBackend` trigger should ATTACH to the already-established
    /// app-level connection instead of re-running the connect+auth sequence
    /// (#3394/#3407). The main WindowGroup's `.task` fires once per window/tab, so
    /// without this every new window would flip the shared status back to
    /// `.starting` and re-probe/re-auth — the visible reconnect churn. True only
    /// when the backend is already connected AND this isn't an explicit Retry
    /// (`restart`), which must always re-run. Pure so window-lifecycle reuse is
    /// unit-testable without a live engine.
    static func shouldReuseExistingConnection(
        restart: Bool,
        status: BackendStatus,
        isBackendReady: Bool
    ) -> Bool {
        guard !restart, isBackendReady else { return false }
        if case .running = status { return true }
        return false
    }

    /// Outcome of an authenticated readiness probe (#2862) — now the shared
    /// `EngineReadiness` (#3106), verified by the one `EngineReadinessProbe`.
    typealias ReadinessResult = EngineReadiness

    /// The most recent readiness outcome, for #2864's diagnosis UI.
    private(set) var lastReadiness: ReadinessResult?

    /// Set true when WE initiate a stop (stop()), so the process
    /// terminationHandler doesn't misread an intentional shutdown as a crash
    /// and flip status to .failed (#2863).
    private var intentionalStop = false

    /// True while a start()/respawn is in flight. Guards against a second
    /// `retry()` spawning a duplicate engine or racing the first probe (#3108):
    /// a retry while starting is a no-op. Because `start()` is @MainActor, the
    /// guard+set at the top run without interleaving up to the first `await`,
    /// so concurrent retries deterministically see this true and bounce.
    private(set) var isStarting = false

    /// How many `start()` calls passed the re-entrancy guard — the spawn-attempt
    /// counter the concurrency-stress test asserts stays at 1 under N rapid
    /// retries (#3108).
    private(set) var startAttemptsPassedGuard = 0

    /// How the port pre-flight resolved (#2863).
    private enum PortResolution { case spawnOurs, adoptExisting }

    /// The user's in-window decision for a foreign :8765 holder (#3111): Stop it
    /// (SIGTERM + respawn) or Use it (adopt, still gated on the authenticated
    /// probe). Quit is a pure UI action (user-chosen terminate), so it isn't
    /// modelled here. Set by the connection view's buttons before a retry;
    /// `resolvePortConflict` consumes it exactly once. nil → surface the
    /// portConflict phase instead of a pre-window NSAlert.
    enum PortConflictResolution { case stopIt, useIt }
    var pendingPortConflictResolution: PortConflictResolution?

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

    // MARK: - Lifecycle

    /// The provisioning strategy the most recent `start()` acted on (#3109),
    /// so the mode is inspectable rather than re-derived. nil before first start.
    private(set) var lastProvisioningStrategy: EngineConfig.EngineProvisioningStrategy?

    /// Start the embedded backend
    func start() async throws {
        // One spawn per host at a time (#3108): a retry fired while a start is
        // already in flight is a no-op, so N rapid retries never spawn a second
        // engine or race the first readiness probe.
        guard !isStarting else {
            logger.info("start() ignored — a start/retry is already in flight (#3108)")
            return
        }
        isStarting = true
        startAttemptsPassedGuard += 1
        defer { isStarting = false }

        // The provisioning mode is decided ONCE from explicit inputs (#3109) and
        // consumed here — no scattered #if DEBUG / usesCustomHost / preview
        // re-derivation. Loopback-only bind + pinned HTTPS are unchanged in every
        // mode (they live in launchEmbeddedBackend / the readiness probe).
        let strategy = EngineConfig.engineProvisioningStrategy()
        lastProvisioningStrategy = strategy
        logger.info("Engine provisioning strategy: \(String(describing: strategy), privacy: .public) (#3109)")

        switch strategy {
        case .inert:
            await adoptInertHostForPreviewOrTest()
        case .configuredRemote, .iosCompanion:
            try await adoptConfiguredRemoteHost()
        #if os(macOS)
        case .debugExternal:
            try await adoptDebugExternalEngine()
        case .releaseEmbedded:
            try await spawnAndAdoptEmbeddedEngine()
        #else
        case .debugExternal, .releaseEmbedded:
            // iOS never runs a local engine; the strategy never yields these on
            // iOS, but the switch must stay exhaustive.
            status = .failed
            errorMessage = "No remote engine host configured. Set a custom host in Settings."
            throw BackendError.notRunning
        #endif
        }
    }

    /// `inert`: previews / XCTest host / UI-test. Adopt an external engine if
    /// one is up, else run with none — NEVER spawn or manage a lifecycle. The
    /// XCTest harness owns its own disposable engine; the host app must not
    /// launch the (often unbuilt) bundled engine nor terminate when it's missing.
    private func adoptInertHostForPreviewOrTest() async {
        expectedLaunchNonce = nil
        logger.info("Preview / playground / XCTest host / UI-test — connecting to external if up, else no-op")
        do {
            try await waitForBackend(timeout: 1.5)
            logger.info("Connected to external backend")
        } catch {
            logger.info("No external backend; host runs without managing one")
        }
        status = .running
        isExternalBackend = true
    }

    /// `configuredRemote` / `iosCompanion`: connect to the explicit/paired host,
    /// never spawn a local engine. Throws on failure so `start()` surfaces the
    /// diagnosis instead of falling through to a local spawn.
    private func adoptConfiguredRemoteHost() async throws {
        expectedLaunchNonce = nil
        logger.info("Configured remote host: \(EngineConfig.host.absoluteString, privacy: .public)")
        do {
            try await waitForBackend(timeout: 5)
            status = .running
            isExternalBackend = true
            logger.info("Connected to configured external backend")
        } catch {
            status = .failed
            errorMessage = error.localizedDescription
            logger.error("Configured external backend did not respond: \(error.localizedDescription, privacy: .public)")
            throw error
        }
    }

    #if os(macOS)
    /// `debugExternal`: the engine is deliberately NOT bundled in Debug (the
    /// embed phase is Release-only, #3042), so we NEVER spawn — adopt a
    /// developer-run engine on :8765. If nothing is up, fail with the actionable
    /// start_backend.sh message; the window renders the diagnosis + Retry and the
    /// app never terminates.
    private func adoptDebugExternalEngine() async throws {
        expectedLaunchNonce = nil
        logger.info("DEBUG mode: adopting external engine on :8765 (engine not bundled in Debug)")
        do {
            try await waitForBackend(timeout: 5)
            status = .running
            isExternalBackend = true
            logger.info("Connected to external backend (will not manage lifecycle)")
        } catch {
            status = .failed
            logger.error("No external engine on :8765 in Debug — start it with start_backend.sh")
            throw BackendError.backendAppNotFound
        }
    }

    /// `releaseEmbedded`: spawn the bundled engine, app-authoritative token
    /// (#2862). The ONLY strategy that spawns and manages a lifecycle.
    /// Briefcase-bundled engine cold-starts in ~25s on Apple Silicon (heavy ML
    /// imports + DB init); 90s gives margin on slower I/O and contended startup.
    private func spawnAndAdoptEmbeddedEngine() async throws {
        logger.info("Starting embedded backend...")
        status = .starting
        // Pre-flight the port (#2863). Sweep our own orphans, then if the port
        // is STILL held by a process we can't claim, ask the user (Stop it /
        // Use it / Quit) rather than silently adopting an engine that may
        // reject our token and leave a blank window.
        switch try resolvePortConflict() {
        case .adoptExisting:
            isExternalBackend = true
            expectedLaunchNonce = nil
            // Adoption is gated on the authenticated probe: if the existing
            // engine rejects our token, waitForBackend throws and we surface
            // failure instead of a blank window.
            try await waitForBackend(timeout: 30)
            status = .running
            logger.info("Adopted user-approved existing engine on port 8765")
        case .spawnOurs:
            try await launchEmbeddedBackend()
            // Bounded by the child, not a clock (#3930) — we spawned this engine,
            // so its liveness is knowable and a fixed budget is just the app
            // racing its own subprocess.
            try await waitForSpawnedBackend()
            // #3975: waitForSpawnedBackend already required an authenticated
            // /api/registry 200 (= token accepted), so the token is provably on
            // disk and working — the redundant waitForToken here was dead. Removed.
            status = .running
            logger.info("Embedded backend started successfully")
        }
    }
    #endif

    /// Stop the embedded backend
    func stop() {
        // Don't stop external backends (user-managed)
        if isExternalBackend {
            logger.info("Using external backend - leaving it running (user-managed)")
            status = .stopped
            return
        }

        guard let pid = backendPID else {
            logger.info("ℹ️  No embedded backend PID tracked (may not have launched yet or using external)")
            status = .stopped
            return
        }

        logger.info("Stopping embedded backend (PID: \(pid))...")

        // Mark intentional so the terminationHandler doesn't flip .failed.
        intentionalStop = true

        // Clear state immediately
        backendPID = nil
        status = .stopped

        // Graceful shutdown - send SIGTERM
        kill(pid, SIGTERM)

        // Wait up to 5 seconds for graceful shutdown (synchronous)
        // This must be synchronous so applicationWillTerminate waits for it
        for attempt in 0..<50 {
            // Check if process is still running
            if kill(pid, 0) != 0 {
                // Process no longer exists
                logger.info("Backend stopped gracefully after \(attempt * 100)ms")
                return
            }
            // Sleep for 100ms
            Thread.sleep(forTimeInterval: 0.1)
        }

        // Force kill if still running after 5 seconds
        if kill(pid, 0) == 0 {
            logger.warning("Backend didn't shut down gracefully after 5s, force killing...")
            kill(pid, SIGKILL)

            // Give it one more second to die
            Thread.sleep(forTimeInterval: 1.0)

            if kill(pid, 0) == 0 {
                logger.error("Failed to kill backend process (PID: \(pid))")
            } else {
                logger.info("Backend force-killed successfully")
            }
        }
    }

    deinit {
        // Clean up backend on service deallocation (shouldn't happen in normal app lifecycle).
        // `backendPID` is set only on the embedded-spawn path and stays nil for every
        // external-backend branch, so a non-nil pid already implies an embedded backend —
        // the former `!isExternalBackend` guard was redundant. Dropping that read keeps
        // `isExternalBackend` fully @Observable-tracked for the Settings views while letting
        // this nonisolated deinit compile (it no longer touches a main-actor-isolated prop).
        if let pid = backendPID {
            logger.warning("EmbeddedBackendService deinit - terminating backend (PID: \(pid))")
            logger.warning("This shouldn't happen in normal app lifecycle - backend should be stopped via stop()")
            kill(pid, SIGTERM)
        }
    }

    // MARK: - Private Helpers

    #if os(macOS)
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

    // swiftlint:disable:next function_body_length
    private func launchEmbeddedBackend() async throws {
        let bundlePath = Bundle.main.bundlePath

        // Bundle is named "Fichero Engine.app" (briefcase formal_name =
        // "Fichero Engine"), bundle ID app.fichero.fichero.engine.
        let candidates = Self.engineBundleSubpaths.map { "\(bundlePath)/\($0)" }
        let backendAppPath = candidates.first {
            FileManager.default.fileExists(atPath: "\($0)/Contents/MacOS/Fichero Engine")
        }

        // Check if backend executable exists
        guard let backendAppPath else {
            let executablePath = candidates[0] + "/Contents/MacOS/Fichero Engine"
            logger.error("Backend executable not found at: \(executablePath)")
            // Debug builds skip the "Embed Fichero Engine" phase (it only runs in
            // Release), so in a Debug ⌘R the engine is expected to be running
            // externally on :8765. If it isn't, that's this path.
            logger.error(
                "Debug: start the engine first — fichero-engine/scripts/start_backend.sh. Release: briefcase build macOS --app engine (in fichero-engine/), then rebuild."
            )
            throw BackendError.backendAppNotFound
        }
        let executablePath = "\(backendAppPath)/Contents/MacOS/Fichero Engine"
        logger.info("Embedded engine: \(backendAppPath)")

        // Port pre-flight (orphan sweep by the DMG build; a loopback probe under
        // the sandbox) already ran in resolvePortConflict() before we got here —
        // including in DEBUG (#2863). By this point the port is ours to bind.

        let accessMaterial: RemoteAccessTLSMaterial
        let publicBaseURL: URL?
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
            publicBaseURL = url
            accessMaterial = try await prepareRemoteAccessTLSMaterial(
                executablePath: executablePath,
                publicBaseURL: url
            )
        } else {
            publicBaseURL = nil
            accessMaterial = try await prepareLocalAccessTLSMaterial(executablePath: executablePath)
        }

        // Persist the SPKI pin for every host the engine binds to. The
        // remote-access cert is also served on loopback, so pins match (#2611).
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

        // Build the child env from the app's environment with every inherited
        // FICHERO_* stripped (#3933). The engine's security posture — auth on/off
        // (FICHERO_DISABLE_AUTH), bind surface (FICHERO_LAN_HOST/FICHERO_BIND_HOST)
        // — is decided ENTIRELY by the FICHERO_* keys the app sets below, never by
        // a stray one in the launching shell. `FICHERO_DISABLE_AUTH=1 open
        // Fichero.app` must not spawn an auth-less engine. Non-FICHERO vars (PATH,
        // HOME, locale, dyld/xpc, …) are inherited unchanged — the bundled
        // interpreter needs them and none influence engine auth or bind. This
        // fails closed for any FICHERO_* added later: unknown ones are dropped
        // until explicitly set here.
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
        process.environment = environment

        // Diagnostic (#757): capture engine stdout/stderr to a tail-able file
        // in ~/Library/Logs/ so Release-build engine failures surface instead
        // of getting silently swallowed.
        let logURL = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero/engine.log")
        try? FileManager.default.createDirectory(
            at: logURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let logHandle = try FileHandle(forWritingTo: logURL)
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
        process.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            Task { @MainActor [weak self] in
                guard let self, !self.intentionalStop else { return }
                let tail = Self.tailEngineLog(lines: 20)
                self.status = .failed
                self.errorMessage = "The engine exited unexpectedly (code \(code))."
                    + (tail.isEmpty ? "" : "\n\n\(tail)")
                logger.error("Engine terminated unexpectedly (code \(code))")
            }
        }

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
        isExternalBackend = false
        logger.info("Tracking embedded backend PID: \(pid)")
    }

    // MARK: - TLS material cache (#3936)

    /// What is worth remembering between launches: the paths the engine derived.
    /// Deliberately NOT the pin — see `prepareTLSMaterial`.
    private struct CachedTLSPaths: Codable {
        let bindHost: String
        let certificatePath: String
        let keyPath: String
    }

    private static let tlsCacheDefaultsPrefix = "fichero.engine.tls_material|"

    /// Everything that could change WHICH material the engine hands back: the
    /// arguments (host / port / public URL / alt hosts) and the engine binary's
    /// own identity. The binary matters because an engine update could change how
    /// the material directory is derived, and a stale path would leave us pinning
    /// a certificate the new engine no longer serves.
    private static func tlsCacheKey(executablePath: String, arguments: [String]) -> String? {
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: executablePath),
              let size = attrs[.size] as? Int,
              let modified = attrs[.modificationDate] as? Date else {
            return nil  // Can't identify the binary → don't risk a stale cache.
        }
        let engineIdentity = "\(executablePath)|\(size)|\(modified.timeIntervalSince1970)"
        return tlsCacheDefaultsPrefix + "\(engineIdentity)|\(arguments.joined(separator: " "))"
    }

    private static func cachedTLSMaterial(forKey key: String) -> RemoteAccessTLSMaterial? {
        guard let data = UserDefaults.standard.data(forKey: key),
              let paths = try? JSONDecoder().decode(CachedTLSPaths.self, from: data),
              FileManager.default.fileExists(atPath: paths.certificatePath),
              FileManager.default.fileExists(atPath: paths.keyPath) else {
            return nil
        }
        // The pin comes from the certificate ON DISK, never from the cache, so it
        // cannot be stale against a rotated cert.
        guard let pin = try? spkiPin(ofCertificateAtPath: paths.certificatePath) else {
            logger.warning("Cached TLS cert unreadable — falling back to the engine (#3936)")
            return nil
        }
        return RemoteAccessTLSMaterial(
            bindHost: paths.bindHost,
            certificatePath: paths.certificatePath,
            keyPath: paths.keyPath,
            spkiPin: pin
        )
    }

    private static func storeTLSMaterial(_ material: RemoteAccessTLSMaterial, forKey key: String) {
        let paths = CachedTLSPaths(
            bindHost: material.bindHost,
            certificatePath: material.certificatePath,
            keyPath: material.keyPath
        )
        guard let data = try? JSONEncoder().encode(paths) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    /// The engine's `_spki_pin_from_certificate` in Swift: PEM → DER → the
    /// certificate's SubjectPublicKeyInfo, base64. Byte-identical by construction
    /// — the engine base64-encodes the same SPKI DER, and
    /// `RemoteCertificatePinning.spkiPin(for:)` is the same encoding the pinning
    /// layer validates against.
    static func spkiPin(ofCertificateAtPath path: String) throws -> String {
        let pem = try String(contentsOfFile: path, encoding: .utf8)
        guard let der = derFromPEM(pem),
              let certificate = SecCertificateCreateWithData(nil, der as CFData),
              let publicKey = SecCertificateCopyKey(certificate) else {
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: 3,
                    userInfo: [NSLocalizedDescriptionKey: "Could not read the engine's TLS certificate."]
                )
            )
        }
        return try RemoteCertificatePinning.spkiPin(for: publicKey)
    }

    /// Strip the PEM armour and decode. Mirrors the engine's `_pem_to_der`.
    static func derFromPEM(_ pem: String) -> Data? {
        let body = pem
            .split(separator: "\n")
            .filter { !$0.contains("BEGIN CERTIFICATE") && !$0.contains("END CERTIFICATE") }
            .joined()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return Data(base64Encoded: body, options: .ignoreUnknownCharacters)
    }

    private func prepareLocalAccessTLSMaterial(executablePath: String) async throws -> RemoteAccessTLSMaterial {
        try await prepareTLSMaterial(
            executablePath: executablePath,
            arguments: ["--prepare-local-access"],
            failureMessage: "Local engine TLS preparation failed."
        )
    }

    private func prepareRemoteAccessTLSMaterial(
        executablePath: String,
        publicBaseURL: URL
    ) async throws -> RemoteAccessTLSMaterial {
        try await prepareTLSMaterial(
            executablePath: executablePath,
            arguments: [
                "--prepare-remote-access",
                "--public-base-url",
                publicBaseURL.absoluteString
            ],
            failureMessage: "Remote access TLS preparation failed."
        )
    }

    /// TLS material for the engine, WITHOUT paying for the engine to tell us
    /// (#3936).
    ///
    /// `remote_access_tls.py` only generates when the cert or key is MISSING —
    /// otherwise it re-reads the existing cert, re-derives the pin, and returns.
    /// So every launch after the first spawned the whole 1.0GB engine binary, on
    /// the main actor, to learn something already on disk. Measured at 2.74s.
    ///
    /// The paths are the only thing we cannot compute (the engine derives the
    /// material directory from host/port/URL/alt-hosts), so those are cached. The
    /// SPKI pin is NOT cached — it is re-derived from the certificate file on
    /// every launch, which is a file read and a parse. That is both cheaper than
    /// a subprocess and strictly safer than caching a pin and guessing at
    /// staleness with mtime/size: a rotated cert produces a new pin automatically,
    /// because the pin is only ever read from the cert actually on disk.
    ///
    /// The cache key includes the engine binary's identity, so an engine update
    /// that changed the material-directory derivation invalidates it — otherwise
    /// we could pin a cert from a directory the new engine no longer serves.
    private func prepareTLSMaterial(
        executablePath: String,
        arguments: [String],
        failureMessage: String
    ) async throws -> RemoteAccessTLSMaterial {
        let cacheKey = Self.tlsCacheKey(executablePath: executablePath, arguments: arguments)
        if let cacheKey, let cached = Self.cachedTLSMaterial(forKey: cacheKey) {
            LaunchProfile.milestone("engine TLS material reused (no subprocess)")
            logger.info("TLS material reused from cache — engine subprocess skipped (#3936)")
            return cached
        }

        // #3936: the subprocess spawns the ~1GB engine and blocks on
        // `waitUntilExit()` for ~2.74s. On a cache HIT (above) we skip it, but on a
        // MISS — every user's first launch, and EVERY dev launch (the mtime-keyed
        // cache invalidates on each engine rebuild) — it used to freeze the main
        // actor and stall first frame. Run it OFF the main actor; only the cheap
        // cache lookup + pin re-derivation stay on main.
        let material = try await Task.detached(priority: .userInitiated) {
            try Self.runEngineTLSPrep(
                executablePath: executablePath,
                arguments: arguments,
                failureMessage: failureMessage
            )
        }.value
        if let cacheKey {
            Self.storeTLSMaterial(material, forKey: cacheKey)
        }
        return material
    }

    /// The subprocess path: only when the material genuinely has to be generated
    /// (first launch, rotated cert, engine update).
    /// nonisolated + static (#3936): self-contained (local Process/pipes only), so
    /// it can run off the @MainActor in a detached task without blocking first frame.
    nonisolated private static func runEngineTLSPrep(
        executablePath: String,
        arguments: [String],
        failureMessage: String
    ) throws -> RemoteAccessTLSMaterial {
        let tlsPhase = LaunchProfile.beginPhase("engine TLS prep (subprocess)")
        defer { LaunchProfile.endPhase("engine TLS prep (subprocess)", tlsPhase) }
        LaunchProfile.milestone("engine TLS prep — spawning engine")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        process.arguments = arguments

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()

        // Drain BOTH pipes concurrently, and BEFORE waiting. Waiting first
        // deadlocks forever the moment the child writes more than the ~64KB pipe
        // buffer: it blocks in write() waiting for a reader that is blocked in
        // waitUntilExit() waiting for it to exit. Draining them in sequence has
        // the same bug on the pipe not currently being read.
        let errorBox = DataBox()
        let drained = DispatchSemaphore(value: 0)
        let errorHandle = stderr.fileHandleForReading
        DispatchQueue.global(qos: .userInitiated).async {
            errorBox.value = errorHandle.readDataToEndOfFile()
            drained.signal()
        }
        let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
        drained.wait()
        let errorData = errorBox.value

        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let message = String(data: errorData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
                ?? failureMessage
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: Int(process.terminationStatus),
                    userInfo: [NSLocalizedDescriptionKey: message]
                )
            )
        }

        do {
            return try JSONDecoder().decode(RemoteAccessTLSMaterial.self, from: outputData)
        } catch {
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "Could not decode remote access TLS material."]
                )
            )
        }
    }
    #endif

    // MARK: - The spawned engine's wait (#3930)

    /// How long a SPAWNED engine may stay alive without ever serving before we
    /// stop believing it. This is an INSANITY cap for a hung process, not a
    /// budget the engine is expected to fit inside: a real cold start is import
    /// + lifespan + bind (~23s measured, and slower on a busy machine or a cold
    /// file cache). Nothing normal should ever come near it.
    static let spawnedEngineInsanityCap: TimeInterval = 300

    /// One step of the spawned-engine wait, as a pure decision (#3930).
    ///
    /// A live child that has not bound yet is NOT a failure — it is startup, and
    /// there is nothing to tell the user and nothing for them to do. Only two
    /// things end the wait early: it served, or it died.
    ///
    /// Order matters: an exit diagnosis beats the cap, so a child that dies at
    /// the cap boundary still reports why it died rather than "never became
    /// ready". Pure so the timing invariants are testable without an engine —
    /// the `BackendConnectionView.connectionFailureTitle` pattern (#3341).
    enum SpawnWaitStep: Equatable {
        case ready
        case keepWaiting
        /// The child exited; `diagnosis` is the terminationHandler's reason + log tail.
        case engineExited(diagnosis: String)
        /// Alive, but never served before the insanity cap.
        case neverBecameReady
    }

    static func spawnWaitStep(
        readiness: EngineReadiness,
        exitDiagnosis: String?,
        elapsed: TimeInterval,
        cap: TimeInterval = spawnedEngineInsanityCap
    ) -> SpawnWaitStep {
        if readiness == .ready { return .ready }
        if let exitDiagnosis { return .engineExited(diagnosis: exitDiagnosis) }
        if elapsed >= cap { return .neverBecameReady }
        return .keepWaiting
    }

    /// Non-nil once the spawned child has exited unexpectedly. The
    /// `terminationHandler` set on the process has already flipped `.failed` and
    /// put the exit code + `engine.log` tail into `errorMessage`, so the reason
    /// is assembled before we ask.
    ///
    /// Read from that handler rather than by polling `kill(pid, 0)`: for OUR OWN
    /// child, `kill(pid, 0)` keeps SUCCEEDING while the process sits as a zombie
    /// awaiting reap, so PID polling can report a dead engine as alive. The
    /// handler fires on reap, which is the moment the truth is knowable.
    private func spawnedEngineExitDiagnosis() -> String? {
        guard status == .failed, let errorMessage, !errorMessage.isEmpty else { return nil }
        return errorMessage
    }

    /// Wait for the engine WE spawned, bounded by its liveness (#3930).
    ///
    /// The old fixed budget made the app race its own engine, and whoever won
    /// decided whether the user saw the app or a failure gate. The engine's cold
    /// start is not something the app can predict, so it stopped guessing.
    private func waitForSpawnedBackend() async throws {
        // The engine's own startup, as one bar in Instruments. `defer` closes it
        // on every exit, so a launch that fails still renders a bar that ends
        // where it gave up rather than a dangling interval.
        let waitPhase = LaunchProfile.beginPhase("engine startup wait")
        defer { LaunchProfile.endPhase("engine startup wait", waitPhase) }

        let startTime = Date()
        var pollInterval: Duration = .milliseconds(100)
        var markedBound = false

        while true {
            if Task.isCancelled { throw CancellationError() }

            let result = await probeReadiness()
            lastReadiness = result

            // The engine answered health AND echoed our launch nonce: the socket
            // is bound and it is OUR process. Distinct from ready — the token
            // exchange may still be pending — and it is the boundary between
            // "engine starting up" (its import + lifespan) and "app finishing
            // auth", which is the split a launch profile has to show (#3946).
            // `.notResponding` also covers health-200-but-registry-5xx, so this
            // marks the first CONFIRMED bind, never an earlier guess.
            if !markedBound, result != .notResponding {
                markedBound = true
                LaunchProfile.milestone("engine bound (health + identity answered)")
            }

            switch Self.spawnWaitStep(
                readiness: result,
                exitDiagnosis: spawnedEngineExitDiagnosis(),
                elapsed: Date().timeIntervalSince(startTime)
            ) {
            case .ready:
                logger.info("Backend readiness passed (health 200 + identity + authenticated probe)")
                return
            case .engineExited(let diagnosis):
                // Surface the real reason NOW rather than polling a dead process
                // until the cap and then blaming a timeout.
                logger.error("Engine exited during startup — surfacing immediately (#3930)")
                throw BackendError.engineDidNotStart(diagnosis: diagnosis)
            case .neverBecameReady:
                logger.error("Engine alive but never served within the insanity cap (#3930)")
                throw BackendError.engineDidNotStart(diagnosis: Self.insanityCapDiagnosis())
            case .keepWaiting:
                break
            }

            try await Task.sleep(for: pollInterval)
            if Date().timeIntervalSince(startTime) > 1 {
                pollInterval = .milliseconds(500)
            }
        }
    }

    private static func insanityCapDiagnosis() -> String {
        let minutes = Int(spawnedEngineInsanityCap / 60)
        let base = "The engine started but never began serving after \(minutes) minutes."
        let tail = tailEngineLog(lines: 20)
        return tail.isEmpty ? base : "\(base)\n\n\(tail)"
    }

    /// Poll until the engine is genuinely READY (#2862): not just answering
    /// health-200, but the instance we spawned (nonce echo) AND accepting the
    /// app's token (authenticated /api/registry 200). Throws `.timeout` if it
    /// never reaches `.ready`. The last probe result is stored in
    /// `lastReadiness` for #2864's diagnosis.
    ///
    /// The CLOCK-bounded wait, for engines we did not spawn and cannot watch: a
    /// remote host, a dev-run uvicorn, an adopted engine on :8765. There is no
    /// child there, so a timeout is the only honest bound. The engine we spawn
    /// uses `waitForSpawnedBackend()` instead (#3930).
    private func waitForBackend(timeout: TimeInterval) async throws {
        let startTime = Date()
        // Poll aggressively at first (100ms) so we catch the backend as soon as
        // it's ready — local FastAPI typically answers within 200-400ms. Back
        // off to 500ms after the first second to avoid log spam if the backend
        // is genuinely slow/stuck.
        var pollInterval: Duration = .milliseconds(100)
        while Date().timeIntervalSince(startTime) < timeout {
            if Task.isCancelled {
                throw CancellationError()
            }

            let result = await probeReadiness()
            lastReadiness = result
            if result == .ready {
                logger.info("Backend readiness passed (health 200 + identity + authenticated probe)")
                return
            }

            try await Task.sleep(for: pollInterval)
            if Date().timeIntervalSince(startTime) > 1 {
                pollInterval = .milliseconds(500)
            }
        }

        throw BackendError.timeout
    }

    /// One authenticated readiness probe — delegates to the shared
    /// `EngineReadinessProbe` (#3106), the single home for the readiness contract.
    func probeReadiness() async -> ReadinessResult {
        await EngineReadinessProbe(hostURL: backendURL, expectedNonce: expectedLaunchNonce).probe()
    }

    // MARK: - Token & identity helpers (#2862)

    /// The base environment for the spawned engine: the app's environment with
    /// every inherited `FICHERO_*` key removed (#3933).
    ///
    /// The engine reads `FICHERO_*` to decide auth (`FICHERO_DISABLE_AUTH`) and
    /// its bind surface (`FICHERO_LAN_HOST`, `FICHERO_BIND_HOST`,
    /// `FICHERO_ALLOW_NON_LOOPBACK_BIND`). Those must come only from what the app
    /// sets on the child — not from a stray value in the shell that launched the
    /// app (`FICHERO_DISABLE_AUTH=1 open Fichero.app` must NOT disable auth). All
    /// non-FICHERO vars pass through unchanged so the bundled interpreter still
    /// has PATH/HOME/locale/etc. Pure + static so it is unit-testable without a
    /// running process.
    static func childEnvironmentBase(inheriting inherited: [String: String]) -> [String: String] {
        inherited.filter { !$0.key.hasPrefix("FICHERO_") }
    }

    /// 32 cryptographically-random bytes, base64url without padding — same
    /// shape as the engine's `secrets.token_urlsafe(32)`. Used for both the
    /// bootstrap token and the launch nonce.
    static func generateSecret() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    /// Write the bootstrap token to `url` with 0600 perms (owner-only), matching
    /// the engine's write. The app is authoritative for the token it minted.
    static func writeBootstrapTokenFile(_ token: String, at url: URL) {
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try token.data(using: .utf8)?.write(to: url, options: .atomic)
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o600], ofItemAtPath: url.path
            )
        } catch {
            logger.error("Failed to write bootstrap token file: \(error.localizedDescription, privacy: .public)")
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
    /// SIGTERM a "Fichero Engine" subprocess left over from a previous run of
    /// **this** app that didn't get a chance to call .stop() (e.g. SIGKILL,
    /// crash, or force-quit). Called before spawning a new engine so the new
    /// spawn can bind port 8765 cleanly.
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
    static func terminateOrphanEngines() {
        if EngineConfig.usesCustomHost {
            logger.info("Custom/remote engine host configured — skipping orphan sweep (no local engine is ours to kill)")
            return
        }

        let thisAppPID = ProcessInfo.processInfo.processIdentifier

        let pgrep = Process()
        pgrep.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        pgrep.arguments = ["-f", "Fichero Engine.app/Contents/MacOS"]
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
    private static func engineParentPID(_ pid: pid_t) -> pid_t? {
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
    private static func isProcessAlive(_ pid: pid_t) -> Bool {
        if pid <= 0 { return false }
        return kill(pid, 0) == 0 || errno == EPERM
    }
    #endif  // !FICHERO_APP_STORE — end of the non-child process machinery

    static func waitForPortToClear(_ port: UInt16, timeout: TimeInterval) {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if !portInUse(port) { return }
            Thread.sleep(forTimeInterval: 0.1)
        }
    }

    private static func portInUse(_ port: UInt16) -> Bool {
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
    static func portIsAcceptingConnections(_ port: UInt16) -> Bool {
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

    #if !FICHERO_APP_STORE
    /// PID of the process LISTENing on `port`, or nil if the port is free.
    ///
    /// Shells out to lsof, so it is compiled out of the App Store build (#3749);
    /// the sandbox permits no view of other processes' descriptors. MAS uses
    /// portIsAcceptingConnections() above, which answers "is it taken?" without
    /// asking "by whom?".
    private static func pidOnPort(_ port: UInt16) -> pid_t? {
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

    /// Port pre-flight (#2863/#3111). Sweep our own orphans; if the port is
    /// then STILL held by a process we can't claim, the user must choose —
    /// but the decision now happens IN-WINDOW (`portConflict` phase), not in a
    /// pre-window `NSAlert`. When no choice has been made yet, throw
    /// `.portConflict(pid)` so the connection view can render Stop it / Use it /
    /// Quit; the button sets `pendingPortConflictResolution` and retries, and
    /// this consumes it exactly once. Never silently adopts or silently kills.
    private func resolvePortConflict() throws -> PortResolution {
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
        Self.terminateOrphanEngines()
        Self.waitForPortToClear(8765, timeout: 3.0)
        let holder = Self.pidOnPort(8765).map(Int.init)

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
                Self.waitForPortToClear(8765, timeout: 5.0)
                if Self.portInUse(8765) {
                    kill(pid, SIGKILL)
                    Self.waitForPortToClear(8765, timeout: 2.0)
                }
            }
            pendingPortConflictResolution = nil
            return .spawnOurs
        }
        #endif
    }

    #endif

    /// Last `lines` lines of the engine log, for surfacing a real cause when
    /// the engine dies (#2863). Empty string if the log can't be read.
    ///
    /// Deliberately OUTSIDE `#if os(macOS)`: this is FileManager + String and
    /// needs no macOS API, but `insanityCapDiagnosis()` — which calls it — is
    /// unguarded, and iOS instantiates this class (`FicheroApp_iOS.swift:14`).
    /// While this sat inside the macOS block the iOS build failed with
    /// "Cannot find 'tailEngineLog' in scope", and the green macOS build hid it.
    static func tailEngineLog(lines: Int) -> String {
        let logURL = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero/engine.log")
        guard let contents = try? String(contentsOf: logURL, encoding: .utf8) else {
            return ""
        }
        let tail = contents.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines)
        return tail.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Readiness probe payload

// MARK: - Errors

/// Somewhere for a background pipe drain to put its bytes. `@unchecked` is
/// honest here: the semaphore, not the type, is what orders the write against
/// the read.
private final class DataBox: @unchecked Sendable {
    var value = Data()
}

enum BackendError: LocalizedError {
    case notRunning
    case backendAppNotFound
    case launchFailed(Error)
    case timeout
    /// The engine we SPAWNED never served: it exited, or stayed alive without
    /// ever binding until the insanity cap (#3930). `diagnosis` carries the
    /// engine.log tail, so a launch failure explains itself instead of reporting
    /// a bare timeout the user can do nothing with.
    case engineDidNotStart(diagnosis: String)
    /// A process we didn't spawn holds port 8765 (#3111). Carries the holder's
    /// PID (when known) so the in-window portConflict phase can name it. Handled
    /// by the launch orchestrator (→ `markPortConflict`), never shown as a raw
    /// error string.
    case portConflict(pid: Int?)

    var errorDescription: String? {
        switch self {
        case .notRunning:
            return "Backend is not running"
        case .portConflict(let pid):
            let who = pid.map(String.init) ?? "unknown"
            return "Port 8765 is held by another process (PID \(who))."
        case .backendAppNotFound:
            // Debug builds don't embed the engine (the embed phase is Release-only),
            // so the usual cause in a Debug ⌘R is simply no engine running on :8765.
            #if DEBUG
            return "The Fichero Engine isn't running. In a Debug build the engine is "
                + "not bundled — start it first with fichero-engine/scripts/start_backend.sh "
                + "(or briefcase dev), then Retry."
            #else
            return "Backend app not found in bundle. Build the engine with: "
                + "briefcase build macOS --app engine (in fichero-engine/), then rebuild Fichero in Xcode."
            #endif
        case .launchFailed(let error):
            return "Failed to launch backend app: \(error.localizedDescription)"
        case .timeout:
            return "Backend failed to start within timeout"
        case .engineDidNotStart(let diagnosis):
            return diagnosis
        }
    }
}

// swiftlint:enable type_body_length
